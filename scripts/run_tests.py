#!/usr/bin/env python3
"""Run the whole test suite.

    python3 scripts/run_tests.py            # unit + integration + smoke + browser
    python3 scripts/run_tests.py -v         # verbose
    python3 scripts/run_tests.py flow       # only tests/test_flow.py
    python3 scripts/run_tests.py --no-smoke --no-browser

Unit, integration and smoke need nothing beyond the standard library, same as
the application. The browser stage needs Playwright; without it that stage
reports itself skipped rather than failing.
"""

import argparse
import os
import subprocess
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pattern", nargs="?", default=None,
                    help="only run tests/test_<pattern>.py")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--no-smoke", action="store_true",
                    help="skip the end-to-end smoke test")
    ap.add_argument("--no-browser", action="store_true",
                    help="skip the Playwright browser tests")
    args = ap.parse_args()

    os.environ.setdefault("MDMP_QUIET", "1")
    os.chdir(ROOT)

    pattern = "test_%s.py" % args.pattern if args.pattern else "test_*.py"
    loader = unittest.TestLoader()
    suite = loader.discover("tests", pattern=pattern, top_level_dir=ROOT)

    count = suite.countTestCases()
    print("=" * 72)
    print("  MDMP harness — %d test%s" % (count, "" if count == 1 else "s"))
    print("=" * 72)

    started = time.time()
    runner = unittest.TextTestRunner(verbosity=2 if args.verbose else 1,
                                     buffer=not args.verbose)
    result = runner.run(suite)
    elapsed = time.time() - started

    ok = result.wasSuccessful()

    if not args.no_smoke and not args.pattern:
        print("\n" + "=" * 72)
        print("  end-to-end smoke test")
        print("=" * 72)
        proc = subprocess.run([sys.executable, "scripts/smoke_test.py"],
                              cwd=ROOT)
        ok = ok and proc.returncode == 0

    if not args.no_browser and not args.pattern:
        proc = subprocess.run([sys.executable, "scripts/ui_test.py"], cwd=ROOT)
        ok = ok and proc.returncode == 0

    print("\n" + "=" * 72)
    print("  unit + integration: %d run, %d failed, %d errored, %d skipped "
          "(%.1fs)" % (result.testsRun, len(result.failures),
                       len(result.errors), len(result.skipped), elapsed))
    print("  %s" % ("ALL GREEN" if ok else "FAILURES ABOVE"))
    print("=" * 72)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
