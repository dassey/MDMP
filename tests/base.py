"""Shared test scaffolding.

Every test case gets its own temporary database so nothing leaks between them.
"""

import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from harness import auth, db  # noqa: E402


class DbCase(unittest.TestCase):
    """A test case with a fresh SQLite database and one admin account."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mdmp-test-")
        db._LOCAL.__dict__.pop("conn", None)
        db.init(os.path.join(self.tmp, "t.db"))
        self.uid = auth.create_user("tester", "testpass", "Tester", "admin")

    def tearDown(self):
        conn = getattr(db._LOCAL, "conn", None)
        if conn:
            conn.close()
            db._LOCAL.__dict__.pop("conn", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make_plan(self, name="TEST PLAN"):
        from harness.mdmp.flow_def import FLOW
        pid = db.ex(
            "INSERT INTO plans(name,flow_id,created_by,created_at,updated_at,"
            "meta_json) VALUES(?,?,?,?,?,?)",
            (name, FLOW.id, self.uid, db.now(), db.now(), "{}"))
        db.ex("INSERT INTO plan_members(plan_id,user_id,role) VALUES(?,?,?)",
              (pid, self.uid, "planner"))
        return pid

    def answer(self, pid, field_key, value):
        """Save an answer the way the API does, so dep hashes stay honest."""
        import json
        from harness.flow import dep_hash
        from harness.mdmp.flow_def import FLOW
        values = self.answers(pid)
        values[field_key] = value
        field = FLOW.field(field_key)
        db.ex("UPDATE answers SET current=0 WHERE plan_id=? AND field_key=? "
              "AND current=1", (pid, field_key))
        db.ex("INSERT INTO answers(plan_id,step_key,field_key,value_json,"
              "source,dep_hash,author_id,created_at,current) "
              "VALUES(?,?,?,?,?,?,?,?,1)",
              (pid, FLOW.step_of(field_key).key, field_key, json.dumps(value),
               "selected", dep_hash(field, values), self.uid, db.now()))

    def answers(self, pid):
        import json
        out = {}
        for r in db.q("SELECT field_key, value_json FROM answers "
                      "WHERE plan_id=? AND current=1", (pid,)):
            out[r["field_key"]] = json.loads(r["value_json"])
        return out

    def hashes(self, pid):
        return {r["field_key"]: r["dep_hash"] for r in
                db.q("SELECT field_key, dep_hash FROM answers "
                     "WHERE plan_id=? AND current=1", (pid,))}
