#!/usr/bin/env python3
"""Produce a single self-contained HTML page that shows what the tool does.

    python3 scripts/export_demo.py                 # writes demo.html
    python3 scripts/export_demo.py --out /tmp/x.html

The point is a reviewer who should not have to install anything. One file, one
link, opens in any browser, works offline. It contains a real run of the tool —
every step, every field, the options the tool actually generated for each one
with its reasoning and trade-offs, and the finished operation order those
answers produced.

Nothing here is mocked up. The page is built by driving the same code the
application runs, on a throwaway database, and capturing the result.
"""

import argparse
import html
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from harness import auth, db                                    # noqa: E402
from harness.agent.engine import Engine                   # noqa: E402
from harness.flow import context_for, dep_hash                      # noqa: E402
from harness.mdmp import opord                            # noqa: E402
from harness.mdmp.flow_def import FLOW                    # noqa: E402

OPTIONS_PER_FIELD = 5


def run_a_plan(operation):
    """Answer every field from generated options. Returns the captured run."""
    engine = Engine()
    uid = auth.create_user("demo", "demo-not-a-real-account", "Demo", "admin")
    plan_id = db.ex(
        "INSERT INTO plans(name, flow_id, phase, created_by, created_at, "
        "updated_at, meta_json) VALUES(?,?,?,?,?,?,?)",
        (operation, FLOW.id, "planning", uid, db.now(), db.now(), "{}"))

    values, captured = {}, {}
    for step in FLOW.steps:
        for field in step.fields:
            ctx = context_for(FLOW, field, values)
            options, meta = engine.generate(FLOW, field, ctx,
                                            n=OPTIONS_PER_FIELD,
                                            plan_id=plan_id)
            if not options:
                continue
            # Always the tool's own first option. Nothing is steered by hand —
            # the page claims nothing on it was written by a person, and that
            # has to stay true or the reviewer is judging our taste, not the
            # tool's.
            chosen = options[0]["value"]
            if field.kind == "items":
                chosen = [o["value"] for o in options[:4]]
            elif field.kind == "multi":
                chosen = [o["value"] for o in options[:3]]
            elif field.kind == "table":
                # A table generator already emits each row as a list of cells;
                # only a model-written row arrives as a " | " string.
                chosen = [o["value"] if isinstance(o["value"], list)
                          else str(o["value"]).split(" | ")
                          for o in options[:5]]
            values[field.key] = chosen
            db.ex("INSERT INTO answers(plan_id, step_key, field_key, "
                  "value_json, dep_hash, source, author_id, created_at, "
                  "current) VALUES(?,?,?,?,?,?,?,?,1)",
                  (plan_id, step.key, field.key, json.dumps(chosen),
                   dep_hash(field, values), "selected", uid, db.now()))
            captured[field.key] = {
                "chosen": chosen,
                "options": options,
                "passages": meta.get("passages") or [],
            }
    return plan_id, values, captured


# ------------------------------------------------------------------ render --

def esc(t):
    return html.escape(str(t if t is not None else ""))


def as_text(value, kind=None):
    if isinstance(value, list):
        if value and isinstance(value[0], list):
            return "\n".join(" | ".join(str(c) for c in row) for row in value)
        if kind == "table":
            # One option for a table field is one row: cells, not a list.
            return " | ".join(str(c) for c in value)
        return "\n".join("(%d) %s" % (i + 1, v) for i, v in enumerate(value))
    return str(value or "")


def field_block(field, cap):
    opts = cap["options"]
    rows = []
    for i, o in enumerate(opts):
        flags = "".join('<span class="flag">%s</span>' % esc(f)
                        for f in (o.get("flags") or []))
        rows.append(
            '<div class="opt%s">'
            '<div class="opthead"><b>%s</b>%s%s</div>'
            '<div class="optval">%s</div>'
            '<div class="why">%s</div></div>'
            % (" chosen" if i == 0 else "",
               esc(o.get("label") or "Option %d" % (i + 1)),
               ' <span class="tick">chosen for this example</span>' if i == 0 else "",
               flags,
               esc(as_text(o.get("value"), field.kind)).replace("\n", "<br>"),
               esc(o.get("rationale") or "")))
    passages = ""
    if cap["passages"]:
        passages = ('<div class="doct"><b>Doctrine the tool retrieved:</b> '
                    + "; ".join(esc(p.get("title")) for p in cap["passages"])
                    + "</div>")
    return (
        '<section class="field" id="f-%s">'
        '<h3>%s</h3>'
        '<p class="plain">%s</p>'
        '<p class="doctrine">%s</p>'
        '%s'
        '<div class="opts">%s</div>'
        '</section>'
        % (esc(field.key), esc(field.label), esc(field.plain),
           esc(field.doctrine), passages, "".join(rows)))


