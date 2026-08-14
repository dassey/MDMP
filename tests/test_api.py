"""HTTP layer: routing, auth enforcement, the prompt endpoints, concurrency.

These run against a real server on a loopback port, so they exercise the same
path a browser does — including cookies, JSON encoding, and status codes.
"""

import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from harness import api, db, server  # noqa: E402
from harness.mdmp.flow_def import FLOW  # noqa: E402

PORT = 8137


class Client:
    def __init__(self, base):
        self.base = base
        self.cookie = None

    def call(self, method, path, body=None, raw=False):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.cookie:
            req.add_header("Cookie", self.cookie)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                sc = resp.headers.get("Set-Cookie")
                if sc:
                    self.cookie = sc.split(";")[0]
                payload = resp.read()
                return payload if raw else json.loads(payload.decode())
        except urllib.error.HTTPError as e:
            raise HttpFail(e.code, e.read().decode("utf-8", "replace"))

    def get(self, p, raw=False):
        return self.call("GET", p, None, raw)

    def post(self, p, b=None):
        return self.call("POST", p, b or {})

    def delete(self, p):
        return self.call("DELETE", p, None)


class HttpFail(Exception):
    def __init__(self, code, body):
        super().__init__("%s: %s" % (code, body))
        self.code = code
        self.body = body


