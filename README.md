# MDMP Harness

A planning workbench that walks a staff through the seven steps of the military
decision-making process and comes out the other side with a finished
five-paragraph operation order.

It is built to run on one laptop that other laptops can reach. No internet, no
cloud account, no install.

```
python3 serve.py
```

That is the whole setup. Python 3.9 or newer, nothing else.

---

## What it does

**It never shows you a blank box.** Every decision in the process — the mission
statement, the enemy's most likely course of action, the PIRs, the
synchronization matrix, the PACE plan — arrives as a set of concrete, doctrinally
grounded options with the reasoning behind each one and the trade-off it carries.
You accept one, edit one, or write your own. Staring at an empty field wondering
what is supposed to go there is the thing this tool exists to remove.

**Every decision flows into the order.** A field answered in step 2 lands in
paragraph 1c of the OPORD without anyone retyping it. By the time you reach step
7 most of the order is already written; the staff's job becomes refining and
owning paragraphs rather than transcribing them.

**You can go back to any step, at any time.** Change something in step 2 after
you have war-gamed, and every answer downstream that depended on it is flagged
for review — not deleted, not silently left wrong. The step rail shows you
exactly what needs a second look.

**Other people can log in and do their part.** Once the planning steps are done,
the order is broken into its paragraphs and annexes, each with a suggested staff
section. Anyone on the network claims theirs, writes it, and marks it ready. The
commander approves. Everyone sees everyone else's progress within a few seconds.

**It works with no model at all.** Option generation falls back to doctrinal
templates that read the plan you have built so far. Point it at a local model
(Ollama, LM Studio, llama.cpp, GPT4All) and the options fit your specific
scenario more closely. Point it at the Claude API if the machine has internet.
Same interface either way — the tool degrades, it does not break.

**Every prompt is yours to change.** The defaults are written and working, but
a gear icon next to every step and every field opens what is actually sent to
the model, with a live preview. Rewrite it for one field, one step, or the whole
flow; for this plan or as the machine's default. Your headquarters does things
its own way — the tool should not argue.

---

## Running it

```bash
python3 serve.py                       # 0.0.0.0:8080, reachable across the LAN
python3 serve.py --port 9000
python3 serve.py --host 127.0.0.1      # this machine only
python3 serve.py --reindex             # rebuild the doctrine index
```

On start it prints the addresses other machines should use:

```
  Open on this machine:   http://localhost:8080
  Others on the network:  http://10.1.20.14:8080
```

The first person to open the page creates the administrator account. Everyone
else is added from **Settings → Accounts**.

Convenience launchers: `./run.sh` (macOS/Linux) and `run.bat` (Windows).

### Roles

| Role | Can do |
|---|---|
| `admin` | Everything, plus accounts, the model provider, and the doctrine index |
| `commander` | Approve paragraphs, own the intent, run the steps |
| `planner` | Run the seven steps, edit any field |
| `staff` | Write and edit the OPORD paragraphs and annexes they own |
| `observer` | Read only |

---

## Connecting a model

**Settings → Model provider.** The tool probes for local servers and tells you
what it found.

| Provider | Use when | Setup |
|---|---|---|
| **Offline templates** | Always available; the default | Nothing |
| **Ollama** | Best local option on a laptop | `ollama pull qwen2.5:7b-instruct` then point at `http://localhost:11434` |
| **OpenAI-compatible** | LM Studio, llama.cpp server, vLLM, GPT4All | Start the server, point at its base URL (e.g. `http://localhost:1234/v1`) |
| **Claude API** | Machine has internet and you want the strongest drafting | `pip install anthropic`, then paste an API key |

A 7–8B instruct model at 4-bit quantisation fits in about 5 GB of RAM and
generates faster than a person reads, which is the bar that matters here. The
harness itself needs no model and no extra packages — the Claude provider is the
one optional install.

Environment variables work too, if you would rather not use the settings page:

```bash
MDMP_PROVIDER=ollama MDMP_MODEL=qwen2.5:7b-instruct python3 serve.py
```

---

## The doctrine library

`corpus/` is indexed at startup into a local full-text search index (SQLite
FTS5 — BM25 ranking, no embeddings, no GPU, instant on a CPU-only machine).
Passages retrieved for a field are shown alongside the options they informed.

It ships with a set of distilled reference notes in `corpus/seed/` so retrieval
works on day one. **Add the real publications** — drop PDFs into `corpus/` and
hit *Index new documents* in Settings. See `corpus/README.md` for the list worth
having.

Readable formats: PDF, DOCX, PPTX, TXT, Markdown, HTML, CSV. PDF extraction is
built in; `pip install pypdf` improves it. Scanned PDFs need OCR first — the
ingest tool will tell you when it finds one.

---

## The harness underneath

The MDMP tool is one *flow* running on a general engine. A flow is a list of
steps; a step holds fields; a field is one decision. The engine handles
dependency tracking, staleness, option generation, critique, persistence, and
document assembly — and knows nothing about MDMP.

