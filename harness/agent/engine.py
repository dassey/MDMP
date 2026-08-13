"""The agentic loop: propose, critique, repair, cite.

For every field the engine does the same four things:

  1. RETRIEVE  pull the most relevant doctrine passages for this field from the
               local corpus (BM25 over SQLite FTS5 — no embeddings, no GPU).
  2. PROPOSE   ask the configured provider for candidate options, giving it the
               plan so far and the retrieved doctrine. On a local model this is
               a few seconds; offline it is instant.
  3. CRITIQUE  score every candidate against doctrinal rules for that field —
               does a mission statement have all five Ws, is a COA
               distinguishable from the one before it, does a PIR tie to a
               decision. Bad candidates are dropped or flagged, not silently
               passed through.
  4. BACKFILL  if fewer than the requested number survive, top up from the
               offline doctrinal templates so the staff is never handed an
               empty screen.

Step 4 is the reason this thing is usable on an aircraft.
"""

import re

from harness.agent import providers
from harness.mdmp import doctrine as D
from harness.rag import index as rag

SYSTEM = """You are a staff planning assistant supporting a US Army \
headquarters running the military decision-making process (MDMP). You produce \
candidate options for one field of a planning product at a time.

Rules:
- Every option must be doctrinally sound per FM 5-0, FM 6-0, ADP 5-0, and \
FM 3-0, and must fit the plan context you are given.
- Options must be genuinely different from one another. Do not return the same \
answer three times with different wording.
- Write in the voice of a staff product: short paragraphs, complete sentences, \
no marketing language, no hedging.
- All scenarios are notional. Use only the notional place and unit names \
present in the context. Never reference real current operations or real units \
in active deployment.
- The `rationale` explains why a planner would choose this option over the \
others, in one or two sentences.
- Use `flags` for a risk or trade-off the planner should see before choosing \
(for example "gives up ground early" or "requires assets we do not hold").

Return JSON only, in this shape:
{"options": [{"label": "...", "value": "...", "rationale": "...", \
"flags": ["..."]}]}"""


# ------------------------------------------------------------- critique ----

_FIVE_W = [
    (r"\b(NLT|no later than|not later than|at \d{6}|H-Hour|H\+|D-Day|D\+|\d{6}Z)\b",
     "no clear WHEN — add a time or a trigger"),
    (r"\b(in order to|to enable|to allow|to prevent|to protect|to deny)\b",
     "no WHY — a mission statement needs a purpose"),
]


def _critique(field, option, prior_values):
    """Return a list of problems with this candidate. Empty list means clean."""
    problems = []
    value = option.get("value")
    text = value if isinstance(value, str) else " ".join(map(str, value or []))
    text = (text or "").strip()

    if not text:
        return problems  # a deliberate "write your own" placeholder

    if field.kind in ("text",) and len(text) < 40:
        problems.append("too short to be usable as a staff product")

    key = field.key

    if key == "mission_statement":
        for pattern, msg in _FIVE_W:
            if not re.search(pattern, text, re.I):
                problems.append(msg)
        verbs = [v for v, _d in D.all_task_verbs()]
        if not any(re.search(r"\b%s" % re.escape(v.split("_")[0]), text, re.I)
                   for v in verbs):
            problems.append("no doctrinal task verb")

    if key.startswith("coa_") and key[4:].isdigit():
        for other in prior_values:
            if isinstance(other, str) and other.strip():
                if _similarity(text, other) > 0.72:
                    problems.append(
                        "not distinguishable from another COA — same approach "
                        "in different words")
                    break
        if len(text) > 60 and not re.search(
                r"(decisive operation|main effort|DECISIVE)", text, re.I):
            problems.append("does not name the decisive operation or main effort")

    if key == "ccir_pir":
        if not re.search(r"\?", text) and not re.search(r"\b(will|is|are|does|"
                                                        r"where|when|what)\b",
                                                        text, re.I):
            problems.append("a PIR should be a question")
        if not re.search(r"(decision|decide|commit|shift|trigger|DP)", text, re.I):
            problems.append("no linked decision — if nothing changes based on "
                            "the answer, it is not a PIR")

    if key == "assumptions":
        if not re.search(r"(confirm|deny|verify|PIR)", text, re.I):
            problems.append("an assumption must say how it will be confirmed "
                            "or denied")

    if key == "intent_end_state":
        for word in ("friendly", "threat", "enemy", "terrain"):
            if word in text.lower():
                break
        else:
            problems.append("end state should describe friendly, threat, "
                            "terrain, and civil conditions")

    if key in ("intent_key_tasks",) and re.search(
            r"\b(1st|2d|2nd|3d|3rd|A Company|B Company|Alpha|Bravo)\b", text):
        problems.append("key tasks are conditions for the force, not tasks to "
                        "a named unit")

    return problems


