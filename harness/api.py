"""HTTP API handlers."""

import json
import os

from harness import auth, db
from harness.agent import engine as agent_engine
from harness.agent import providers
from harness.flow import context_for, dep_hash, flow_state, is_empty
from harness.mdmp import doctrine as D
from harness.mdmp import opord
from harness.mdmp.flow_def import FLOW
from harness.rag import index as rag
from harness.server import (COOKIE, HttpError, json_response, route,
                            text_response)

CORPUS_DIR = None


# ------------------------------------------------------------- session ----

@route("GET", "/api/bootstrap", auth_required=False)
def bootstrap(req):
    return {"needs_setup": auth.user_count() == 0,
            "user": auth.public(req.user),
            "flow": {"id": FLOW.id, "title": FLOW.title}}


@route("POST", "/api/setup", auth_required=False)
def setup(req):
    if auth.user_count() > 0:
        raise HttpError(400, "this server already has accounts")
    data = req.json()
    try:
        uid = auth.create_user(
            data.get("username", ""), data.get("password", ""),
            data.get("display_name"), role="admin",
            staff_section=data.get("staff_section", "s3"))
    except ValueError as e:
        raise HttpError(400, str(e))
    token = auth.start_session(uid)
    return _with_cookie({"user": auth.public(
        db.q1("SELECT * FROM users WHERE id=?", (uid,)))}, token)


@route("POST", "/api/login", auth_required=False)
def login(req):
    data = req.json()
    user = auth.authenticate(data.get("username", ""), data.get("password", ""))
    if not user:
        raise HttpError(401, "wrong username or password")
    token = auth.start_session(user["id"])
    db.log(None, user["id"], "user.login", user["username"])
    return _with_cookie({"user": auth.public(user)}, token)


def _with_cookie(payload, token):
    return json_response(payload, 200, {
        "Set-Cookie": "%s=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=%d"
                      % (COOKIE, token, auth.SESSION_DAYS * 86400)})


@route("POST", "/api/logout")
def logout(req):
    auth.end_session(req.token)
    return json_response({"ok": True}, 200,
                         {"Set-Cookie": "%s=; Path=/; Max-Age=0" % COOKIE})


@route("GET", "/api/me")
def me(req):
    return {"user": auth.public(req.user)}


# --------------------------------------------------------------- users ----

@route("GET", "/api/users")
def list_users(req):
    rows = db.q("SELECT id,username,display_name,role,staff_section,active "
                "FROM users ORDER BY display_name")
    return {"users": rows,
            "roles": auth.ROLES,
            "sections": [{"key": k, "name": n, "desc": d}
                         for k, n, d in D.STAFF_SECTIONS]}


@route("POST", "/api/users")
def add_user(req):
    if req.user["role"] != "admin":
        raise HttpError(403, "only an admin can add accounts")
    data = req.json()
    try:
        uid = auth.create_user(data.get("username", ""),
                               data.get("password", ""),
                               data.get("display_name"),
                               data.get("role", "planner"),
                               data.get("staff_section", "s3"))
    except ValueError as e:
        raise HttpError(400, str(e))
    return {"id": uid}


@route("POST", "/api/users/{uid}/password")
def change_password(req):
    uid = int(req.params["uid"])
    if req.user["role"] != "admin" and req.user["id"] != uid:
        raise HttpError(403, "you can only change your own password")
    try:
        auth.set_password(uid, req.json().get("password", ""))
    except ValueError as e:
        raise HttpError(400, str(e))
    return {"ok": True}


@route("POST", "/api/users/{uid}/deactivate")
def deactivate_user(req):
    if req.user["role"] != "admin":
        raise HttpError(403, "only an admin can deactivate accounts")
    uid = int(req.params["uid"])
    if uid == req.user["id"]:
        raise HttpError(400, "you cannot deactivate your own account")
    db.ex("UPDATE users SET active=0 WHERE id=?", (uid,))
    db.ex("DELETE FROM sessions WHERE user_id=?", (uid,))
    return {"ok": True}


