# Working on this project

Notes for whoever picks this up next, human or agent. The owner is not going to
be editing this code — assume changes arrive through an agent session, and that
the person reading the result is a staff officer, not a programmer.

## Standing constraints

These are not preferences. Breaking one is a bug even if every test passes.

1. **Say nothing about classification.** No markings, no banners, no "(U)"
   prefixes, no guidance on handling or release, no fields asking for it, no
   warnings about it. Marking, handling, and release are decisions for people,
   and the tool takes no position. This holds in generated options, exported
   orders, interface text, and documentation alike. If a doctrine publication in
   `corpus/` discusses classification, that is fine — it is a source document,
   not the tool speaking. `tests/test_agent.py` guards this across every
   generator, the flow definition, the OPORD skeleton, the default prompts, and
   the interface text.

2. **Never show a blank field.** Every field must offer options, in every
   situation, including with no model configured, no network, and an empty plan.
   The offline generators in `harness/mdmp/generators.py` are the floor, and
   `engine.py` backfills from them when the critique layer rejects too many
   candidates. A field that can render an empty option list is broken.

3. **Every scenario is notional.** Generated units, places, and operations are
   invented. Nothing should reference a real current operation or a real unit in
   active deployment. `tests/test_agent.py::test_notional_names_only` guards this.

4. **No new dependencies in the application.** It runs on a locked-down laptop
   with no internet and no admin rights: `python3 serve.py` and nothing else.
   Python 3.9 is the floor. Two exceptions, both already in place — `anthropic`
   for the Claude provider (optional, degrades gracefully) and `playwright` for
   the browser test stage (test-only, reports itself skipped when absent).
   Adding a third is a decision for the owner, not a convenience.

5. **The staff owns the words.** Generated text is a starting point. Do not add
   anything that presents output as finished, authoritative, or approved.

## Before you push

```bash
python3 scripts/run_tests.py
```

Three stages, all must be green: 259 unit and integration tests, 47 smoke checks
against a real server over HTTP, 69 browser checks driving Chromium. It takes
about 75 seconds. `--no-browser` skips the slow stage while iterating, but the
full run is what goes on a branch.

CI runs the same thing on every push, on Python 3.9 and 3.13.

If you change a generator, the sweep in `tests/test_agent.py` exercises every one
across thousands of plan contexts — it has already caught generators that raised
on a literal `%` and silently degraded to "write it yourself". Trust it over
spot-checking.

## Branches

**Do not leave branches lying around.** `main` and nothing else, at rest.

Work goes straight to `main` once the suite is green — this is a small project
with one owner who is not reviewing diffs, and a branch that only ever gets
merged by the person who wrote it is ceremony, not safety. Use a branch only
when a change genuinely needs a second pair of eyes before it lands.

When you do use one: merge it as soon as CI is green, then delete it. A branch
that is fully contained in `main` has nothing in it — every commit is already
there — so deleting it loses nothing.

If a branch does not belong, delete it rather than leaving it to be puzzled
over later. Check first that it is actually merged:

```bash
git merge-base --is-ancestor origin/<branch> origin/main && echo "safe to delete"
```

Turning on **Settings → General → Automatically delete head branches** makes
GitHub do this itself on every merge, which is better than remembering.

## The shape of the thing

A generic flow engine with MDMP as its first tool. `harness/flow.py` knows
nothing about the military; `harness/mdmp/` holds everything that does.

| Path | What lives there |
|---|---|
| `harness/flow.py` | Field / Step / Flow, dependency hashing, staleness |
| `harness/db.py` | SQLite schema and helpers |
| `harness/auth.py` | accounts, scrypt passwords, sessions, roles |
| `harness/server.py` | stdlib HTTP server, router, static files |
| `harness/api.py` | the JSON API |
| `harness/agent/prompts.py` | prompt defaults and the override chain |
| `harness/agent/providers.py` | offline / ollama / openai-compatible / anthropic |
| `harness/agent/engine.py` | retrieve → propose → critique → backfill |
| `harness/rag/` | text extraction, FTS5 index, BM25 search |
| `harness/mdmp/flow_def.py` | the flow: 7 steps, 66 fields, each mapped to the OPORD |
| `harness/mdmp/generators.py` | 64 offline option generators |
| `harness/mdmp/opord.py` | assembly and rendering |
| `static/` | vanilla-JS single page, no build step |

`docs/EXTENDING.md` covers adding a field, adding a critique rule, the prompt
override chain, and building a second flow on the same engine. Read it before
changing any of those — particularly `only_changes()`, which is subtle and easy
to break.

## Things that look like bugs and are not

- **Prompt overrides do nothing on the offline provider.** Correct — those
  options come from code, not from a model. The editor says so.
- **An unknown `{placeholder}` survives into the prompt.** Correct — it is
  reported to the planner rather than rejected, so a typo does not block work.
- **Changing an early answer does not delete later ones.** Correct — they are
  flagged *needs review*. A human decides whether the change invalidated them.
- **A stale answer keeps its old value.** Correct, same reason.

## Tone

The interface is read under time pressure by people who did not choose to use
it. Plain sentences, no exclamation marks, no encouragement, no apologising.
Explain what a field is for in the words a staff officer would use. Where the
tool is uncertain, say so plainly and let the planner decide.
