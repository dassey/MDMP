#!/usr/bin/env python3
"""Drive the whole application through a real browser.

    python3 scripts/ui_test.py              # both suites, headless
    python3 scripts/ui_test.py --headed     # watch it happen
    python3 scripts/ui_test.py --shots DIR  # keep the screenshots

Unlike the rest of the harness this one is not zero-dependency: it needs
Playwright and a Chromium build.

    pip install playwright && playwright install chromium

If Playwright is missing the script says so and exits 0, so it can sit in CI
next to the stdlib tests without becoming a hard requirement.

Each suite gets its own throwaway server and database on its own port, so
neither can see the other's accounts, plans, or prompt overrides.
"""

import argparse
import contextlib
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMIUM_HINTS = [
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/opt/pw-browsers/chromium/chrome-linux/chrome",
]


def free_port():
    with contextlib.closing(socket.socket()) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def chromium_path():
    for p in CHROMIUM_HINTS:
        if os.path.exists(p):
            return p
    return None       # let Playwright find its own


@contextlib.contextmanager
def server():
    """A fresh server on a free port with an empty database."""
    port = free_port()
    tmp = tempfile.mkdtemp(prefix="mdmp-ui-")
    env = dict(os.environ, MDMP_QUIET="1")
    proc = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "serve.py"),
         "--host", "127.0.0.1", "--port", str(port),
         "--data", os.path.join(tmp, "ui.db")],
        cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = "http://127.0.0.1:%d" % port
    try:
        deadline = time.time() + 60
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError("server exited with %s" % proc.returncode)
            try:
                urllib.request.urlopen(base + "/", timeout=2).read()
                break
            except (urllib.error.URLError, socket.timeout, ConnectionError):
                time.sleep(0.4)
        else:
            raise RuntimeError("server did not come up on %s" % base)
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)


class Suite:
    """Collects pass/fail so one bad check does not hide the other twenty."""

    def __init__(self, name, shots):
        self.name = name
        self.shots = shots
        self.failures = []
        self.checks = 0
        print("\n%s\n  %s\n%s" % ("-" * 72, name, "-" * 72))

    def check(self, label, cond, detail=""):
        self.checks += 1
        print("  [%s] %s%s" % ("ok  " if cond else "FAIL", label,
                               "" if cond else " — " + str(detail)[:200]))
        if not cond:
            self.failures.append(label)

    def shot(self, page, name, full_page=False):
        if self.shots:
            page.screenshot(path=os.path.join(self.shots, name),
                            full_page=full_page)


