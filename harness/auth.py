"""Accounts, passwords, and sessions.

Local accounts only. This runs on a laptop on a closed network; there is no
directory service to talk to and no third-party identity provider to depend on.
Passwords are hashed with scrypt from the standard library.

Roles
-----
admin      manage users and settings; everything below
commander  approve the plan, own the intent, approve OPORD paragraphs
planner    drive the seven steps and edit any field
staff      edit the OPORD paragraphs and annexes assigned to them
observer   read only
"""

import hashlib
import hmac
import os
import secrets

from harness import db

ROLES = ["admin", "commander", "planner", "staff", "observer"]
SESSION_DAYS = 30

_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt.encode("utf-8"),
                        **_SCRYPT)
    return dk.hex(), salt


def verify_password(password, pw_hash, salt):
    try:
        calc, _ = hash_password(password, salt)
    except Exception:
        return False
    return hmac.compare_digest(calc, pw_hash)


def user_count():
    row = db.q1("SELECT COUNT(*) AS n FROM users WHERE active=1")
    return row["n"] if row else 0


def create_user(username, password, display_name=None, role="planner",
                staff_section="s3"):
    username = (username or "").strip().lower()
    if not username:
        raise ValueError("username required")
    if len(password or "") < 6:
        raise ValueError("password must be at least 6 characters")
    if role not in ROLES:
        raise ValueError("unknown role: %s" % role)
    if db.q1("SELECT id FROM users WHERE username=?", (username,)):
        raise ValueError("that username is taken")
    pw_hash, salt = hash_password(password)
    uid = db.ex(
        "INSERT INTO users(username,display_name,pw_hash,pw_salt,role,"
        "staff_section,active,created_at) VALUES(?,?,?,?,?,?,1,?)",
        (username, display_name or username.title(), pw_hash, salt, role,
         staff_section, db.now()))
    db.log(None, uid, "user.created", "%s (%s)" % (username, role))
    return uid


def set_password(user_id, password):
    if len(password or "") < 6:
        raise ValueError("password must be at least 6 characters")
    pw_hash, salt = hash_password(password)
    db.ex("UPDATE users SET pw_hash=?, pw_salt=? WHERE id=?",
          (pw_hash, salt, user_id))


def authenticate(username, password):
    row = db.q1("SELECT * FROM users WHERE username=? AND active=1",
                ((username or "").strip().lower(),))
    if not row:
        return None
    if not verify_password(password, row["pw_hash"], row["pw_salt"]):
        return None
    return row


def start_session(user_id):
    token = secrets.token_urlsafe(32)
    now = db.now()
    db.ex("INSERT INTO sessions(token,user_id,created_at,expires_at,last_seen) "
          "VALUES(?,?,?,?,?)",
          (token, user_id, now, now + SESSION_DAYS * 86400, now))
    return token


def user_for_token(token):
    if not token:
        return None
    row = db.q1(
        "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id "
        "WHERE s.token=? AND s.expires_at > ? AND u.active=1",
        (token, db.now()))
    if row:
        db.ex("UPDATE sessions SET last_seen=? WHERE token=?",
              (db.now(), token))
    return row


def end_session(token):
    if token:
        db.ex("DELETE FROM sessions WHERE token=?", (token,))


def public(user):
    if not user:
        return None
    return {"id": user["id"], "username": user["username"],
            "display_name": user["display_name"], "role": user["role"],
            "staff_section": user["staff_section"]}


# ------------------------------------------------------------ permissions --

def plan_role(plan_id, user):
    """Effective role of a user on a plan."""
    if not user:
        return None
    if user["role"] == "admin":
        return "admin"
    row = db.q1("SELECT role FROM plan_members WHERE plan_id=? AND user_id=?",
                (plan_id, user["id"]))
    if row:
        return row["role"]
    plan = db.q1("SELECT created_by FROM plans WHERE id=?", (plan_id,))
    if plan and plan["created_by"] == user["id"]:
        return "planner"
    # Anyone with an account on this server can read a plan and pick up an
    # unassigned paragraph; a closed network of staff officers is the whole
    # point of the tool.
    return "staff"


def can_plan(role):
    return role in ("admin", "commander", "planner")


def can_edit_section(role):
    return role in ("admin", "commander", "planner", "staff")


def can_approve(role):
    return role in ("admin", "commander")


def bootstrap_admin_from_env():
    """Create the first account from the environment, if asked to."""
    username = os.environ.get("MDMP_ADMIN_USER")
    password = os.environ.get("MDMP_ADMIN_PASSWORD")
    if username and password and user_count() == 0:
        create_user(username, password, display_name=username.title(),
                    role="admin", staff_section="s3")
        return username
    return None