# ---------------------------------------------------------------- flow ----

@route("GET", "/api/flow")
def get_flow(req):
    return {"flow": FLOW.to_dict(),
            "doctrine": {
                "screening": [{"key": k, "name": n, "desc": d}
                              for k, n, d in D.COA_SCREENING_CRITERIA],
                "wargame_methods": [{"name": n, "desc": d, "when": w}
                                    for _k, n, d, w in D.WARGAME_METHODS],
                "risk_probability": D.RISK_PROBABILITY,
                "risk_severity": D.RISK_SEVERITY,
                "warnord": D.WARNORD_CONTENT,
                "sections": [{"key": k, "name": n, "desc": d}
                             for k, n, d in D.STAFF_SECTIONS],
            }}


# --------------------------------------------------------------- plans ----

@route("GET", "/api/plans")
def list_plans(req):
    rows = db.q(
        "SELECT p.*, u.display_name AS owner FROM plans p "
        "JOIN users u ON u.id=p.created_by WHERE p.archived=0 "
        "ORDER BY p.updated_at DESC")
    for r in rows:
        state = _state(r["id"])
        done = sum(1 for s in state["steps"] if s["status"] == "complete")
        r["progress"] = {"complete": done, "total": len(state["steps"])}
    return {"plans": rows}


@route("POST", "/api/plans")
def create_plan(req):
    data = req.json()
    name = (data.get("name") or "").strip()
    if not name:
        raise HttpError(400, "give the plan a name")
    pid = db.ex("INSERT INTO plans(name,flow_id,created_by,created_at,"
                "updated_at,meta_json) VALUES(?,?,?,?,?,?)",
                (name, FLOW.id, req.user["id"], db.now(), db.now(), "{}"))
    db.ex("INSERT INTO plan_members(plan_id,user_id,role) VALUES(?,?,?)",
          (pid, req.user["id"], "planner"))
    db.log(pid, req.user["id"], "plan.created", name)
    return {"id": pid}


def _plan_or_404(plan_id):
    plan = db.q1("SELECT * FROM plans WHERE id=?", (plan_id,))
    if not plan:
        raise HttpError(404, "no such plan")
    return plan


def _answers(plan_id):
    rows = db.q("SELECT field_key, value_json, dep_hash, source, author_id, "
                "created_at FROM answers WHERE plan_id=? AND current=1",
                (plan_id,))
    values, hashes, meta = {}, {}, {}
    for r in rows:
        try:
            values[r["field_key"]] = json.loads(r["value_json"])
        except ValueError:
            values[r["field_key"]] = r["value_json"]
        hashes[r["field_key"]] = r["dep_hash"]
        meta[r["field_key"]] = {"source": r["source"],
                                "author_id": r["author_id"],
                                "at": r["created_at"]}
    return values, hashes, meta


def _state(plan_id):
    values, hashes, _meta = _answers(plan_id)
    return flow_state(FLOW, values, hashes)


@route("GET", "/api/plans/{pid}")
def get_plan(req):
    pid = int(req.params["pid"])
    plan = _plan_or_404(pid)
    values, hashes, meta = _answers(pid)
    role = auth.plan_role(pid, req.user)
    members = db.q(
        "SELECT m.role, u.id, u.display_name, u.staff_section FROM "
        "plan_members m JOIN users u ON u.id=m.user_id WHERE m.plan_id=?",
        (pid,))
    return {"plan": plan, "answers": values, "meta": meta,
            "state": flow_state(FLOW, values, hashes),
            "role": role, "can_plan": auth.can_plan(role),
            "can_approve": auth.can_approve(role),
            "members": members,
            "completeness": opord.completeness(pid),
            "provider": _engine().describe()}


@route("POST", "/api/plans/{pid}/archive")
def archive_plan(req):
    pid = int(req.params["pid"])
    if not auth.can_plan(auth.plan_role(pid, req.user)):
        raise HttpError(403, "you cannot archive this plan")
    db.ex("UPDATE plans SET archived=1, updated_at=? WHERE id=?",
          (db.now(), pid))
    return {"ok": True}


