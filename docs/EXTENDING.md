# Extending the harness

The MDMP tool is one flow running on a general engine. This document is about
the engine — how to change the MDMP flow, and how to build a different tool on
the same machinery.

---

## The model

```
Flow          an ordered list of Steps
  Step        a phase of work; holds Fields
    Field     one decision a human has to make
```

A **Field** declares:

| Property | What it does |
|---|---|
| `key` | Unique identifier. Used in the database, the API, and the OPORD mapping. |
| `label` | What the human sees. |
| `kind` | `choice`, `multi`, `text`, `items`, or `table`. Determines the widget and the shape of the stored value. |
| `plain` | One or two sentences explaining the field to someone who has never done this. This is not decoration — it is the difference between a usable tool and a form. |
| `doctrine` | The reference and the doctrinal note, for someone who has. |
| `depends` | Other field keys this one is built from. Drives generation context *and* staleness. |
| `opord` | Which OPORD nodes this field feeds. This is what removes retyping. |
| `gen` | Which generator produces options. Defaults to `key`. |
| `columns` | For `table` fields. |
| `required` | Whether the step can be complete without it. |
| `owner` | Default staff section, used to suggest paragraph ownership later. |

Value shapes by kind:

| Kind | Stored value | Option `value` |
|---|---|---|
| `choice` | string | the full choice |
| `text` | string | a complete draft |
| `multi` | list of strings | one selectable entry |
| `items` | list of strings | one list entry |
| `table` | list of rows (each a list of cells) | one candidate row |

---

## Adding a field to the MDMP flow

Three edits, all additive.

**1. Declare it** in `harness/mdmp/flow_def.py`, inside the right step:

```python
Field("deception_plan", "Military deception plan", kind="text",
      gen="deception_plan",
      plain="What you want the enemy to believe, and what you will do to make "
            "them believe it. Deception that is not resourced is a wish.",
      doctrine="FM 3-13.4. The deception objective is what you want the "
               "enemy to DO, not what you want them to think.",
      depends=["approved_coa", "enemy_mlcoa", "intent_key_tasks"],
      opord=["p3h"], owner="s3"),
```

**2. Register a generator** in `harness/mdmp/generators.py`:

```python
@generator("deception_plan")
def gen_deception(ctx, n=3):
    return [
        opt("Draw the reserve north",
            "DECEPTION OBJECTIVE: cause the threat to commit its reserve "
            "north of PHASE LINE BLUE before H+2. STORY: a brigade attack "
            "in the north. MEANS: demonstration by the cavalry squadron, "
            "increased radio traffic on a dummy net, and vehicle tracks "
            "into false assembly areas.",
            "Ties the objective to an enemy ACTION, which is the test of a "
            "real deception plan.",
            ["Consumes the cavalry squadron for the first two hours"]),
        opt("No deception effort", "No deception effort is planned for this "
            "operation.", "Honest, and better than a deception annex nobody "
            "resources."),
        opt("Write the deception plan myself", "", ""),
    ][:n]
```

**3. Nothing else.** The wizard renders it, the dependency tracker watches it,
the OPORD draft picks it up in paragraph 3h, and every export includes it.

To make a field feed a *new* OPORD paragraph, add a node to `OPORD_SKELETON` in
`harness/mdmp/doctrine.py` and reference the field in its `from` list.

---

## What the critique layer checks

`harness/agent/engine.py` scores every model-generated candidate before a human
sees it. Rules are per-field and deliberately specific:

- **`mission_statement`** — must contain a WHEN (a time or a trigger), a WHY (a
  purpose clause), and a doctrinal task verb.
- **`coa_1/2/3`** — must name the decisive operation or the main effort, and
  must not be a token-level near-duplicate of another COA. Duplicates are
  dropped, not flagged; an indistinguishable COA is worse than no COA.
- **`ccir_pir`** — must be a question and must reference a decision.
- **`assumptions`** — must state how the assumption will be confirmed or denied.
- **`intent_end_state`** — must cover friendly, threat, terrain, or civil
  conditions.
- **`intent_key_tasks`** — must not name a specific subordinate unit, because
  key tasks are conditions for the force.

Hard failures are dropped. Soft failures survive with a `check:` flag so the
planner sees the concern rather than having the option silently withheld.

Add a rule by extending `_critique()`. Keep them cheap — they run on every
candidate.

---

## Adding a generator that adapts to the plan

Generators receive `ctx`, which holds the field's declared dependencies plus a
little ambient context (echelon, unit, operation type, operational environment,
threat posture, mission statement, intent). Helpers in `generators.py`:

```python
_unit(ctx)          # "2d Brigade Combat Team, 52d Infantry Division"
_echelon_key(ctx)   # "bct"
_subordinates(ctx)  # ["1-11 IN", "2-11 IN", ...] — correct for the echelon
_optype(ctx)        # "offense" | "defense" | "stability" | "dsca"
_posture(ctx)       # ("near_peer", "Near-Peer", "...")
_phases(ctx)        # phase names appropriate to the operation type
_country(ctx, i)    # notional country from the selected environment
_g(i)               # a deconflicted set of notional graphic control measures
```

Two rules that matter:

1. **Always return at least one usable option.** A generator that raises is
   caught and replaced with a "write it yourself" placeholder, but that is a
   degraded experience. The test at the bottom of this document exercises every
   generator against every context combination for exactly this reason.
2. **Escape literal percent signs** as `%%` in `%`-formatted strings. Three
   generators shipped broken for this reason during development; the test now
   catches it.

---

## Building a second tool

Write a new flow definition. It imports `harness.flow` and nothing from the MDMP
package:

