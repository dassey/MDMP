#!/usr/bin/env python3
"""Index the doctrine corpus from the command line.

    python3 scripts/ingest.py                 # index anything new
    python3 scripts/ingest.py --force         # rebuild every document
    python3 scripts/ingest.py --clear         # empty the index first
    python3 scripts/ingest.py path/to/file.pdf
"""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from harness import db                     # noqa: E402
from harness.rag import index as rag       # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", default=None)
    ap.add_argument("--data", default=os.path.join(ROOT, "data", "mdmp.db"))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--clear", action="store_true")
    args = ap.parse_args()

    db.init(args.data)
    if args.clear:
        rag.clear()
        print("index cleared")

    targets = args.paths or [os.path.join(ROOT, "corpus")]
    results = []
    for t in targets:
        if os.path.isdir(t):
            results += rag.ingest_dir(t, force=args.force)
        elif os.path.isfile(t):
            results.append(rag.ingest_file(t, force=args.force))
        else:
            print("not found: %s" % t)

    for r in results:
        print("  %-10s %-46s %4d passages%s"
              % (r["status"], os.path.basename(r["path"])[:46], r["chunks"],
                 ("  ! " + r["note"]) if r["note"] else ""))
    st = rag.stats()
    print("\n%d document(s), %d passage(s) indexed"
          % (len(st["documents"]), st["chunks"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