def new_page(pw, headed, errors):
    browser = pw.chromium.launch(headless=not headed,
                                 executable_path=chromium_path())
    page = browser.new_page(viewport={"width": 1500, "height": 1000})
    page.on("console",
            lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("dialog", lambda d: d.accept())
    return browser, page


def sign_up(page, base, user, name, password="testpass"):
    page.goto(base)
    page.wait_for_timeout(700)
    page.fill("input[type=text] >> nth=0", user)
    page.fill("input[type=text] >> nth=1", name)
    page.fill("input[type=password]", password)
    page.click("button:has-text('Create account')")
    page.wait_for_timeout(900)


def start_plan(page, name):
    page.fill("input[placeholder*='OPERATION']", name)
    page.click("button:has-text('Start a new plan')")
    page.wait_for_timeout(1300)


# --------------------------------------------------------------- suite one --

def suite_workflow(pw, base, headed, shots):
    """The planner's path: sign in, answer fields, move between steps, export."""
    s = Suite("planning workflow", shots)
    errors = []
    browser, pg = new_page(pw, headed, errors)
    try:
        pg.goto(base)
        pg.wait_for_timeout(700)
        s.check("first-run setup screen", "First run" in pg.content())
        sign_up(pg, base, "cdr", "COL Massey")
        s.check("signed in, plans list shown", "Plans" in pg.content())
        s.shot(pg, "ui-1-plans.png")

        start_plan(pg, "OPERATION IRON ANVIL")
        s.check("plan workspace opened", "Step 1" in pg.content())
        s.check("step rail present", pg.locator(".step").count() == 7,
                pg.locator(".step").count())
        s.shot(pg, "ui-2-step1.png")

        pg.click("button:has-text('Generate options') >> nth=0")
        pg.wait_for_timeout(1100)
        n = pg.locator(".opt").count()
        s.check("options rendered", n >= 3, n)
        s.shot(pg, "ui-3-options.png")

        pg.click(".opt >> nth=0 >> button:has-text('Use this')")
        pg.wait_for_timeout(800)
        s.check("answer saved and shown", pg.locator(".answer").count() >= 1)
        s.check("field badge now answered",
                pg.locator(".badge.answered").count() >= 1)

        pg.click("button:has-text('Write my own') >> nth=1")
        pg.wait_for_timeout(400)
        ta = pg.locator("textarea").first
        s.check("writer opened", ta.count() == 1)
        ta.fill("Battalion / Squadron")
        pg.click("button:has-text('Save')")
        pg.wait_for_timeout(700)
        s.check("hand-written answer saved",
                "Battalion / Squadron" in pg.content())

        # jumping away and back is a core requirement, not a nicety
        pg.click(".step >> nth=4")
        pg.wait_for_timeout(700)
        s.check("jumped to step 5", "Step 5" in pg.content())
        s.shot(pg, "ui-4-step5.png")
        pg.click(".step >> nth=0")
        pg.wait_for_timeout(700)
        s.check("returned to step 1 with answers intact",
                "Step 1" in pg.content() and pg.locator(".answer").count() >= 2)

        pg.click(".step >> nth=1")
        pg.wait_for_timeout(700)
        s.check("step 2 loaded", "Mission Analysis" in pg.content())
        pg.locator("button:has-text('Generate options')").nth(1).click()
        pg.wait_for_timeout(1100)
        add = pg.locator("button:has-text('Add to list')")
        s.check("multi-select options offer 'Add to list'", add.count() >= 2,
                add.count())
        add.nth(0).click()
        pg.wait_for_timeout(600)
        s.check("list answer recorded", pg.locator(".item").count() >= 1,
                pg.locator(".item").count())
        s.shot(pg, "ui-5-items.png")

        for tab, marker in (("Staff production", "staff"), ("OPORD", "operation"),
                            ("Briefing products", "warning")):
            pg.click(".tab:has-text('%s')" % tab.split()[0])
            pg.wait_for_timeout(900)
            s.check("tab '%s' renders" % tab, marker in pg.content().lower())
        s.shot(pg, "ui-6-opord.png")

        pg.click(".tab:has-text('Plan')")
        pg.wait_for_timeout(400)
        pg.click("button:has-text('Settings')")
        pg.wait_for_timeout(1200)
        s.check("settings shows provider, doctrine, accounts",
                all(x in pg.content() for x in
                    ["Model provider", "Doctrine library", "Accounts"]))
        s.check("doctrine documents listed", "mdmp overview" in pg.content().lower())
        s.shot(pg, "ui-7-settings.png", full_page=True)

        pg.set_viewport_size({"width": 420, "height": 900})
        pg.click("button:has-text('back to plans')")
        pg.wait_for_timeout(900)
        width = pg.evaluate("document.body.scrollWidth")
        s.check("no horizontal overflow on a phone", width <= 430, width)
        s.shot(pg, "ui-8-mobile.png")
    finally:
        browser.close()
    s.check("no javascript errors",
            not [e for e in errors if "favicon" not in e.lower()], errors[:3])
    return s


# --------------------------------------------------------------- suite two --

def suite_prompts(pw, base, headed, shots):
    """The gear icons and the prompt editor behind them."""
    s = Suite("prompt editing", shots)
    errors = []
    browser, pg = new_page(pw, headed, errors)
    try:
        sign_up(pg, base, "cdr", "LTC Reyes")
        start_plan(pg, "OPERATION STEEL RAIN")
        s.check("plan workspace opened", "Step 1" in pg.content())

        gears = pg.locator("button.gear")
        ngears = gears.count()
        s.check("gear on the step header and on every field", ngears >= 4, ngears)
        s.check("flow-wide prompt bar present",
                pg.locator("button:has-text('Prompt for every field')").count() == 1)
        s.check("gear carries an accessible label",
                bool(gears.nth(0).get_attribute("aria-label")))

        # ------------------------------------------------------- field level
        gears.nth(1).click()
        pg.wait_for_timeout(900)
        s.check("modal opened", pg.locator(".modal").count() == 1)
        body = pg.content()
        s.check("modal titled for the field", "Prompt —" in body)
        s.check("shows which system prompt is in force",
                "System prompt in force: built-in default" in body)
        s.check("shows which task template is in force",
                "Task template in force: built-in default" in body)
        s.check("two editable boxes", pg.locator(".modal textarea").count() == 2)
        s.check("placeholder help present", "{step_title}" in body)
        preview = pg.locator("pre.preview").inner_text()
        s.check("live preview rendered", len(preview) > 200, len(preview))
        s.check("preview interpolated the real step title",
                "Receipt of Mission" in preview)
        reset = pg.locator(".modalfoot button:has-text('Reset to built-in')")
        s.check("reset is disabled with nothing to reset", reset.is_disabled())
        s.shot(pg, "ui-9-prompt-field.png")

        tpl = pg.locator(".modal textarea").nth(1)
        tpl.fill("MARKER-ALPHA for {field_label} in step {step_num}. "
                 "Give {n} options. {kind_instruction}")
        pg.click(".modalfoot button:has-text('Preview')")
        pg.wait_for_timeout(900)
        pv = pg.locator("pre.preview").inner_text()
        s.check("preview reflects the edited template", "MARKER-ALPHA" in pv,
                pv[:120])
        s.check("preview interpolated {step_num}", "step 1." in pv, pv[:120])
        s.check("source now reports a field override",
                "field override" in pg.content())
        s.check("reset became available once an override exists",
                not reset.is_disabled())
        pg.check(".modalfoot input[type=checkbox]")
        pg.wait_for_timeout(200)
        s.check("reset goes back to disabled for the empty server scope",
                reset.is_disabled())
        pg.uncheck(".modalfoot input[type=checkbox]")
        pg.wait_for_timeout(200)
        s.shot(pg, "ui-10-prompt-edited.png")

        tpl.fill("MARKER-ALPHA {field_label} {not_a_real_placeholder} {n}")
        pg.click(".modalfoot button:has-text('Save')")
        pg.wait_for_timeout(900)
        s.check("unknown placeholder is reported, not rejected",
                "not_a_real_placeholder" in pg.content())
        s.check("modal closed after save", pg.locator(".modal").count() == 0)

        pg.locator("button.gear").nth(1).click()
        pg.wait_for_timeout(800)
        s.check("override persisted across a reopen",
                "MARKER-ALPHA" in pg.locator(".modal textarea").nth(1).input_value())
        s.check("status says this plan owns an override",
                "This plan has its own override" in pg.content())
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(400)
        s.check("Escape dismisses the modal", pg.locator(".modal").count() == 0)

        # ------------------------------------------------ from the options panel
        pg.click("button:has-text('Generate options') >> nth=0")
        pg.wait_for_timeout(1200)
        s.check("options rendered under an override",
                pg.locator(".opt").count() >= 3, pg.locator(".opt").count())
        s.check("options header carries a prompt button",
                pg.locator("button:has-text('⚙ prompt')").count() >= 1)
        pg.click("button:has-text('⚙ prompt') >> nth=0")
        pg.wait_for_timeout(800)
        s.check("options-panel gear opens the same editor",
                pg.locator(".modal").count() == 1 and "MARKER-ALPHA" in
                pg.locator(".modal textarea").nth(1).input_value())

        pg.click(".modalfoot button:has-text('Reset to built-in')")
        pg.wait_for_timeout(900)
        s.check("reset closes the modal", pg.locator(".modal").count() == 0)
        pg.locator("button.gear").nth(1).click()
        pg.wait_for_timeout(800)
        s.check("reset restored the built-in template", "MARKER-ALPHA" not in
                pg.locator(".modal textarea").nth(1).input_value())
        s.check("status back to built-in default",
                "Task template in force: built-in default" in pg.content())
        pg.mouse.click(30, 30)
        pg.wait_for_timeout(400)
        s.check("clicking the backdrop dismisses the modal",
                pg.locator(".modal").count() == 0)

        # -------------------------------------------------------- step level
        pg.locator("button.gear").nth(0).click()
        pg.wait_for_timeout(800)
        s.check("step gear scopes to the whole step",
                "every field in this step" in pg.content())
        pg.locator(".modal textarea").nth(0).fill(
            "You are a step-scoped planner. Answer only with JSON.")
        pg.click(".modalfoot button:has-text('Save')")
        pg.wait_for_timeout(900)
        pg.locator("button.gear").nth(1).click()
        pg.wait_for_timeout(800)
        s.check("field inherits the step-level system prompt",
                "System prompt in force: step override (this plan)" in pg.content())
        s.check("the untouched half stays inherited",
                "Task template in force: built-in default" in pg.content())
        s.check("chain lists the step override", "step override" in pg.content())
        s.shot(pg, "ui-11-prompt-inherit.png")
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(300)

        # ------------------------------------------- flow-wide, server scope
        pg.click("button:has-text('Prompt for every field')")
        pg.wait_for_timeout(800)
        s.check("flow-wide gear scopes to every field",
                "every field in the flow" in pg.content())
        pg.check(".modalfoot input[type=checkbox]")
        pg.wait_for_timeout(200)
        s.check("scope note switches to server-wide",
                "applies to every plan on this machine" in pg.content())
        pg.locator(".modal textarea").nth(1).fill(
            "SERVER-WIDE MARKER {field_label} {n} {kind_instruction}")
        pg.click(".modalfoot button:has-text('Save')")
        pg.wait_for_timeout(900)

        pg.click(".brand")
        pg.wait_for_timeout(1000)
        start_plan(pg, "OPERATION SECOND PLAN")
        pg.locator("button.gear").nth(1).click()
        pg.wait_for_timeout(800)
        s.check("a new plan inherits the server-wide default",
                "SERVER-WIDE MARKER" in
                pg.locator(".modal textarea").nth(1).input_value())
        s.check("source names the server scope",
                "global override (server default)" in pg.content())
        s.check("the other plan's step override does not leak in",
                "System prompt in force: built-in default" in pg.content())
        s.shot(pg, "ui-12-prompt-server.png")
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(300)

        pg.click("button:has-text('Generate options') >> nth=0")
        pg.wait_for_timeout(1200)
        s.check("options still generate under a server-wide override",
                pg.locator(".opt").count() >= 3, pg.locator(".opt").count())

        pg.click("button:has-text('Prompt for every field')")
        pg.wait_for_timeout(800)
        pg.check(".modalfoot input[type=checkbox]")
        pg.click(".modalfoot button:has-text('Reset to built-in')")
        pg.wait_for_timeout(900)

        # --------------------------------------------------- gears elsewhere
        for idx, marker in ((1, "Mission Analysis"), (4, "Step 5")):
            pg.locator(".step").nth(idx).click()
            pg.wait_for_timeout(900)
            s.check("step %d loaded" % (idx + 1), marker in pg.content())
            n = pg.locator("button.gear").count()
            s.check("step %d has a gear per field plus the header" % (idx + 1),
                    n >= 3, n)
            pg.locator("button.gear").nth(n - 1).click()
            pg.wait_for_timeout(800)
            s.check("the last field's gear on step %d opens its editor"
                    % (idx + 1), pg.locator(".modal").count() == 1)
            pg.keyboard.press("Escape")
            pg.wait_for_timeout(300)

        pg.click("button:has-text('Sign out')")
        pg.wait_for_timeout(900)
        s.check("signed out", "Sign in" in pg.content())
    finally:
        browser.close()
    s.check("no javascript errors",
            not [e for e in errors if "favicon" not in e.lower()], errors[:3])
    return s


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--headed", action="store_true",
                    help="show the browser instead of running headless")
    ap.add_argument("--shots", default=None,
                    help="directory to write screenshots into")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed — skipping the browser tests.")
        print("  pip install playwright && playwright install chromium")
        return 0

    if args.shots:
        os.makedirs(args.shots, exist_ok=True)

    print("=" * 72)
    print("  MDMP harness — browser tests")
    print("=" * 72)

    suites = []
    started = time.time()
    with sync_playwright() as pw:
        for fn in (suite_workflow, suite_prompts):
            with server() as base:
                suites.append(fn(pw, base, args.headed, args.shots))

    checks = sum(s.checks for s in suites)
    failures = [f for s in suites for f in s.failures]
    print("\n" + "=" * 72)
    print("  browser: %d check%s, %d failed (%.1fs)"
          % (checks, "" if checks == 1 else "s", len(failures),
             time.time() - started))
    if failures:
        for f in failures:
            print("    FAILED  %s" % f)
    print("  %s" % ("ALL GREEN" if not failures else "FAILURES ABOVE"))
    print("=" * 72)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