```python
# harness/tlp/flow_def.py — troop leading procedures, company and below
from harness.flow import Field, Flow, Step

FLOW = Flow(
    flow_id="tlp",
    title="Troop Leading Procedures",
    description="Eight steps, platoon and company level, ending in an "
                "operation order briefed from a terrain model.",
    steps=[
        Step(key="receive", num=1, title="Receive the Mission", fields=[...]),
        Step(key="warno", num=2, title="Issue a Warning Order", fields=[...]),
        Step(key="tentative", num=3, title="Make a Tentative Plan", fields=[...]),
        Step(key="movement", num=4, title="Initiate Movement", fields=[...]),
        Step(key="recon", num=5, title="Conduct Reconnaissance", fields=[...]),
        Step(key="complete", num=6, title="Complete the Plan", fields=[...]),
        Step(key="issue", num=7, title="Issue the Order", fields=[...]),
        Step(key="supervise", num=8, title="Supervise and Refine", fields=[...]),
    ],
)
```

Then:

- Register generators for its fields (a separate module, same `@generator`
  registry — keys must be unique across flows, so prefix them).
- Give it a document skeleton if it produces one, following the shape of
  `OPORD_SKELETON`.
- Point the API at it. Today `harness/api.py` imports the MDMP flow directly;
  making the flow selectable per plan is a matter of a registry lookup keyed on
  `plans.flow_id`, which the schema already stores.

Everything else — accounts, staleness, option generation, critique, retrieval,
the wizard, exports, multi-user production — is flow-agnostic and comes free.

---

## Storage

One SQLite file. Every table is small and readable.

```
users        accounts and roles
sessions     signed-in browser sessions
plans        one row per plan; carries flow_id and phase
plan_members plan-scoped roles
answers      append-only. Superseded rows keep current=0, so nothing is lost
             and every field has a full history
optionsets   cached generated options, keyed by the hash of the field's
             dependency values — change an input, get fresh options
sections     OPORD paragraphs and annexes with owner and status
activity     the feed
docs/chunks  the doctrine index (chunks is an FTS5 virtual table)
settings     provider configuration
prompts      prompt overrides, keyed by (level, scope_key, plan_id). A NULL
             plan_id is the server-wide default
```

The `dep_hash` column on `answers` is the whole staleness mechanism: it is a
hash of the values a field's dependencies had when it was answered. If the
current hash differs, the answer is stale. Nothing is ever auto-deleted — a
human decides whether the change actually invalidates the answer.

---

## Prompts and the override chain

`harness/agent/prompts.py` owns everything the model is told. Two independent
pieces of text — `DEFAULT_SYSTEM` (role, rules, output contract) and
`DEFAULT_TEMPLATE` (the field, the plan context, the retrieved doctrine) — with
an override chain on top of each.

```
resolve(plan_id, step_key, field_key) -> {system, system_source,
                                          template, template_source}
```

walks seven rungs, most specific first, and stops at the first non-empty value
**for each half separately**:

```
field override, this plan          <- P.save("field", field_key, plan_id, ...)
field override, server default     <- P.save("field", field_key, None, ...)
step  override, this plan
step  override, server default
global override, this plan
global override, server default
built-in default                   <- DEFAULT_SYSTEM / DEFAULT_TEMPLATE
```

Because the halves resolve independently, a row that sets only `template`
leaves `system` falling through to the next rung. That is what makes the editor
usable: you can rewrite the task template for one field without restating the
whole system prompt.

Two rules keep the chain honest, and both matter if you write a client:

- **`only_changes()` before `save()`.** The editor pre-fills both boxes with the
  text currently in force, wherever it came from. Storing an untouched box would
  silently pin it at this level, so a planner tweaking a template would freeze
  the system prompt against later changes higher up. `only_changes()` resolves
  the chain *with this rung skipped* and blanks any half that matches.
- **A row with both halves blank is deleted.** It overrides nothing, and leaving
  it would make the editor claim a customisation that is not there.

### Adding a placeholder

Add it to `PLACEHOLDERS` (name and the description shown in the editor) and
supply it in `values_for()`. `test_every_documented_placeholder_is_actually_provided`
fails if you do one without the other.

Rendering is deliberately forgiving: `render()` uses a `format_map` subclass that
leaves unknown placeholders in place, and catches the malformed-template errors
so a stray `{` degrades to the built-in with an explanation rather than breaking
generation. `unknown_placeholders()` is what the API reports back to the editor.

Prompts never reach the offline provider — `engine.generate()` calls the
generators directly for it. An override there is stored and reported, but it
changes nothing until a model is configured.

---

## Testing

```bash
python3 scripts/run_tests.py            # unit + integration + smoke + browser
python3 scripts/run_tests.py prompts    # just tests/test_prompts.py
python3 scripts/run_tests.py --no-browser
```

`tests/` is stdlib `unittest`; `tests/base.py` gives you `DbCase` with a
throwaway database and `make_plan` / `answer` / `answers` / `hashes` helpers.

`scripts/smoke_test.py` drives the whole tool over HTTP against a throwaway
database. When you add a field it is automatically covered — the test walks
every field in the flow, generates options, and answers from them.

`scripts/ui_test.py` does the same through Chromium, one throwaway server per
suite. It is the only part of the project with a dependency; without Playwright
installed it prints a note and exits 0 rather than failing.

The generator sweep is worth keeping close by:

```python
import sys; sys.path.insert(0, '.')
from harness.mdmp import generators as G

for key, fn in G.REGISTRY.items():
    for ctx in [{}, {"operation_type": "Defensive Operation: Area Defense"}]:
        out = fn(ctx, 6)                      # must not raise
        assert any(not (isinstance(o["value"], str) and not o["value"].strip())
                   for o in out), key         # must offer something usable
```

Run it across the cross product of operation type, threat posture, environment,
and echelon before shipping a generator change.