class ApiCase(unittest.TestCase):
    """One shared server for the whole class; a fresh database per class."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="mdmp-api-")
        os.environ["MDMP_QUIET"] = "1"
        db._LOCAL.__dict__.pop("conn", None)
        db.init(os.path.join(cls.tmp, "api.db"))
        api.CORPUS_DIR = os.path.join(ROOT, "corpus")
        cls.httpd = server.serve("127.0.0.1", PORT,
                                 static_dir=os.path.join(ROOT, "static"))
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % PORT

        cls.admin = Client(cls.base)
        cls.admin.post("/api/setup", {"username": "admin", "password": "testpass",
                                      "display_name": "COL Admin"})
        cls.admin.post("/api/users", {"username": "planner", "password": "testpass",
                                      "display_name": "MAJ Plans",
                                      "role": "planner"})
        cls.admin.post("/api/users", {"username": "staffer", "password": "testpass",
                                      "display_name": "CPT Staff", "role": "staff"})
        cls.admin.post("/api/users", {"username": "watcher", "password": "testpass",
                                      "display_name": "Observer",
                                      "role": "observer"})

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def as_user(self, name):
        c = Client(self.base)
        c.post("/api/login", {"username": name, "password": "testpass"})
        return c

    def new_plan(self, name="PLAN"):
        return self.admin.post("/api/plans", {"name": name})["id"]


class TestRoutingAndStatic(ApiCase):
    def test_static_index_is_served(self):
        body = self.admin.get("/", raw=True).decode()
        self.assertIn("<title>MDMP Harness</title>", body)

    def test_unknown_path_falls_back_to_the_app_shell(self):
        body = self.admin.get("/some/deep/link", raw=True).decode()
        self.assertIn("app.js", body)

    def test_unknown_api_route_is_404(self):
        with self.assertRaises(HttpFail) as cm:
            self.admin.get("/api/nonexistent")
        self.assertEqual(cm.exception.code, 404)

    def test_path_traversal_is_refused(self):
        for path in ("/../serve.py", "/..%2fserve.py", "/static/../../serve.py"):
            body = self.admin.get(path, raw=True).decode("utf-8", "replace")
            self.assertNotIn("argparse", body)

    def test_security_headers_are_present(self):
        req = urllib.request.Request(self.base + "/api/bootstrap")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.headers.get("X-Content-Type-Options"),
                             "nosniff")

    def test_malformed_json_body_is_a_400(self):
        req = urllib.request.Request(self.base + "/api/login", data=b"{not json",
                                     method="POST")
        req.add_header("Content-Type", "application/json")
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 400)


class TestAuthEnforcement(ApiCase):
    def test_anonymous_is_rejected(self):
        anon = Client(self.base)
        for path in ("/api/plans", "/api/me", "/api/users", "/api/flow"):
            with self.assertRaises(HttpFail) as cm:
                anon.get(path)
            self.assertEqual(cm.exception.code, 401, path)

    def test_bad_password(self):
        c = Client(self.base)
        with self.assertRaises(HttpFail) as cm:
            c.post("/api/login", {"username": "admin", "password": "nope"})
        self.assertEqual(cm.exception.code, 401)

    def test_forged_cookie_is_rejected(self):
        c = Client(self.base)
        c.cookie = "mdmp_session=made-up-token"
        with self.assertRaises(HttpFail):
            c.get("/api/plans")

    def test_logout_invalidates_the_session(self):
        c = self.as_user("planner")
        c.get("/api/plans")
        c.post("/api/logout")
        with self.assertRaises(HttpFail):
            c.get("/api/plans")

    def test_only_admin_can_add_accounts(self):
        c = self.as_user("planner")
        with self.assertRaises(HttpFail) as cm:
            c.post("/api/users", {"username": "x", "password": "testpass"})
        self.assertEqual(cm.exception.code, 403)

    def test_only_admin_can_change_the_provider(self):
        c = self.as_user("planner")
        with self.assertRaises(HttpFail) as cm:
            c.post("/api/providers", {"provider": "ollama"})
        self.assertEqual(cm.exception.code, 403)

    def test_observer_cannot_answer_a_field(self):
        pid = self.new_plan("OBSERVER TEST")
        c = self.as_user("watcher")
        c.post("/api/plans/%d/join" % pid, {"role": "observer"})
        with self.assertRaises(HttpFail) as cm:
            c.post("/api/plans/%d/answer" % pid,
                   {"field": "unit_designation", "value": "x"})
        self.assertEqual(cm.exception.code, 403)

    def test_staff_cannot_approve_a_paragraph(self):
        pid = self.new_plan("APPROVAL TEST")
        self.admin.post("/api/plans/%d/phase" % pid, {"phase": "production"})
        c = self.as_user("staffer")
        c.post("/api/plans/%d/sections/p2" % pid, {"body": "ok"})   # allowed
        with self.assertRaises(HttpFail) as cm:
            c.post("/api/plans/%d/sections/p2" % pid, {"status": "approved"})
        self.assertEqual(cm.exception.code, 403)

    def test_admin_cannot_deactivate_themselves(self):
        me = self.admin.get("/api/me")["user"]
        with self.assertRaises(HttpFail) as cm:
            self.admin.post("/api/users/%d/deactivate" % me["id"])
        self.assertEqual(cm.exception.code, 400)


class TestPlanApi(ApiCase):
    def test_plan_needs_a_name(self):
        with self.assertRaises(HttpFail) as cm:
            self.admin.post("/api/plans", {"name": "   "})
        self.assertEqual(cm.exception.code, 400)

    def test_missing_plan_is_404(self):
        with self.assertRaises(HttpFail) as cm:
            self.admin.get("/api/plans/999999")
        self.assertEqual(cm.exception.code, 404)

    def test_unknown_field_is_404(self):
        pid = self.new_plan("FIELD TEST")
        with self.assertRaises(HttpFail) as cm:
            self.admin.post("/api/plans/%d/answer" % pid,
                            {"field": "not_a_field", "value": "x"})
        self.assertEqual(cm.exception.code, 404)

    def test_answer_history_is_kept(self):
        pid = self.new_plan("HISTORY")
        for v in ("first", "second", "third"):
            self.admin.post("/api/plans/%d/answer" % pid,
                            {"field": "unit_designation", "value": v})
        hist = self.admin.get("/api/plans/%d/history/unit_designation" % pid)
        self.assertEqual(len(hist["history"]), 3)
        self.assertEqual(hist["history"][0]["value"], "third")
        current = self.admin.get("/api/plans/%d" % pid)["answers"]
        self.assertEqual(current["unit_designation"], "third")

    def test_options_are_cached_until_a_dependency_changes(self):
        pid = self.new_plan("CACHE")
        self.admin.post("/api/plans/%d/answer" % pid,
                        {"field": "operation_type",
                         "value": "Offensive Operation: Attack"})
        first = self.admin.post("/api/plans/%d/options" % pid,
                                {"field": "specified_tasks"})
        again = self.admin.post("/api/plans/%d/options" % pid,
                                {"field": "specified_tasks"})
        self.assertFalse(first["cached"])
        self.assertTrue(again["cached"])
        self.admin.post("/api/plans/%d/answer" % pid,
                        {"field": "operation_type",
                         "value": "Defensive Operation: Area Defense"})
        after = self.admin.post("/api/plans/%d/options" % pid,
                                {"field": "specified_tasks"})
        self.assertFalse(after["cached"])

    def test_refresh_bypasses_the_cache(self):
        pid = self.new_plan("REFRESH")
        self.admin.post("/api/plans/%d/options" % pid, {"field": "echelon"})
        r = self.admin.post("/api/plans/%d/options" % pid,
                            {"field": "echelon", "refresh": True})
        self.assertFalse(r["cached"])

    def test_option_count_is_capped(self):
        pid = self.new_plan("CAP")
        r = self.admin.post("/api/plans/%d/options" % pid,
                            {"field": "echelon", "n": 500})
        self.assertLessEqual(len(r["options"]), 12)

    def test_stale_dependents_are_reported_on_save(self):
        pid = self.new_plan("STALE")
        self.admin.post("/api/plans/%d/answer" % pid,
                        {"field": "operation_type",
                         "value": "Offensive Operation: Attack"})
        self.admin.post("/api/plans/%d/answer" % pid,
                        {"field": "specified_tasks", "value": ["Attack."]})
        r = self.admin.post("/api/plans/%d/answer" % pid,
                            {"field": "operation_type",
                             "value": "Defensive Operation: Area Defense"})
        keys = [s["field"] for s in r["stale"]]
        self.assertIn("specified_tasks", keys)

    def test_warnord_endpoints_return_text(self):
        pid = self.new_plan("WARNORD")
        for n in (1, 2, 3):
            text = self.admin.get("/api/plans/%d/warnord/%d" % (pid, n),
                                  raw=True).decode()
            self.assertIn("WARNING ORDER #%d" % n, text)
            self.assertIn("ACKNOWLEDGE", text)

    def test_export_formats(self):
        pid = self.new_plan("EXPORT")
        self.admin.post("/api/plans/%d/answer" % pid,
                        {"field": "mission_statement",
                         "value": "2d BCT attacks at 010500Z to seize OBJ."})
        for fmt, marker in (("md", b"# Operation Order"),
                            ("txt", b"OPERATION ORDER"),
                            ("html", b"<html>"),
                            ("docx", b"PK"),
                            ("json", b"\"answers\"")):
            blob = self.admin.get("/api/plans/%d/export?format=%s" % (pid, fmt),
                                  raw=True)
            self.assertTrue(blob.startswith(marker) or marker in blob, fmt)

    def test_unknown_export_format_is_400(self):
        pid = self.new_plan("BADEXPORT")
        with self.assertRaises(HttpFail) as cm:
            self.admin.get("/api/plans/%d/export?format=wombat" % pid, raw=True)
        self.assertEqual(cm.exception.code, 400)

    def test_export_filename_is_sanitised(self):
        pid = self.admin.post("/api/plans",
                              {"name": "../../etc/passwd; rm -rf /"})["id"]
        req = urllib.request.Request(
            self.base + "/api/plans/%d/export?format=md" % pid)
        req.add_header("Cookie", self.admin.cookie)
        with urllib.request.urlopen(req) as resp:
            disp = resp.headers.get("Content-Disposition")
        self.assertNotIn("..", disp)
        self.assertNotIn("/", disp.split("filename=")[1])


class TestPromptApi(ApiCase):
    def setUp(self):
        # Server-wide overrides are shared by design, so clear them between
        # tests instead of letting execution order decide the outcome.
        db.ex("DELETE FROM prompts")
        self.pid = self.new_plan("PROMPT PLAN")

    def test_defaults_are_returned(self):
        r = self.admin.get("/api/plans/%d/prompt?field=mission_statement"
                           % self.pid)
        self.assertEqual(r["level"], "field")
        self.assertEqual(r["effective"]["system_source"], "built-in default")
        self.assertIn("MDMP", r["effective"]["system"])
        self.assertTrue(r["placeholders"])
        self.assertIn("PLANNING STEP", r["preview"]["user"])

    def test_preview_reflects_the_plan(self):
        self.admin.post("/api/plans/%d/answer" % self.pid,
                        {"field": "unit_designation", "value": "9th Cavalry"})
        r = self.admin.get("/api/plans/%d/prompt?field=mission_statement"
                           % self.pid)
        self.assertIn("9th Cavalry", r["preview"]["user"])

    def test_save_and_read_back_a_field_prompt(self):
        self.admin.post("/api/plans/%d/prompt?field=mission_statement" % self.pid,
                        {"system": "CUSTOM", "template": "Give me {n} options."})
        r = self.admin.get("/api/plans/%d/prompt?field=mission_statement"
                           % self.pid)
        self.assertEqual(r["effective"]["system"], "CUSTOM")
        self.assertEqual(r["preview"]["user"], "Give me 5 options.")
        self.assertIn("this plan", r["effective"]["system_source"])

    def test_step_prompt_applies_to_its_fields(self):
        self.admin.post("/api/plans/%d/prompt?step=mission_analysis" % self.pid,
                        {"system": "STEP SYSTEM", "template": "step template"})
        r = self.admin.get("/api/plans/%d/prompt?field=enemy_mlcoa" % self.pid)
        self.assertEqual(r["effective"]["system"], "STEP SYSTEM")
        # a field in a different step is untouched
        r2 = self.admin.get("/api/plans/%d/prompt?field=echelon" % self.pid)
        self.assertEqual(r2["effective"]["system_source"], "built-in default")

    def test_global_prompt_applies_to_everything(self):
        self.admin.post("/api/plans/%d/prompt" % self.pid,
                        {"system": "GLOBAL", "template": "global template"})
        for field in ("echelon", "enemy_mlcoa", "pace_plan"):
            r = self.admin.get("/api/plans/%d/prompt?field=%s"
                               % (self.pid, field))
            self.assertEqual(r["effective"]["system"], "GLOBAL", field)

    def test_plan_scoped_prompt_does_not_leak_to_another_plan(self):
        other = self.new_plan("OTHER PROMPT PLAN")
        self.admin.post("/api/plans/%d/prompt?field=echelon" % self.pid,
                        {"system": "ONLY HERE", "template": "t"})
        r = self.admin.get("/api/plans/%d/prompt?field=echelon" % other)
        self.assertEqual(r["effective"]["system_source"], "built-in default")

    def test_server_default_reaches_every_plan(self):
        other = self.new_plan("SERVER DEFAULT PLAN")
        self.admin.post("/api/plans/%d/prompt?field=echelon" % self.pid,
                        {"system": "SERVERWIDE", "template": "t",
                         "server_default": True})
        r = self.admin.get("/api/plans/%d/prompt?field=echelon" % other)
        self.assertEqual(r["effective"]["system"], "SERVERWIDE")
        self.assertIn("server default", r["effective"]["system_source"])

    def test_only_admin_may_set_the_server_default(self):
        c = self.as_user("planner")
        c.post("/api/plans/%d/join" % self.pid, {"role": "planner"})
        c.post("/api/plans/%d/prompt?field=echelon" % self.pid,
               {"system": "planner's own", "template": "t"})     # plan scope: ok
        with self.assertRaises(HttpFail) as cm:
            c.post("/api/plans/%d/prompt?field=echelon" % self.pid,
                   {"system": "x", "template": "t", "server_default": True})
        self.assertEqual(cm.exception.code, 403)

    def test_staff_cannot_edit_prompts(self):
        c = self.as_user("staffer")
        with self.assertRaises(HttpFail) as cm:
            c.post("/api/plans/%d/prompt?field=echelon" % self.pid,
                   {"system": "x", "template": "t"})
        self.assertEqual(cm.exception.code, 403)

    def test_reset_restores_the_built_in(self):
        self.admin.post("/api/plans/%d/prompt?field=echelon" % self.pid,
                        {"system": "TEMP", "template": "t"})
        self.admin.delete("/api/plans/%d/prompt?field=echelon&scope=plan"
                          % self.pid)
        r = self.admin.get("/api/plans/%d/prompt?field=echelon" % self.pid)
        self.assertEqual(r["effective"]["system_source"], "built-in default")

    def test_unknown_placeholders_are_reported_but_accepted(self):
        r = self.admin.post("/api/plans/%d/prompt?field=echelon" % self.pid,
                            {"system": "s", "template": "Use {wombat} here"})
        self.assertIn("wombat", r["unknown_placeholders"])
        p = self.admin.get("/api/plans/%d/prompt?field=echelon" % self.pid)
        self.assertIn("{wombat}", p["preview"]["user"])

    def test_broken_template_does_not_break_generation(self):
        self.admin.post("/api/plans/%d/prompt?field=echelon" % self.pid,
                        {"system": "s", "template": "unbalanced {"})
        r = self.admin.post("/api/plans/%d/options" % self.pid,
                            {"field": "echelon", "refresh": True})
        self.assertTrue(r["options"])

    def test_unknown_field_or_step_is_404(self):
        for qs in ("?field=nope", "?step=nope"):
            with self.assertRaises(HttpFail) as cm:
                self.admin.get("/api/plans/%d/prompt%s" % (self.pid, qs))
            self.assertEqual(cm.exception.code, 404)

    def test_prompt_source_is_reported_with_generated_options(self):
        self.admin.post("/api/plans/%d/prompt?field=echelon" % self.pid,
                        {"system": "s", "template": "t"})
        r = self.admin.post("/api/plans/%d/options" % self.pid,
                            {"field": "echelon", "refresh": True})
        self.assertIn("field", r["prompt"]["template_source"])

    def test_audit_endpoint_lists_overrides(self):
        self.admin.post("/api/plans/%d/prompt?step=coa_development" % self.pid,
                        {"system": "s", "template": "t"})
        rows = self.admin.get("/api/prompts")["prompts"]
        self.assertTrue(any(r["scope_key"] == "coa_development" for r in rows))
        self.assertTrue(any(r["label"] == "COA Development" for r in rows))

    def test_saving_the_editor_untouched_stores_nothing(self):
        """Open the editor, change nothing, press Save: no override appears."""
        url = "/api/plans/%d/prompt?field=echelon" % self.pid
        d = self.admin.get(url)
        r = self.admin.post(url, {"system": d["effective"]["system"],
                                  "template": d["effective"]["template"]})
        self.assertFalse(r["changed"])
        after = self.admin.get(url)
        self.assertIsNone(after["own_override"])
        self.assertEqual(after["effective"]["system_source"], "built-in default")
        self.assertEqual(self.admin.get("/api/prompts")["prompts"], [])

    def test_editing_one_half_leaves_the_other_inherited(self):
        self.admin.post("/api/plans/%d/prompt" % self.pid,
                        {"system": "GLOBAL SYSTEM", "template": "global {n}"})
        url = "/api/plans/%d/prompt?field=echelon" % self.pid
        d = self.admin.get(url)
        # the editor showed the global text in both boxes; only one is edited
        r = self.admin.post(url, {"system": d["effective"]["system"],
                                  "template": "field only {n}"})
        self.assertEqual(r["stored"], {"system": False, "template": True})
        after = self.admin.get(url)
        self.assertEqual(after["effective"]["template"], "field only {n}")
        self.assertEqual(after["effective"]["system"], "GLOBAL SYSTEM")
        self.assertIn("global", after["effective"]["system_source"])
        # changing the global system prompt still reaches this field
        self.admin.post("/api/plans/%d/prompt" % self.pid,
                        {"system": "GLOBAL SYSTEM v2", "template": "global {n}"})
        after = self.admin.get(url)
        self.assertEqual(after["effective"]["system"], "GLOBAL SYSTEM v2")
        self.assertEqual(after["effective"]["template"], "field only {n}")

    def test_a_server_default_is_not_copied_into_a_plan_override(self):
        self.admin.post("/api/plans/%d/prompt?field=echelon" % self.pid,
                        {"system": "SERVERWIDE", "template": "server {n}",
                         "server_default": True})
        url = "/api/plans/%d/prompt?field=echelon" % self.pid
        d = self.admin.get(url)
        r = self.admin.post(url, {"system": d["effective"]["system"],
                                  "template": d["effective"]["template"]})
        self.assertFalse(r["changed"])
        after = self.admin.get(url)
        self.assertIsNone(after["own_override"])
        self.assertIsNotNone(after["server_override"])
        self.assertIn("server default", after["effective"]["system_source"])


class TestProductionAndCollaboration(ApiCase):
    def test_two_users_edit_different_paragraphs(self):
        pid = self.new_plan("COLLAB")
        self.admin.post("/api/plans/%d/phase" % pid, {"phase": "production"})
        a = self.as_user("planner")
        b = self.as_user("staffer")
        a.post("/api/plans/%d/sections/p2/claim" % pid)
        b.post("/api/plans/%d/sections/p4/claim" % pid)
        a.post("/api/plans/%d/sections/p2" % pid, {"body": "A wrote this"})
        b.post("/api/plans/%d/sections/p4" % pid, {"body": "B wrote this"})
        secs = {s["key"]: s for s in
                self.admin.get("/api/plans/%d/sections" % pid)["sections"]}
        self.assertEqual(secs["p2"]["body"], "A wrote this")
        self.assertEqual(secs["p4"]["body"], "B wrote this")
        self.assertEqual(secs["p2"]["owner_name"], "MAJ Plans")
        self.assertEqual(secs["p4"]["owner_name"], "CPT Staff")

    def test_concurrent_answers_all_persist(self):
        """Twelve threads writing different fields at once."""
        pid = self.new_plan("CONCURRENT")
        fields = [f.key for f in FLOW.step("mission_analysis").fields][:12]
        errors = []

        def write(key):
            try:
                c = self.as_user("planner")
                c.post("/api/plans/%d/join" % pid, {"role": "planner"})
                c.post("/api/plans/%d/answer" % pid,
                       {"field": key, "value": "value for " + key
                        if FLOW.field(key).kind in ("text", "choice")
                        else ["value for " + key]})
            except Exception as exc:      # noqa: BLE001 - recorded and asserted
                errors.append("%s: %s" % (key, exc))

        threads = [threading.Thread(target=write, args=(k,)) for k in fields]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        self.assertEqual(errors, [])
        answers = self.admin.get("/api/plans/%d" % pid)["answers"]
        for key in fields:
            self.assertIn(key, answers)

    def test_concurrent_writes_to_one_field_leave_exactly_one_current(self):
        pid = self.new_plan("RACE")
        def write(i):
            c = self.as_user("planner")
            c.post("/api/plans/%d/join" % pid, {"role": "planner"})
            c.post("/api/plans/%d/answer" % pid,
                   {"field": "unit_designation", "value": "writer %d" % i})
        threads = [threading.Thread(target=write, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        rows = db.q("SELECT COUNT(*) AS n FROM answers WHERE plan_id=? AND "
                    "field_key='unit_designation' AND current=1", (pid,))
        self.assertEqual(rows[0]["n"], 1)

    def test_pulse_reports_activity_and_presence(self):
        pid = self.new_plan("PULSE")
        self.admin.post("/api/plans/%d/answer" % pid,
                        {"field": "unit_designation", "value": "x"})
        r = self.admin.get("/api/plans/%d/pulse?since=0" % pid)
        self.assertTrue(r["activity"])
        self.assertTrue(r["online"])
        since = r["last_id"]
        r2 = self.admin.get("/api/plans/%d/pulse?since=%d" % (pid, since))
        self.assertEqual(r2["activity"], [])

    def test_moving_to_production_drafts_the_order(self):
        pid = self.new_plan("DRAFT")
        self.admin.post("/api/plans/%d/answer" % pid,
                        {"field": "mission_statement",
                         "value": "2d BCT attacks at 010500Z to seize OBJ."})
        r = self.admin.post("/api/plans/%d/phase" % pid, {"phase": "production"})
        self.assertGreater(r["sections_created"], 30)
        secs = self.admin.get("/api/plans/%d/sections" % pid)["sections"]
        p2 = [s for s in secs if s["key"] == "p2"][0]
        self.assertIn("seize OBJ", p2["body"])
        self.assertEqual(p2["status"], "drafted")

    def test_unknown_phase_is_rejected(self):
        pid = self.new_plan("BADPHASE")
        with self.assertRaises(HttpFail) as cm:
            self.admin.post("/api/plans/%d/phase" % pid, {"phase": "wombat"})
        self.assertEqual(cm.exception.code, 400)

    def test_unknown_section_status_is_rejected(self):
        pid = self.new_plan("BADSTATUS")
        self.admin.post("/api/plans/%d/phase" % pid, {"phase": "production"})
        with self.assertRaises(HttpFail) as cm:
            self.admin.post("/api/plans/%d/sections/p2" % pid,
                            {"status": "excellent"})
        self.assertEqual(cm.exception.code, 400)


class TestDoctrineApi(ApiCase):
    def test_search_and_stats(self):
        self.admin.post("/api/doctrine/ingest", {})
        st = self.admin.get("/api/doctrine/stats")
        self.assertGreater(st["chunks"], 10)
        hits = self.admin.get("/api/doctrine/search?q=commander+intent")
        self.assertTrue(hits["results"])

    def test_only_admin_can_reindex(self):
        c = self.as_user("planner")
        with self.assertRaises(HttpFail) as cm:
            c.post("/api/doctrine/ingest", {})
        self.assertEqual(cm.exception.code, 403)

    def test_search_with_a_hostile_query_is_safe(self):
        r = self.admin.get("/api/doctrine/search?q=%22%3B+DROP+TABLE+docs%3B--")
        self.assertIsInstance(r["results"], list)
        st = self.admin.get("/api/doctrine/stats")
        self.assertGreaterEqual(st["chunks"], 0)


if __name__ == "__main__":
    unittest.main()