def build_html(plan_id, values, captured, unit, operation):
    steps_html, rail = [], []
    for step in FLOW.steps:
        blocks = [field_block(f, captured[f.key]) for f in step.fields
                  if f.key in captured]
        rail.append('<li><a href="#s-%s"><span class="n">%d</span>%s'
                    '<small>%d decisions</small></a></li>'
                    % (esc(step.key), step.num, esc(step.title), len(blocks)))
        steps_html.append(
            '<div class="step" id="s-%s"><h2><span class="n">%d</span>%s</h2>'
            '<p class="steplead">%s</p>%s</div>'
            % (esc(step.key), step.num, esc(step.title),
               esc(step.purpose or step.plain), "".join(blocks)))

    doc, annexes = opord.build_document(plan_id)
    order = []
    for node in doc:
        if node["container"]:
            order.append('<h3 class="para">%s %s</h3>'
                         % (esc(node["num"]), esc(node["title"])))
            continue
        body = esc(node["body"]).replace("\n", "<br>")
        order.append(
            '<div class="node"><h4>%s %s <small>%s</small></h4><div>%s</div></div>'
            % (esc(node["num"]), esc(node["title"]), esc(node["owner"]),
               body or '<i class="muted">drafted by the staff</i>'))
    annex_rows = "".join(
        '<tr><td>%s</td><td>%s</td><td>%s</td></tr>'
        % (esc(a["letter"]), esc(a["title"]), esc(a["owner"]))
        for a in annexes)

    total_fields = sum(len(s.fields) for s in FLOW.steps)
    total_options = sum(len(c["options"]) for c in captured.values())

    page = TEMPLATE
    for token, value in (
            ("OPERATION", esc(operation)), ("UNIT", esc(unit)),
            ("STEPS", "".join(steps_html)), ("RAIL", "".join(rail)),
            ("ORDER", "".join(order)), ("ANNEXES", annex_rows),
            ("N_FIELDS", total_fields), ("N_OPTIONS", total_options),
            ("N_ANNEXES", len(annexes))):
        page = page.replace("{{%s}}" % token, str(value))
    return page


