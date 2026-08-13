"""Accounts, passwords, sessions, and permissions."""

import unittest

from tests.base import DbCase

from harness import auth, db


class TestPasswords(unittest.TestCase):
    def test_hash_verifies(self):
        h, salt = auth.hash_password("correct horse")
        self.assertTrue(auth.verify_password("correct horse", h, salt))
        self.assertFalse(auth.verify_password("wrong horse", h, salt))

    def test_same_password_hashes_differently(self):
        h1, s1 = auth.hash_password("same")
        h2, s2 = auth.hash_password("same")
        self.assertNotEqual(s1, s2)
        self.assertNotEqual(h1, h2)

    def test_password_is_never_stored_in_the_clear(self):
        h, salt = auth.hash_password("plaintextpassword")
        self.assertNotIn("plaintextpassword", h)
        self.assertNotIn("plaintextpassword", salt)

    def test_verify_handles_garbage_without_raising(self):
        self.assertFalse(auth.verify_password("x", "", ""))
        self.assertFalse(auth.verify_password("", "abc", "def"))


class TestAccounts(DbCase):
    def test_created_in_setup(self):
        self.assertEqual(auth.user_count(), 1)

    def test_usernames_are_lowercased_and_unique(self):
        auth.create_user("MixedCase", "testpass")
        self.assertTrue(db.q1("SELECT 1 FROM users WHERE username='mixedcase'"))
        with self.assertRaises(ValueError):
            auth.create_user("mixedcase", "testpass")

    def test_short_passwords_are_rejected(self):
        with self.assertRaises(ValueError):
            auth.create_user("bob", "12345")
        with self.assertRaises(ValueError):
            auth.set_password(self.uid, "123")

    def test_blank_username_is_rejected(self):
        with self.assertRaises(ValueError):
            auth.create_user("   ", "testpass")

    def test_unknown_role_is_rejected(self):
        with self.assertRaises(ValueError):
            auth.create_user("bob", "testpass", role="field-marshal")

    def test_authenticate(self):
        auth.create_user("s3", "hunter22", "MAJ Ops", "planner")
        self.assertIsNotNone(auth.authenticate("s3", "hunter22"))
        self.assertIsNotNone(auth.authenticate("S3", "hunter22"))  # case
        self.assertIsNone(auth.authenticate("s3", "wrong"))
        self.assertIsNone(auth.authenticate("nobody", "hunter22"))

    def test_deactivated_account_cannot_authenticate(self):
        uid = auth.create_user("gone", "testpass")
        db.ex("UPDATE users SET active=0 WHERE id=?", (uid,))
        self.assertIsNone(auth.authenticate("gone", "testpass"))

    def test_password_change_invalidates_the_old_one(self):
        auth.create_user("bob", "oldpass1")
        uid = db.q1("SELECT id FROM users WHERE username='bob'")["id"]
        auth.set_password(uid, "newpass1")
        self.assertIsNone(auth.authenticate("bob", "oldpass1"))
        self.assertIsNotNone(auth.authenticate("bob", "newpass1"))

    def test_public_view_hides_the_hash(self):
        row = db.q1("SELECT * FROM users WHERE id=?", (self.uid,))
        pub = auth.public(row)
        self.assertNotIn("pw_hash", pub)
        self.assertNotIn("pw_salt", pub)
        self.assertIsNone(auth.public(None))


class TestSessions(DbCase):
    def test_round_trip(self):
        token = auth.start_session(self.uid)
        self.assertEqual(auth.user_for_token(token)["id"], self.uid)

    def test_unknown_and_empty_tokens(self):
        self.assertIsNone(auth.user_for_token("nope"))
        self.assertIsNone(auth.user_for_token(""))
        self.assertIsNone(auth.user_for_token(None))

    def test_tokens_are_long_and_unique(self):
        tokens = {auth.start_session(self.uid) for _ in range(20)}
        self.assertEqual(len(tokens), 20)
        for t in tokens:
            self.assertGreaterEqual(len(t), 32)

    def test_expired_session_is_rejected(self):
        token = auth.start_session(self.uid)
        db.ex("UPDATE sessions SET expires_at=? WHERE token=?",
              (db.now() - 10, token))
        self.assertIsNone(auth.user_for_token(token))

    def test_logout_removes_the_session(self):
        token = auth.start_session(self.uid)
        auth.end_session(token)
        self.assertIsNone(auth.user_for_token(token))

    def test_deactivating_a_user_kills_their_sessions(self):
        uid = auth.create_user("temp", "testpass")
        token = auth.start_session(uid)
        db.ex("UPDATE users SET active=0 WHERE id=?", (uid,))
        self.assertIsNone(auth.user_for_token(token))

    def test_last_seen_is_touched_on_use(self):
        token = auth.start_session(self.uid)
        db.ex("UPDATE sessions SET last_seen=0 WHERE token=?", (token,))
        auth.user_for_token(token)
        row = db.q1("SELECT last_seen FROM sessions WHERE token=?", (token,))
        self.assertGreater(row["last_seen"], 0)


class TestPermissions(DbCase):
    def setUp(self):
        super().setUp()
        self.pid = self.make_plan()
        self.roles = {}
        for role in ("commander", "planner", "staff", "observer"):
            uid = auth.create_user(role, "testpass", role.title(), role)
            self.roles[role] = db.q1("SELECT * FROM users WHERE id=?", (uid,))
        self.admin = db.q1("SELECT * FROM users WHERE id=?", (self.uid,))

    def test_admin_is_admin_everywhere(self):
        self.assertEqual(auth.plan_role(self.pid, self.admin), "admin")

    def test_plan_owner_is_a_planner(self):
        # The admin created the plan; another user gets the default.
        self.assertEqual(auth.plan_role(self.pid, self.roles["staff"]), "staff")

    def test_membership_role_is_honoured(self):
        db.ex("INSERT INTO plan_members(plan_id,user_id,role) VALUES(?,?,?)",
              (self.pid, self.roles["commander"]["id"], "commander"))
        self.assertEqual(auth.plan_role(self.pid, self.roles["commander"]),
                         "commander")

    def test_no_user_has_no_role(self):
        self.assertIsNone(auth.plan_role(self.pid, None))

    def test_capability_matrix(self):
        expect = {
            #            can_plan  can_edit_section  can_approve
            "admin":     (True,    True,             True),
            "commander": (True,    True,             True),
            "planner":   (True,    True,             False),
            "staff":     (False,   True,             False),
            "observer":  (False,   False,            False),
        }
        for role, (plan, edit, approve) in expect.items():
            self.assertEqual(auth.can_plan(role), plan, role)
            self.assertEqual(auth.can_edit_section(role), edit, role)
            self.assertEqual(auth.can_approve(role), approve, role)

    def test_unknown_role_can_do_nothing(self):
        self.assertFalse(auth.can_plan("intruder"))
        self.assertFalse(auth.can_edit_section("intruder"))
        self.assertFalse(auth.can_approve("intruder"))


if __name__ == "__main__":
    unittest.main()