@route("POST", "/api/plans/{pid}/join")
def join_plan(req):
    pid = int(req.params["pid"])
    _plan_or_404(pid)
    role = req.json().get("role", "staff")
    if role not in auth.ROLES:
        role = "staff"
    db.ex("INSERT INTO plan_members(plan_id,user_id,role) VALUES(?,?,?) "
          "ON CONFLICT(plan_id,user_id) DO UPDATE SET role=excluded.role",
          (pid, req.user["id"], role))
    db.log(pid, req.user["id"], "plan.joined", role)
    return {"ok": True}


# ------------------------------------------------------------- options ----

def _engine():
    return agent_engine.Engine(providers.build(
        db.setting("provider"), db.setting("base_url"), db.setting("model"),
        db.setting("api_key")))


@route("POST", "/api/plans/{pid}/options")
def gen_options(req):
    pid = int(req.params["pid"])
    _plan_or_404(pid)
    if not auth.can_plan(auth.plan_role(pid, req.user)):
        raise HttpError(403, "you do not have planning rights on this plan")
    data = req.json()
    field_key = data.get("field")
    field = FLOW.field(field_key)
    if not field:
        raise HttpError(404, "no such field: %s" % field_key)

    values, hashes, _meta = _answers(pid)
    ctx = context_for(FLOW, field, values)
    want = min(int(data.get("n") or 5), 8)
    fresh = bool(data.get("refresh"))
    current_hash = dep_hash(field, values)

    if not fresh:
        cached = db.q1(
            "SELECT * FROM optionsets WHERE plan_id=? AND field_key=? AND "
            "dep_hash=? ORDER BY created_at DESC LIMIT 1",
            (pid, field_key, current_hash))
        if cached:
            return {"options": json.loads(cached["options_json"]),
                    "cached": True, "provider": cached["provider"],
                    "notes": []}

    prior = []
    if field_key.startswith("coa_") and field_key[4:].isdigit():
        for k in ("coa_1", "coa_2", "coa_3"):
            if k != field_key and not is_empty(values.get(k)):
                prior.append(values[k])

    options, meta = _engine().generate(FLOW, field, ctx, want, prior)
    db.ex("INSERT INTO optionsets(plan_id,step_key,field_key,dep_hash,"
          "provider,options_json,created_at) VALUES(?,?,?,?,?,?,?)",
          (pid, FLOW.step_of(field_key).key, field_key, current_hash,
           meta.get("provider", "offline"), json.dumps(options), db.now()))
    return {"options": options, "cached": False,
            "provider": meta.get("provider"), "notes": meta.get("notes", []),
            "passages": meta.get("passages", [])}


@route("POST", "/api/plans/{pid}/answer")
def save_answer(req):
    pid = int(req.params["pid"])
    _plan_or_404(pid)
    if not auth.can_plan(auth.plan_role(pid, req.user)):
        raise HttpError(403, "you do not have planning rights on this plan")
    data = req.json()
    field_key = data.get("field")
    field = FLOW.field(field_key)
    if not field:
        raise HttpError(404, "no such field: %s" % field_key)

    values, _hashes, _meta = _answers(pid)
    value = data.get("value")
    values[field_key] = value
    step = FLOW.step_of(field_key)

    conn = db.connect()
    conn.execute("UPDATE answers SET current=0 WHERE plan_id=? AND "
                 "field_key=? AND current=1", (pid, field_key))
    conn.execute(
        "INSERT INTO answers(plan_id,step_key,field_key,value_json,source,"
        "option_id,dep_hash,author_id,created_at,current) "
        "VALUES(?,?,?,?,?,?,?,?,?,1)",
        (pid, step.key, field_key, json.dumps(value),
         data.get("source", "selected"), data.get("option_id"),
         dep_hash(field, values), req.user["id"], db.now()))
    conn.execute("UPDATE plans SET updated_at=? WHERE id=?", (db.now(), pid))
    conn.commit()
    db.log(pid, req.user["id"], "answer.saved", field.label)

    # Anything downstream of this field may now be stale; the UI paints that
    # from the returned state rather than us deleting the staff's work.
    stale = []
    values2, hashes2, _m = _answers(pid)
    for dep_key in FLOW.dependents_of(field_key):
        dep_field = FLOW.field(dep_key)
        if is_empty(values2.get(dep_key)):
            continue
        if hashes2.get(dep_key) != dep_hash(dep_field, values2):
            stale.append({"field": dep_key, "label": dep_field.label,
                          "step": FLOW.step_of(dep_key).key})
    if plan_phase(pid) == "production":
        opord.ensure_sections(pid)
    return {"ok": True, "state": flow_state(FLOW, values2, hashes2),
            "stale": stale}