TEMPLATE = """<title>MDMP Harness Walkthrough</title>
<style>
:root{--bg:#faf9f7;--panel:#fff;--ink:#1c1b19;--ink2:#4a4844;--ink3:#78756e;
--line:#e2ded6;--accent:#33502f;--accent2:#eef2ec;--amber:#8a6d1f;--amber-bg:#fdf6e3}
:root:not([data-theme=light]) {}
@media (prefers-color-scheme: dark){:root:not([data-theme=light]){
--bg:#17181a;--panel:#1f2124;--ink:#eceae6;--ink2:#c2beb6;--ink3:#8f8b83;
--line:#33363a;--accent:#a9c9a2;--accent2:#222a21;--amber:#e0c070;--amber-bg:#2a2418}}
:root[data-theme=dark]{--bg:#17181a;--panel:#1f2124;--ink:#eceae6;--ink2:#c2beb6;
--ink3:#8f8b83;--line:#33363a;--accent:#a9c9a2;--accent2:#222a21;--amber:#e0c070;--amber-bg:#2a2418}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:0 1.2rem 5rem}
header{border-bottom:1px solid var(--line);margin-bottom:2rem;padding:2.5rem 0 1.6rem}
h1{margin:0 0 .3rem;font-size:1.9rem;letter-spacing:-.02em}
.sub{color:var(--ink3);margin:0 0 1.4rem}
.lede{background:var(--panel);border:1px solid var(--line);border-radius:10px;
padding:1.1rem 1.3rem;max-width:70ch}
.lede p{margin:.5rem 0}
.stats{display:flex;flex-wrap:wrap;gap:.6rem;margin:1.2rem 0 0;padding:0;list-style:none}
.stats li{background:var(--accent2);color:var(--accent);border-radius:99px;
padding:.3rem .85rem;font-size:.85rem;font-weight:600}
nav.tabs{display:flex;gap:.3rem;flex-wrap:wrap;position:sticky;top:0;z-index:5;
background:var(--bg);padding:.7rem 0;border-bottom:1px solid var(--line);margin-bottom:1.6rem}
nav.tabs button{font:inherit;font-size:.92rem;padding:.45rem 1rem;border-radius:8px;
border:1px solid transparent;background:none;color:var(--ink2);cursor:pointer}
nav.tabs button:hover{background:var(--panel)}
nav.tabs button[aria-selected=true]{background:var(--accent);color:var(--bg);
border-color:var(--accent);font-weight:600}
.panel[hidden]{display:none}
.cols{display:grid;grid-template-columns:230px 1fr;gap:2rem;align-items:start}
@media(max-width:820px){.cols{grid-template-columns:1fr}ol.rail{position:static}}
ol.rail{position:sticky;top:4.2rem;list-style:none;margin:0;padding:0;
border:1px solid var(--line);border-radius:10px;background:var(--panel);overflow:hidden}
ol.rail a{display:block;padding:.6rem .8rem;color:var(--ink2);text-decoration:none;
border-bottom:1px solid var(--line);font-size:.9rem;line-height:1.35}
ol.rail li:last-child a{border-bottom:0}
ol.rail a:hover{background:var(--accent2);color:var(--accent)}
ol.rail small{display:block;color:var(--ink3);font-size:.75rem}
.n{display:inline-grid;place-items:center;width:1.5rem;height:1.5rem;border-radius:50%;
background:var(--accent);color:var(--bg);font-size:.8rem;font-weight:700;margin-right:.5rem}
.step{margin-bottom:3rem;scroll-margin-top:4.5rem}
.step h2{font-size:1.35rem;display:flex;align-items:center;margin:0 0 .2rem}
.steplead{color:var(--ink3);margin:0 0 1.4rem;max-width:72ch}
.field{background:var(--panel);border:1px solid var(--line);border-radius:10px;
padding:1.1rem 1.3rem;margin-bottom:1rem}
.field h3{margin:0 0 .3rem;font-size:1.05rem}
.plain{margin:0 0 .35rem;color:var(--ink2);max-width:72ch}
.doctrine{margin:0 0 .9rem;color:var(--ink3);font-size:.85rem;max-width:72ch}
.doct{font-size:.8rem;color:var(--ink3);margin:0 0 .8rem}
.opts{display:grid;gap:.55rem}
.opt{border:1px solid var(--line);border-radius:8px;padding:.7rem .9rem;font-size:.93rem}
.opt.chosen{border-color:var(--accent);background:var(--accent2)}
.opthead{margin-bottom:.3rem}
.tick{color:var(--accent);font-size:.75rem;font-weight:600;margin-left:.4rem}
.flag{display:inline-block;background:var(--amber-bg);color:var(--amber);
border-radius:99px;padding:.05rem .55rem;font-size:.72rem;margin-left:.4rem}
.optval{color:var(--ink)}
.why{color:var(--ink3);font-size:.85rem;margin-top:.35rem;font-style:italic}
.order{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:1.6rem 1.8rem}
.para{margin:1.8rem 0 .6rem;font-size:1.1rem;border-bottom:2px solid var(--line);padding-bottom:.3rem}
.node{margin:0 0 1.1rem}
.node h4{margin:0 0 .25rem;font-size:.95rem}
.node h4 small{color:var(--ink3);font-weight:400;margin-left:.4rem}
.node div{color:var(--ink2);font-size:.93rem;max-width:78ch}
.muted{color:var(--ink3)}
table{border-collapse:collapse;width:100%;font-size:.9rem;margin-top:1rem}
th,td{text-align:left;padding:.4rem .6rem;border-bottom:1px solid var(--line)}
th{color:var(--ink3);font-weight:600;font-size:.8rem;text-transform:uppercase;letter-spacing:.04em}
code{background:var(--accent2);color:var(--accent);padding:.1rem .4rem;border-radius:4px;font-size:.88em}
.scroll{overflow-x:auto}
footer{margin-top:3rem;padding-top:1.4rem;border-top:1px solid var(--line);
color:var(--ink3);font-size:.88rem;max-width:72ch}
</style>
<div class="wrap">
<header>
  <h1>{{OPERATION}}</h1>
  <p class="sub">A complete run of the MDMP planning harness — {{UNIT}}</p>
  <div class="lede">
    <p><b>What you are looking at.</b> This is a real run of the tool, captured
    to a page so you can read it without installing anything. Every option below
    was generated by the tool from the plan as it stood at that moment. Nothing
    on this page was written by hand.</p>
    <p><b>What is being asked of you.</b> Whether the doctrine is right — the
    decisions it asks for, the order it asks for them in, the options it offers,
    and the order it produces at the end. Not the code.</p>
    <p><b>How the real thing differs.</b> In the tool these are live: you press
    <i>Generate options</i>, pick one, edit it, or write your own, and go back to
    any step at any time. This page is a snapshot with the first option taken
    every time, so you can see what it offers unaided.</p>
  </div>
  <ul class="stats">
    <li>7 steps</li><li>{{N_FIELDS}} decisions</li>
    <li>{{N_OPTIONS}} generated options</li><li>{{N_ANNEXES}} annexes</li>
    <li>no model — offline templates only</li>
  </ul>
</header>

<nav class="tabs" role="tablist">
  <button role="tab" aria-selected="true" data-p="plan">The seven steps</button>
  <button role="tab" aria-selected="false" data-p="order">The order it produced</button>
  <button role="tab" aria-selected="false" data-p="about">How to run it yourself</button>
</nav>

<div class="panel" id="p-plan">
  <div class="cols">
    <ol class="rail">{{RAIL}}</ol>
    <div>{{STEPS}}</div>
  </div>
</div>

<div class="panel" id="p-order" hidden>
  <div class="order">{{ORDER}}
    <h3 class="para">Annexes</h3>
    <div class="scroll"><table>
      <tr><th>Annex</th><th>Title</th><th>Suggested owner</th></tr>
      {{ANNEXES}}
    </table></div>
  </div>
</div>

<div class="panel" id="p-about" hidden>
  <div class="lede">
    <p><b>It is one command.</b> No install, no internet, no admin rights.
    Python 3.9 or newer is the only requirement.</p>
    <p><code>git clone https://github.com/dassey/mdmp</code><br>
    <code>cd mdmp &amp;&amp; python3 serve.py</code></p>
    <p>It prints two addresses. Open the first on that machine; the second is
    what other laptops on the same network use. The first person to open it
    creates the administrator account.</p>
    <p><b>Where the doctrine lives, if you want to change it.</b> The decisions
    and their explanations are in <code>harness/mdmp/flow_def.py</code>. The
    options are in <code>harness/mdmp/generators.py</code>. The shape of the
    order is in <code>harness/mdmp/doctrine.py</code>. The rules that reject a
    bad option — a mission statement missing one of the five Ws, a course of
    action that is not distinguishable from another, a PIR with no decision
    tied to it — are in <code>harness/agent/engine.py</code>.</p>
    <p><b>You do not need to touch any of that to give useful feedback.</b>
    Telling us "step 4 asks the wrong question" or "that is not what a PIR is"
    is the feedback that matters.</p>
  </div>
</div>

<footer>
  <p>Every unit, place, and operation named here is notional. The options are a
  starting point for a staff officer, not a product — the staff owns the words.
  Doctrine drawn from FM 5-0, FM 6-0, ADP 5-0, FM 3-0, ATP 2-01.3, ATP 5-19,
  and the TC 7-100 series.</p>
</footer>
</div>
<script>
document.querySelectorAll('nav.tabs button').forEach(function(b){
  b.addEventListener('click', function(){
    document.querySelectorAll('nav.tabs button').forEach(function(x){
      x.setAttribute('aria-selected', String(x === b));
    });
    ['plan','order','about'].forEach(function(p){
      document.getElementById('p-' + p).hidden = (p !== b.dataset.p);
    });
    window.scrollTo({top: 0});
  });
});
</script>
"""


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(ROOT, "demo.html"))
    ap.add_argument("--operation", default="OPERATION IRON ANVIL")
    args = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="mdmp-demo-")
    db.init(os.path.join(tmp, "demo.db"))
    plan_id, values, captured = run_a_plan(args.operation)
    unit = values.get("unit_designation") or "(unit)"
    page = build_html(plan_id, values, captured, unit, args.operation)

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(page)
    print("%s  (%.0f KB, %d fields, %d options)"
          % (args.out, len(page) / 1024.0, len(captured),
             sum(len(c["options"]) for c in captured.values())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