def _similarity(a, b):
    """Cheap token-overlap similarity; good enough to catch a re-shaded COA."""
    ta = set(re.findall(r"[a-z]{4,}", a.lower()))
    tb = set(re.findall(r"[a-z]{4,}", b.lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / float(min(len(ta), len(tb)))


# ---------------------------------------------------------------- prompt ----

def _context_block(ctx):
    if not ctx:
        return "(no prior decisions recorded yet)"
    lines = []
    for k, v in ctx.items():
        if isinstance(v, list):
            if v and isinstance(v[0], list):
                rendered = "; ".join(" | ".join(map(str, row)) for row in v[:6])
            else:
                rendered = "; ".join(str(x) for x in v[:8])
        else:
            rendered = str(v)
        if len(rendered) > 700:
            rendered = rendered[:700] + " …"
        lines.append("- %s: %s" % (k.replace("_", " "), rendered))
    return "\n".join(lines)


def _kind_instruction(field):
    if field.kind == "choice":
        return ("Each option's `value` is the full text of one choice. The "
                "planner will pick exactly one.")
    if field.kind == "multi":
        return ("Each option's `value` is one selectable entry. The planner "
                "will pick several.")
    if field.kind == "items":
        return ("Each option's `value` is ONE list entry, written as a "
                "complete sentence or a short labelled statement. The planner "
                "assembles a list from several of them.")
    if field.kind == "table":
        return ("Each option's `value` is one table row, written as a single "
                "string with the cells separated by ' | ' in this column "
                "order: %s." % ", ".join(field.columns))
    return ("Each option's `value` is a complete draft of this field — a "
            "paragraph or several, ready to paste into the order.")


def build_prompt(field, step, ctx, passages, n):
    parts = [
        "PLANNING STEP: %d. %s" % (step.num, step.title),
        "FIELD: %s" % field.label,
        "WHAT THIS FIELD IS: %s" % (field.plain or field.label),
        "DOCTRINAL NOTE: %s" % (field.doctrine or "—"),
        "",
        "PLAN CONTEXT (decisions already made):",
        _context_block(ctx),
    ]
    if passages:
        parts += ["", "RELEVANT DOCTRINE FROM THE LOCAL LIBRARY:"]
        for p in passages:
            parts.append("[%s] %s" % (p["title"], p["snippet"]))
    parts += [
        "",
        "TASK: Produce %d distinct candidate options for this field." % n,
        _kind_instruction(field),
    ]
    if field.columns:
        parts.append("Columns: %s" % " | ".join(field.columns))
    return "\n".join(parts)


# ---------------------------------------------------------------- engine ----

class Engine:
    def __init__(self, provider=None):
        self.provider = provider or providers.build()

    def describe(self):
        return self.provider.describe()

    def generate(self, flow, field, ctx, n=5, prior_values=()):
        """Return (options, meta). Never raises, never returns an empty list."""
        step = flow.step_of(field.key)
        meta = {"provider": self.provider.name, "notes": []}

        passages = []
        try:
            query = " ".join(filter(None, [field.label, field.doctrine[:120]]))
            passages = rag.search(query, limit=4)
        except Exception as exc:
            meta["notes"].append("doctrine search unavailable: %s" % exc)

        options = []
        if self.provider.name != "offline":
            try:
                prompt = build_prompt(field, step, ctx, passages, n)
                raw = self.provider.options(SYSTEM, prompt, n)
                options = self._normalise(raw, field)
            except providers.ProviderError as exc:
                meta["notes"].append("%s unavailable (%s) — using offline "
                                     "doctrinal templates"
                                     % (self.provider.name, exc))
                meta["provider"] = "offline"
            except Exception as exc:
                meta["notes"].append("provider error (%s) — using offline "
                                     "doctrinal templates" % exc)
                meta["provider"] = "offline"

        # ---- critique -------------------------------------------------
        kept = []
        for o in options:
            problems = _critique(field, o, prior_values)
            hard = [p for p in problems if "not distinguishable" in p
                    or "too short" in p]
            if hard:
                continue
            if problems:
                o["flags"] = list(o.get("flags") or []) + \
                    ["check: " + p for p in problems]
            kept.append(o)

        # ---- backfill from doctrine templates ---------------------------
        if len(kept) < max(2, n // 2):
            fill = providers.offline_options(field.gen, ctx, n)
            have = {self._sig(o) for o in kept}
            for o in fill:
                if self._sig(o) not in have:
                    kept.append(o)
                    have.add(self._sig(o))
                if len(kept) >= n + 1:
                    break
            if options:
                meta["notes"].append("topped up with doctrinal templates")

        for i, o in enumerate(kept):
            o.setdefault("id", "opt-%s-%d" % (field.key, i))
            o.setdefault("provider", meta["provider"])
            o.setdefault("flags", [])
            o["cites"] = [{"title": p["title"], "snippet": p["snippet"][:220]}
                          for p in passages[:2]]

        meta["passages"] = [{"title": p["title"], "snippet": p["snippet"][:400]}
                            for p in passages]
        return kept, meta

    @staticmethod
    def _sig(option):
        v = option.get("value")
        if isinstance(v, list):
            v = " | ".join(map(str, v))
        return (str(v) or "")[:120].strip().lower()

    @staticmethod
    def _normalise(raw, field):
        """Coerce model output into the shape the field expects."""
        out = []
        for o in raw:
            value = o.get("value")
            if field.kind == "table" and isinstance(value, str):
                cells = [c.strip() for c in value.split("|")]
                width = len(field.columns) or len(cells)
                cells = (cells + [""] * width)[:width]
                value = cells
            if field.kind == "table" and isinstance(value, list):
                width = len(field.columns) or len(value)
                value = ([str(c) for c in value] + [""] * width)[:width]
            if field.kind != "table" and isinstance(value, list):
                value = "\n".join(str(x) for x in value)
            out.append({
                "label": o.get("label") or "Option",
                "value": value,
                "rationale": o.get("rationale") or "",
                "flags": list(o.get("flags") or []),
            })
        return out