def plan_phase(plan_id):
    plan = db.q1("SELECT phase FROM plans WHERE id=?", (plan_id,))
    return plan["phase"] if plan else "planning"


@route("GET", "/api/plans/{pid}/history/{field}")
def answer_history(req):
    pid = int(req.params["pid"])
    rows = db.q(
        "SELECT a.*, u.display_name FROM answers a "
        "LEFT JOIN users u ON u.id=a.author_id "
        "WHERE a.plan_id=? AND a.field_key=? ORDER BY a.created_at DESC "
        "LIMIT 20", (pid, req.params["field"]))
    for r in rows:
        try:
            r["value"] = json.loads(r["value_json"])
        except ValueError:
            r["value"] = r["value_json"]
        del r["value_json"]
    return {"history": rows}


# ------------------------------------------------------------- warnord ----

@route("GET", "/api/plans/{pid}/warnord/{num}")
def warnord(req):
    pid = int(req.params["pid"])
    num = int(req.params["num"])
    values, _h, _m = _answers(pid)
    plan = _plan_or_404(pid)
    items = D.WARNORD_CONTENT.get(num, [])
    mapping = {
        "Restated mission": "mission_statement",
        "Mission": "mission_statement",
        "Commander's intent": "intent_purpose",
        "CCIRs and EEFIs": "ccir_pir",
        "Task organization": "task_organization",
        "Tasks to subordinate units": "tasks_to_subordinates",
        "Updated timeline": "time_available",
        "Initial timeline": "time_available",
        "Type of operation": "operation_type",
        "Risk guidance": "final_guidance",
        "Rehearsal guidance": "rehearsals",
        "Updated timeline and rehearsal plan": "rehearsals",
        "Coordinating instructions": "constraints",
        "Concept of operations sketch": "concept_of_operations",
        "AO / area of interest": "area_of_interest",
    }
    lines = ["WARNING ORDER #%d — %s" % (num, plan["name"]),
             "Issuing headquarters: %s"
             % (values.get("unit_designation") or "(unit)"), ""]
    for item in items:
        lines.append("%s:" % item.upper())
        key = mapping.get(item)
        val = values.get(key) if key else None
        if is_empty(val):
            lines.append("    (to be determined)")
        elif isinstance(val, list):
            for v in val[:8]:
                if isinstance(v, list):
                    lines.append("    " + " | ".join(str(c) for c in v))
                else:
                    lines.append("    - %s" % v)
        else:
            for para in str(val).split("\n"):
                lines.append("    %s" % para)
        lines.append("")
    lines.append("ACKNOWLEDGE.")
    return text_response("\n".join(lines))


# --------------------------------------------------------------- OPORD ----

