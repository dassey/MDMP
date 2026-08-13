#!/usr/bin/env python3
"""End-to-end smoke test.

Starts a real server on a throwaway database, then drives the whole thing over
HTTP exactly as a browser would: create the admin, add a second user, start a
plan, answer all 66 fields from generated options, move to production, edit and
approve a paragraph, and export the order in every format.

    python3 scripts/smoke_test.py

Exit code 0 means the tool works end to end with no model and no network.
"""

import json
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

FAILURES = []


def check(label, cond, detail=""):
    mark = "ok  " if cond else "FAIL"
    print("  [%s] %s%s" % (mark, label, (" — " + str(detail)) if detail and not cond else ""))
    if not cond:
        FAILURES.append(label)
    return cond


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
                setcookie = resp.headers.get("Set-Cookie")
                if setcookie:
                    self.cookie = setcookie.split(";")[0]
                payload = resp.read()
                if raw:
                    return payload
                return json.loads(payload.decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            raise AssertionError("%s %s -> %s %s" % (method, path, e.code, body))

    get = lambda self, p, raw=False: self.call("GET", p, None, raw)
    post = lambda self, p, b=None: self.call("POST", p, b or {})


def main():
    tmp = tempfile.mkdtemp(prefix="mdmp-smoke-")
    port = 8099
    os.environ["MDMP_QUIET"] = "1"

    from harness import api, db, server
    import harness.api  # noqa: F401  (registers routes)

    db.init(os.path.join(tmp, "test.db"))
    api.CORPUS_DIR = os.path.join(ROOT, "corpus")

    from harness.rag import index as rag
    if os.path.isdir(api.CORPUS_DIR):
        rag.ingest_dir(api.CORPUS_DIR)

    httpd = server.serve("127.0.0.1", port, static_dir=os.path.join(ROOT, "static"))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    time.sleep(0.4)

    try:
        run(Client("http://127.0.0.1:%d" % port), tmp)
    finally:
        httpd.shutdown()
        httpd.server_close()
        shutil.rmtree(tmp, ignore_errors=True)

    print("")
    if FAILURES:
        print("  %d FAILURE(S): %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("  all checks passed")
    return 0


def run(c, tmp):
    print("\n-- setup ---------------------------------------------------")
    boot = c.get("/api/bootstrap")
    check("fresh server needs setup", boot["needs_setup"] is True)

    r = c.post("/api/setup", {"username": "cdr", "password": "testpass",
                              "display_name": "COL Smoke"})
    check("admin account created", r["user"]["role"] == "admin")

    r = c.post("/api/users", {"username": "s3", "password": "testpass",
                              "display_name": "MAJ Ops", "role": "planner",
                              "staff_section": "s3"})
    check("second account created", "id" in r)

    print("\n-- flow ----------------------------------------------------")
    f = c.get("/api/flow")
    flow = f["flow"]
    n_fields = sum(len(s["fields"]) for s in flow["steps"])
    check("flow has 7 steps", len(flow["steps"]) == 7, len(flow["steps"]))
    check("flow has fields", n_fields > 50, n_fields)

    print("\n-- plan ----------------------------------------------------")
    plan = c.post("/api/plans", {"name": "OPERATION SMOKE TEST"})
    pid = plan["id"]
    check("plan created", pid > 0)

    print("\n-- answering every field from generated options ------------")
    t0 = time.time()
    answered, table_fields, item_fields = 0, 0, 0
    for step in flow["steps"]:
        for fd in step["fields"]:
            res = c.post("/api/plans/%d/options" % pid, {"field": fd["key"], "n": 5})
            opts = res["options"]
            if not opts:
                check("options for %s" % fd["key"], False, "none returned")
                continue
            usable = [o for o in opts
                      if not (isinstance(o["value"], str) and not o["value"].strip())]
            if not usable:
                check("usable option for %s" % fd["key"], False)
                continue
            if fd["kind"] in ("items", "multi"):
                value = [o["value"] for o in usable[:3]]
                item_fields += 1
            elif fd["kind"] == "table":
                value = [o["value"] if isinstance(o["value"], list)
                         else [o["value"]] for o in usable[:4]]
                table_fields += 1
            else:
                value = usable[0]["value"]
            c.post("/api/plans/%d/answer" % pid,
                   {"field": fd["key"], "value": value, "source": "selected"})
            answered += 1
    dt = time.time() - t0
    check("answered every field (%d)" % answered, answered == n_fields, answered)
    check("list fields exercised", item_fields > 8, item_fields)
    check("table fields exercised", table_fields > 5, table_fields)
    print("       %d fields generated + answered in %.1fs (%.0f ms each)"
          % (answered, dt, 1000 * dt / max(answered, 1)))

    st = c.get("/api/plans/%d" % pid)
    complete = [s for s in st["state"]["steps"] if s["status"] == "complete"]
    check("all 7 steps complete", len(complete) == 7,
          [s["key"] + ":" + s["status"] for s in st["state"]["steps"]])

    print("\n-- dependency / staleness ----------------------------------")
    r = c.post("/api/plans/%d/answer" % pid,
               {"field": "operation_type", "value": "Defensive Operation: Area Defense",
                "source": "written"})
    check("changing an upstream answer marks dependents stale",
          len(r["stale"]) > 3, len(r["stale"]))
    stale_steps = [s for s in r["state"]["steps"] if s["status"] == "stale"]
    check("step rail shows the stale steps", len(stale_steps) >= 1,
          len(stale_steps))
    hist = c.get("/api/plans/%d/history/operation_type" % pid)
    check("answer history kept", len(hist["history"]) >= 2, len(hist["history"]))

    print("\n-- warning orders ------------------------------------------")
    for n in (1, 2, 3):
        text = c.get("/api/plans/%d/warnord/%d" % (pid, n), raw=True).decode()
        check("WARNORD #%d generated" % n,
              "WARNING ORDER #%d" % n in text and len(text) > 200, len(text))

    print("\n-- staff production ----------------------------------------")
    r = c.post("/api/plans/%d/phase" % pid, {"phase": "production"})
    check("moved to production", r["phase"] == "production")
    secs = c.get("/api/plans/%d/sections" % pid)
    paras = [s for s in secs["sections"] if s["kind"] == "paragraph"]
    drafted = [s for s in paras if s["body"].strip()]
    check("OPORD paragraphs materialised", len(paras) >= 25, len(paras))
    check("most paragraphs pre-drafted from the plan",
          len(drafted) >= 15, "%d of %d" % (len(drafted), len(paras)))
    check("annexes listed",
          len([s for s in secs["sections"] if s["kind"] == "annex"]) >= 15)

    c.post("/api/plans/%d/sections/p2/claim" % pid)
    c.post("/api/plans/%d/sections/p2" % pid,
           {"body": "2. MISSION. Edited by the smoke test.",
            "status": "ready_for_review"})
    c.post("/api/plans/%d/sections/p2" % pid, {"status": "approved"})
    secs = c.get("/api/plans/%d/sections" % pid)
    p2 = [s for s in secs["sections"] if s["key"] == "p2"][0]
    check("paragraph edited, claimed, and approved",
          p2["status"] == "approved" and "smoke test" in p2["body"],
          p2["status"])

    print("\n-- a second user picks up a paragraph ----------------------")
    c2 = Client(c.base)
    c2.post("/api/login", {"username": "s3", "password": "testpass"})
    c2.post("/api/plans/%d/join" % pid, {"role": "staff"})
    c2.post("/api/plans/%d/sections/p4/claim" % pid)
    c2.post("/api/plans/%d/sections/p4" % pid,
            {"body": "4. SUSTAINMENT. Written by the S-3 account.",
             "status": "ready_for_review"})
    secs = c.get("/api/plans/%d/sections" % pid)
    p4 = [s for s in secs["sections"] if s["key"] == "p4"][0]
    check("second user owns and edited their paragraph",
          p4["owner_name"] == "MAJ Ops", p4["owner_name"])
    try:
        c2.post("/api/plans/%d/sections/p4" % pid, {"status": "approved"})
        check("staff cannot approve a paragraph", False, "no error raised")
    except AssertionError as e:
        check("staff cannot approve a paragraph", "403" in str(e), str(e)[:80])

    pulse = c.get("/api/plans/%d/pulse?since=0" % pid)
    check("activity feed populated", len(pulse["activity"]) > 3,
          len(pulse["activity"]))
    check("presence shows both users online", len(pulse["online"]) == 2,
          len(pulse["online"]))

    print("\n-- export --------------------------------------------------")
    md = c.get("/api/plans/%d/export?format=md" % pid, raw=True).decode()
    check("markdown export", "# Operation Order" in md and len(md) > 2000, len(md))
    txt = c.get("/api/plans/%d/export?format=txt" % pid, raw=True).decode()
    check("plain text export", "OPERATION ORDER" in txt, len(txt))
    html = c.get("/api/plans/%d/export?format=html" % pid, raw=True).decode()
    check("html export", "<html>" in html and "Operation Order" in html, len(html))
    docx = c.get("/api/plans/%d/export?format=docx" % pid, raw=True)
    check("docx export is a valid zip", docx[:2] == b"PK" and len(docx) > 3000,
          len(docx))
    import zipfile
    import io
    with zipfile.ZipFile(io.BytesIO(docx)) as z:
        names = z.namelist()
        check("docx contains document.xml", "word/document.xml" in names, names)
        body = z.read("word/document.xml").decode()
        check("docx has the order text", "MISSION" in body.upper(), len(body))
    data = json.loads(c.get("/api/plans/%d/export?format=json" % pid, raw=True))
    check("json export has answers and document",
          len(data["answers"]) > 50 and len(data["document"]) > 20)

    for section in ("1. SITUATION", "2. MISSION", "3. EXECUTION",
                    "4. SUSTAINMENT", "5. COMMAND AND SIGNAL"):
        check("order contains %s" % section, section.lower() in txt.lower())

    print("\n-- doctrine retrieval --------------------------------------")
    stats = c.get("/api/doctrine/stats")
    check("doctrine corpus indexed", stats["chunks"] > 20, stats["chunks"])
    hits = c.get("/api/doctrine/search?q=commander%20intent%20key%20tasks")
    check("doctrine search returns passages", len(hits["results"]) > 0,
          len(hits["results"]))

    print("\n-- providers -----------------------------------------------")
    prov = c.get("/api/providers")
    names = [d["name"] for d in prov["detected"]]
    check("all four providers listed", set(names) ==
          {"offline", "ollama", "openai", "anthropic"}, names)
    check("offline provider is always available",
          [d for d in prov["detected"] if d["name"] == "offline"][0]["available"])

    print("\n-- auth ----------------------------------------------------")
    anon = Client(c.base)
    try:
        anon.get("/api/plans")
        check("unauthenticated request is rejected", False, "no error raised")
    except AssertionError as e:
        check("unauthenticated request is rejected", "401" in str(e), str(e)[:60])
    try:
        anon.post("/api/setup", {"username": "x", "password": "yyyyyy"})
        check("setup blocked once accounts exist", False, "no error raised")
    except AssertionError as e:
        check("setup blocked once accounts exist", "400" in str(e), str(e)[:60])


if __name__ == "__main__":
    sys.exit(main())
