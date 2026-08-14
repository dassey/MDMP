#!/usr/bin/env python3
"""MDMP harness — start the server.

    python3 serve.py                 # http://0.0.0.0:8080, reachable on the LAN
    python3 serve.py --port 9000
    python3 serve.py --host 127.0.0.1 --no-lan

Nothing to install. Python 3.9 or newer is the only requirement.
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from harness import api, auth, db, server  # noqa: E402
from harness.rag import index as rag  # noqa: E402

BANNER = r"""
   __  __ ___  __  __ ___
  |  \/  |   \|  \/  | _ \    Military Decision-Making Process
  | |\/| | |) | |\/| |  _/    planning harness  ->  five-paragraph OPORD
  |_|  |_|___/|_|  |_|_|
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="0.0.0.0",
                    help="interface to bind (default 0.0.0.0 — reachable from "
                         "other laptops on the network)")
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("MDMP_PORT", 8080)))
    ap.add_argument("--data", default=os.environ.get(
        "MDMP_DATA", os.path.join(HERE, "data", "mdmp.db")),
        help="path to the database file")
    ap.add_argument("--corpus", default=os.environ.get(
        "MDMP_CORPUS", os.path.join(HERE, "corpus")),
        help="directory of doctrine documents to index")
    ap.add_argument("--no-ingest", action="store_true",
                    help="skip the corpus check at startup")
    ap.add_argument("--reindex", action="store_true",
                    help="rebuild the doctrine index from scratch")
    args = ap.parse_args(argv)

    print(BANNER)
    db.init(args.data)
    print("  database   %s" % db.path())

    api.CORPUS_DIR = os.path.abspath(args.corpus)
    if not args.no_ingest and os.path.isdir(api.CORPUS_DIR):
        if args.reindex:
            rag.clear()
        stats = rag.stats()
        if stats["chunks"] == 0 or args.reindex:
            print("  indexing   %s" % api.CORPUS_DIR)
            results = rag.ingest_dir(api.CORPUS_DIR, force=args.reindex)
            indexed = [r for r in results if r["status"] == "indexed"]
            for r in results:
                if r["note"]:
                    print("             ! %s — %s"
                          % (os.path.basename(r["path"]), r["note"]))
            print("             %d document(s), %d passage(s)"
                  % (len(indexed), sum(r["chunks"] for r in indexed)))
        else:
            print("  doctrine   %d passage(s) from %d document(s)"
                  % (stats["chunks"], len(stats["documents"])))

    created = auth.bootstrap_admin_from_env()
    if created:
        print("  account    created admin '%s' from the environment" % created)

    provider = db.setting("provider", "offline")
    print("  provider   %s" % provider)
    if auth.user_count() == 0:
        print("  setup      no accounts yet — the first person to open the "
              "page creates the admin account")

    httpd = server.serve(args.host, args.port,
                         static_dir=os.path.join(HERE, "static"))
    print("")
    print("  Open on this machine:   http://localhost:%d" % args.port)
    if args.host == "0.0.0.0":
        addrs = server.local_addresses()
        if addrs:
            print("  Others on the network:  " + "\n                          "
                  .join("http://%s:%d" % (a, args.port) for a in addrs))
        else:
            print("  Others on the network:  http://<this machine's IP>:%d"
                  % args.port)
    print("")
    print("  Ctrl-C to stop.")
    print("")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopping...")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