@route("POST", "/api/plans/{pid}/phase")
def set_phase(req):
    pid = int(req.params["pid"])
    _plan_or_404(pid)
    if not auth.can_plan(auth.plan_role(pid, req.user)):
        raise HttpError(403, "you cannot change the plan phase")
    phase = req.json().get("phase", "production")
    if phase not in ("planning", "production", "published"):
        raise HttpError(400, "unknown phase")
    db.ex("UPDATE plans SET phase=?, updated_at=? WHERE id=?",
          (phase, db.now(), pid))
    created = 0
    if phase in ("production", "published"):
        created = opord.ensure_sections(pid)
    db.log(pid, req.user["id"], "plan.phase", phase)
    return {"ok": True, "phase": phase, "sections_created": created}


@route("GET", "/api/plans/{pid}/sections")
def get_sections(req):
    pid = int(req.params["pid"])
    _plan_or_404(pid)
    opord.ensure_sections(pid)
    rows = opord.sections(pid)
    guidance = {n["key"]: n["guidance"] for n in D.OPORD_SKELETON}
    for r in rows:
        r["guidance"] = guidance.get(r["key"], "")
        r["owner_hint_name"] = D.staff_section_name(r["owner_hint"])
    return {"sections": rows, "completeness": opord.completeness(pid),
            "phase": plan_phase(pid)}


@route("POST", "/api/plans/{pid}/sections/{key}")
def update_section(req):
    pid = int(req.params["pid"])
    key = req.params["key"]
    _plan_or_404(pid)
    role = auth.plan_role(pid, req.user)
    if not auth.can_edit_section(role):
        raise HttpError(403, "you cannot edit this order")
    row = db.q1("SELECT * FROM sections WHERE plan_id=? AND key=?", (pid, key))
    if not row:
        raise HttpError(404, "no such section")
    data = req.json()
    fields, args = [], []
    if "body" in data:
        fields.append("body=?")
        args.append(data["body"])
    if "status" in data:
        status = data["status"]
        if status not in ("not_started", "drafted", "in_progress",
                          "ready_for_review", "approved"):
            raise HttpError(400, "unknown status")
        if status == "approved" and not auth.can_approve(role):
            raise HttpError(403, "only the commander or an admin approves "
                                 "paragraphs")
        fields.append("status=?")
        args.append(status)
    if "owner_id" in data:
        fields.append("owner_id=?")
        args.append(data["owner_id"] or None)
    if not fields:
        return {"ok": True}
    fields += ["updated_by=?", "updated_at=?"]
    args += [req.user["id"], db.now(), row["id"]]
    db.ex("UPDATE sections SET %s WHERE id=?" % ", ".join(fields), tuple(args))
    db.ex("UPDATE plans SET updated_at=? WHERE id=?", (db.now(), pid))
    db.log(pid, req.user["id"], "section.updated",
           "%s → %s" % (row["title"], data.get("status", "edited")))
    return {"ok": True}


@route("POST", "/api/plans/{pid}/sections/{key}/claim")
def claim_section(req):
    pid = int(req.params["pid"])
    key = req.params["key"]
    row = db.q1("SELECT * FROM sections WHERE plan_id=? AND key=?", (pid, key))
    if not row:
        raise HttpError(404, "no such section")
    db.ex("UPDATE sections SET owner_id=?, status=CASE WHEN status="
          "'not_started' THEN 'in_progress' ELSE status END, updated_at=? "
          "WHERE id=?", (req.user["id"], db.now(), row["id"]))
    db.log(pid, req.user["id"], "section.claimed", row["title"])
    return {"ok": True}


@route("GET", "/api/plans/{pid}/opord")
def get_opord(req):
    pid = int(req.params["pid"])
    _plan_or_404(pid)
    doc, annexes = opord.build_document(pid)
    return {"document": doc, "annexes": annexes,
            "completeness": opord.completeness(pid)}


