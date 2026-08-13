#!/usr/bin/env python3
"""Add or reset an account from the command line.

    python3 scripts/adduser.py cdr --name "COL Smith" --role commander
    python3 scripts/adduser.py s2 --role staff --section s2
    python3 scripts/adduser.py cdr --reset

Useful when nobody can get into the web interface, or for setting up a machine
before handing it over.
"""

import argparse
import getpass
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from harness import auth, db               # noqa: E402
from harness.mdmp import doctrine as D     # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("username", nargs="?",
                    help="omit only with --list")
    ap.add_argument("--name", default=None, help="display name")
    ap.add_argument("--role", default="planner", choices=auth.ROLES)
    ap.add_argument("--section", default="s3",
                    choices=[k for k, _n, _d in D.STAFF_SECTIONS])
    ap.add_argument("--password", default=None,
                    help="omit to be prompted (safer — it stays out of shell history)")
    ap.add_argument("--reset", action="store_true",
                    help="reset the password of an existing account")
    ap.add_argument("--list", action="store_true", help="list accounts and exit")
    ap.add_argument("--data", default=os.path.join(ROOT, "data", "mdmp.db"))
    args = ap.parse_args()

    db.init(args.data)

    if args.list:
        for u in db.q("SELECT username,display_name,role,staff_section,active "
                      "FROM users ORDER BY username"):
            print("  %-14s %-22s %-10s %-6s %s"
                  % (u["username"], u["display_name"], u["role"],
                     (u["staff_section"] or "").upper(),
                     "" if u["active"] else "(inactive)"))
        return 0

    if not args.username:
        ap.error("a username is required unless you pass --list")

    password = args.password or getpass.getpass("password: ")

    if args.reset:
        row = db.q1("SELECT id FROM users WHERE username=?",
                    (args.username.lower(),))
        if not row:
            print("no such account: %s" % args.username)
            return 1
        auth.set_password(row["id"], password)
        print("password reset for %s" % args.username)
        return 0

    try:
        auth.create_user(args.username, password, args.name, args.role,
                         args.section)
    except ValueError as e:
        print("error: %s" % e)
        return 1
    print("created %s (%s, %s)" % (args.username, args.role,
                                   args.section.upper()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