```
harness/
  flow.py            the engine: Field, Step, Flow, dependency hashing, state
  db.py              SQLite schema and helpers
  auth.py            accounts, passwords (scrypt), sessions, roles
  server.py          stdlib HTTP server, router, static files
  api.py             the JSON API
  agent/
    providers.py     offline | ollama | openai-compatible | anthropic
    engine.py        retrieve → propose → critique → backfill
  rag/
    extract.py       PDF/DOCX/PPTX/HTML text extraction, no dependencies
    index.py         FTS5 index, BM25 search
  mdmp/
    doctrine.py      the doctrinal data: tasks, criteria, OPORD skeleton, risk
    flow_def.py      THE FLOW — 7 steps, 66 fields, each mapped to the OPORD
    generators.py    64 offline option generators
    opord.py         assembly and rendering (text, Markdown, HTML, DOCX, JSON)
```

**To add a field**, add a `Field(...)` to a step in `flow_def.py`, declare what
it `depends` on and which OPORD node it feeds via `opord=[...]`, and register a
generator for it in `generators.py`. Nothing else needs to change — the wizard,
the staleness tracking, the OPORD draft, and the exports all pick it up.

**To build a second tool** — troop leading procedures, an after action review,
a targeting cycle — write a new flow definition beside `flow_def.py`. It imports
nothing from the MDMP one.

### The agent loop

For each field:

1. **Retrieve** relevant doctrine passages from the local index.
2. **Propose** candidate options from the configured provider, given the plan so
   far and the retrieved doctrine.
3. **Critique** each candidate against rules for that field — a mission statement
   needs all five Ws and a doctrinal task verb; a COA must be distinguishable
   from the others; a PIR must tie to a decision; an assumption must say how it
   will be confirmed. Failures are dropped or flagged, not passed through.
4. **Backfill** from the offline templates if too few survive.

Step 4 is why this works on an aircraft.

---

## Changing the prompts

Every field's options come from two pieces of text: a **system prompt** (role,
rules, output contract) and a **task template** (the field, the plan context,
the retrieved doctrine). Both ship with working defaults, and both can be
rewritten from the gear icon — ⚙ — that sits next to every step heading and
every field label.

Three scopes, each editable for just this plan or as the server-wide default:

| Gear | Affects |
|---|---|
| Next to a field label, or *⚙ prompt* on an options panel | that one field |
| Next to the step heading | every field in that step |
| *⚙ Prompt for every field*, at the foot of the step | the whole flow |

Resolution runs most-specific-first — field, then step, then global; within each
level, this plan beats the server default — and falls back to the built-in.
The system prompt and the task template resolve **independently**, so you can
rewrite the task template for one field without restating the system prompt.
The editor tells you which rung each half is currently coming from, and only
stores the half you actually changed, so an override higher up the chain keeps
flowing through to the rest.

The editor renders a live preview by asking the server to fill the template
against the real plan, so what you see is what gets sent. Placeholders like
`{field_label}`, `{context}`, and `{passages}` are documented in the editor;
an unknown one is left in place rather than rejected, and a template with an
unbalanced brace degrades to the built-in instead of breaking generation.

Prompts have no effect while the provider is **Offline doctrinal templates** —
those options come from code, not from a model. Every override is recorded in
the plan's activity log, and `GET /api/prompts` lists all of them.

---

## Testing

```bash
python3 scripts/run_tests.py          # everything
python3 scripts/run_tests.py prompts  # one file
```

**Unit and integration — 254 tests.** The flow engine and dependency hashing,
the prompt override chain, option parsing and the critique rules, every offline
generator swept across thousands of plan contexts, retrieval, auth and role
enforcement, OPORD assembly and every export format, and the HTTP API against a
real server including concurrent writers.

**Smoke — 47 checks.** `scripts/smoke_test.py` starts a real server on a
throwaway database and drives the whole tool over HTTP: creates accounts, runs a
plan through all 66 fields from generated options, checks dependency staleness,
generates all three warning orders, moves to production, has a second user claim
and edit a paragraph, verifies that staff cannot approve, and exports the order
in every format.

**Browser — 69 checks.** `scripts/ui_test.py` drives Chromium through the real
interface: the wizard, back-navigation between steps, writing your own option,
the production and OPORD tabs, mobile layout, and the whole prompt editor —
including that an override at one level is inherited rather than copied. This is
the only stage with a dependency (`pip install playwright && playwright install
chromium`); without it the stage reports itself skipped.

---

## Exports

Markdown, plain text, print-ready HTML, Word `.docx`, and the full plan as JSON.
The DOCX writer is built from `zipfile` alone — no Word, no python-docx.

---

## Things it deliberately does not do

- **No classification handling.** Marking, handling, and release decisions belong
  to people, not to a tool.
- **No opinion about your data.** Everything lives in one SQLite file. Copy it,
  back it up, or delete it.
- **No telemetry, no phone home.** If the machine has no network, nothing about
  the tool notices.

## Notes

- Doctrine encoded here is drawn from FM 5-0, FM 6-0, ADP 5-0, FM 3-0,
  ATP 2-01.3, ATP 5-19, and the TC 7-100 series. The seed notes in `corpus/seed/`
  are distilled references, not a substitute for the publications.
- Every scenario name, unit, and place in the generated options is notional.
- Generated text is a starting point for a staff officer, not a product. The
  tool is explicit about this everywhere it matters, and so should you be.