@route("GET", "/api/plans/{pid}/export")
def export(req):
    pid = int(req.params["pid"])
    plan = _plan_or_404(pid)
    fmt = (req.arg("format") or "md").lower()
    safe = "".join(c if c.isalnum() or c in "-_" else "_"
                   for c in plan["name"])[:60] or "opord"
    if fmt in ("md", "markdown"):
        return text_response(opord.render_markdown(pid),
                             content_type="text/markdown; charset=utf-8",
                             filename="%s_OPORD.md" % safe)
    if fmt == "txt":
        return text_response(opord.render_text(pid),
                             filename="%s_OPORD.txt" % safe)
    if fmt == "html":
        return text_response(opord.render_html(pid),
                             content_type="text/html; charset=utf-8")
    if fmt == "docx":
        return text_response(
            opord.render_docx(pid),
            content_type="application/vnd.openxmlformats-officedocument."
                         "wordprocessingml.document",
            filename="%s_OPORD.docx" % safe)
    if fmt == "json":
        values, _h, meta = _answers(pid)
        doc, annexes = opord.build_document(pid)
        payload = {"plan": plan, "answers": values, "meta": meta,
                   "document": doc, "annexes": annexes}
        return text_response(json.dumps(payload, indent=2, default=str),
                             content_type="application/json; charset=utf-8",
                             filename="%s_plan.json" % safe)
    raise HttpError(400, "unknown export format")


# ------------------------------------------------------------ activity ----

@route("GET", "/api/plans/{pid}/pulse")
def pulse(req):
    pid = int(req.params["pid"])
    since = req.int_arg("since", 0)
    rows = db.q(
        "SELECT a.id, a.ts, a.kind, a.detail, u.display_name FROM activity a "
        "LEFT JOIN users u ON u.id=a.user_id "
        "WHERE a.plan_id=? AND a.id > ? ORDER BY a.id DESC LIMIT 40",
        (pid, since))
    online = db.q(
        "SELECT DISTINCT u.display_name, u.staff_section FROM sessions s "
        "JOIN users u ON u.id=s.user_id WHERE s.last_seen > ?",
        (db.now() - 300,))
    plan = db.q1("SELECT updated_at, phase FROM plans WHERE id=?", (pid,))
    return {"activity": rows, "online": online,
            "last_id": rows[0]["id"] if rows else since,
            "updated_at": plan["updated_at"] if plan else 0,
            "phase": plan["phase"] if plan else "planning"}


# ------------------------------------------------------------ doctrine ----

@route("GET", "/api/doctrine/search")
def doctrine_search(req):
    q = req.arg("q", "")
    return {"results": rag.search(q, limit=req.int_arg("limit", 8))}


@route("GET", "/api/doctrine/stats")
def doctrine_stats(req):
    st = rag.stats()
    st["corpus_dir"] = CORPUS_DIR
    return st


@route("POST", "/api/doctrine/ingest")
def doctrine_ingest(req):
    if req.user["role"] != "admin":
        raise HttpError(403, "only an admin can rebuild the doctrine index")
    force = bool(req.json().get("force"))
    if not CORPUS_DIR or not os.path.isdir(CORPUS_DIR):
        raise HttpError(400, "corpus directory not found")
    results = rag.ingest_dir(CORPUS_DIR, force=force)
    return {"results": results, "stats": rag.stats()}


# ----------------------------------------------------------- providers ----

@route("GET", "/api/providers")
def get_providers(req):
    return {"detected": providers.detect(),
            "current": {"provider": db.setting("provider", "offline"),
                        "model": db.setting("model", ""),
                        "base_url": db.setting("base_url", ""),
                        "has_key": bool(db.setting("api_key")
                                        or os.environ.get("ANTHROPIC_API_KEY"))},
            "describe": _engine().describe()}


@route("POST", "/api/providers")
def set_provider(req):
    if req.user["role"] != "admin":
        raise HttpError(403, "only an admin can change the model provider")
    data = req.json()
    for key in ("provider", "model", "base_url"):
        if key in data:
            db.set_setting(key, data[key])
    if data.get("api_key"):
        db.set_setting("api_key", data["api_key"])
    if data.get("clear_api_key"):
        db.set_setting("api_key", "")
    eng = _engine()
    ok = eng.provider.available()
    return {"ok": True, "describe": eng.describe(), "available": ok}
