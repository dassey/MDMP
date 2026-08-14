"""Prompt templates and the override chain.

Every field's options are generated from two pieces of text: a **system prompt**
that sets the role and the output contract, and a **task template** that carries
the field, the plan context, and the retrieved doctrine. Both ship with sensible
defaults and both can be replaced — for one field, for a whole step, or for
everything — either just for one plan or as the server-wide default.

Resolution, most specific first:

    field override, this plan
    field override, server default
    step override,  this plan
    step override,  server default
    global override, this plan
    global override, server default
    built-in default

`system` and `template` resolve independently, so you can override the task
template for one field without also having to restate the system prompt.
"""

import re

from harness import db

# --------------------------------------------------------------- defaults --

DEFAULT_SYSTEM = """You are a staff planning assistant supporting a US Army \
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

DEFAULT_TEMPLATE = """PLANNING STEP: {step_num}. {step_title}
FIELD: {field_label}
WHAT THIS FIELD IS: {field_plain}
DOCTRINAL NOTE: {field_doctrine}

PLAN CONTEXT (decisions already made):
{context}

{passages}

TASK: Produce {n} distinct candidate options for this field.
{kind_instruction}{columns}"""

# Every placeholder the template may use, with the explanation shown in the
# editor. Anything not in this list is left alone rather than erroring.
PLACEHOLDERS = [
    ("step_num", "The step number, 1 through 7."),
    ("step_title", "The step's title, e.g. 'Mission Analysis'."),
    ("step_purpose", "The doctrinal purpose of the step."),
    ("field_key", "The field's internal key."),
    ("field_label", "The field's title as the planner sees it."),
    ("field_plain", "The plain-English explanation of the field."),
    ("field_doctrine", "The doctrinal note and reference for the field."),
    ("field_kind", "choice, multi, text, items, or table."),
    ("context", "Every decision already made that this field depends on."),
    ("passages", "Doctrine passages retrieved from the local library."),
    ("n", "How many options to produce."),
    ("kind_instruction", "How to shape `value` for this field's kind."),
    ("columns", "Column names, for table fields only."),
    ("unit", "The unit designation, if it has been chosen."),
    ("operation_type", "The type of operation, if it has been chosen."),
]

LEVELS = ("field", "step", "global")


# ------------------------------------------------------------- resolution --

def _row(level, key, plan_id):
    return db.q1(
        "SELECT * FROM prompts WHERE level=? AND scope_key=? AND "
        + ("plan_id=?" if plan_id else "plan_id IS NULL"),
        (level, key, plan_id) if plan_id else (level, key))


def _chain(plan_id, step_key, field_key, skip=None):
    """The lookup order, most specific first, as (label, row) pairs.

    `skip` is an optional (level, key, plan_id) naming one rung to pretend is
    empty — used to answer "what would be in force here if I had not set
    anything at this exact scope?".
    """
    out = []
    for level, key in (("field", field_key), ("step", step_key), ("global", "")):
        if key is None:
            continue
        for scope, pid in (("this plan", plan_id), ("server default", None)):
            row = None if skip == (level, key, pid) else _row(level, key, pid)
            out.append(("%s override (%s)" % (level, scope), level, key, pid, row))
    return out


def resolve(plan_id, step_key, field_key, skip=None):
    """Effective system prompt and task template, plus where each came from."""
    system, system_src = DEFAULT_SYSTEM, "built-in default"
    template, template_src = DEFAULT_TEMPLATE, "built-in default"
    for label, _level, _key, _pid, row in _chain(plan_id, step_key, field_key,
                                                 skip):
        if row:
            if system_src == "built-in default" and (row["system"] or "").strip():
                system, system_src = row["system"], label
            if template_src == "built-in default" and (row["template"] or "").strip():
                template, template_src = row["template"], label
    return {"system": system, "system_source": system_src,
            "template": template, "template_source": template_src}


def overrides_for(plan_id, step_key, field_key):
    """Which override rows exist along the chain — used to paint the editor."""
    out = []
    for label, level, key, pid, row in _chain(plan_id, step_key, field_key):
        has_system = bool(row and (row["system"] or "").strip())
        has_template = bool(row and (row["template"] or "").strip())
        if has_system or has_template:
            out.append({"label": label, "level": level, "key": key,
                        "plan_scoped": bool(pid),
                        "has_system": has_system,
                        "has_template": has_template,
                        "updated_at": row["updated_at"]})
    return out


def save(level, key, plan_id, system, template, user_id):
    if level not in LEVELS:
        raise ValueError("unknown prompt level: %s" % level)
    if level == "global":
        key = ""
    if not (system or "").strip() and not (template or "").strip():
        # Nothing left to override — drop the row rather than leave a hollow
        # one that the editor would report as "this plan has an override".
        clear(level, key, plan_id)
        return
    existing = _row(level, key, plan_id)
    now = db.now()
    if existing:
        db.ex("UPDATE prompts SET system=?, template=?, updated_by=?, "
              "updated_at=? WHERE id=?",
              (system or "", template or "", user_id, now, existing["id"]))
    else:
        db.ex("INSERT INTO prompts(level,scope_key,plan_id,system,template,"
              "updated_by,updated_at) VALUES(?,?,?,?,?,?,?)",
              (level, key, plan_id, system or "", template or "", user_id, now))


def clear(level, key, plan_id):
    if level == "global":
        key = ""
    db.ex("DELETE FROM prompts WHERE level=? AND scope_key=? AND "
          + ("plan_id=?" if plan_id else "plan_id IS NULL"),
          (level, key, plan_id) if plan_id else (level, key))


def only_changes(level, key, plan_id, step_key, field_key, system, template):
    """Strip the halves the editor merely echoed back.

    The editor pre-fills both boxes with the text currently in force, wherever
    it came from. Storing an unedited box would silently pin it here — so a
    planner who tweaks the task template would also freeze the system prompt
    against later changes higher up the chain. Only what actually differs from
    the inherited text is worth storing.
    """
    base = resolve(plan_id, step_key, field_key,
                   skip=(level, key, plan_id))
    if (system or "").strip() == base["system"].strip():
        system = ""
    if (template or "").strip() == base["template"].strip():
        template = ""
    return system, template


def list_all(plan_id=None):
    rows = db.q(
        "SELECT p.*, u.display_name FROM prompts p "
        "LEFT JOIN users u ON u.id=p.updated_by "
        "ORDER BY p.level, p.scope_key")
    for r in rows:
        r["plan_scoped"] = r["plan_id"] is not None
    return rows


# ---------------------------------------------------------------- rendering --

class _Safe(dict):
    """Leave unknown placeholders alone instead of blowing up on them."""

    def __missing__(self, key):
        return "{%s}" % key


def render(template, values):
    """Fill a template. A broken template degrades, it does not raise."""
    try:
        return template.format_map(_Safe(values))
    except (ValueError, IndexError, KeyError, AttributeError) as exc:
        # An unbalanced brace is the usual cause. Show it rather than failing.
        return ("%s\n\n[the task template could not be rendered: %s — the "
                "built-in default was used instead]\n\n%s"
                % (DEFAULT_TEMPLATE.format_map(_Safe(values)), exc, template))


def context_block(ctx):
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


def passages_block(passages):
    if not passages:
        return ""
    out = ["RELEVANT DOCTRINE FROM THE LOCAL LIBRARY:"]
    for p in passages:
        out.append("[%s] %s" % (p["title"], p["snippet"]))
    return "\n".join(out)


def kind_instruction(field):
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


def values_for(field, step, ctx, passages, n):
    return {
        "step_num": step.num if step else "",
        "step_title": step.title if step else "",
        "step_purpose": step.purpose if step else "",
        "field_key": field.key,
        "field_label": field.label,
        "field_plain": field.plain or field.label,
        "field_doctrine": field.doctrine or "—",
        "field_kind": field.kind,
        "context": context_block(ctx),
        "passages": passages_block(passages),
        "n": n,
        "kind_instruction": kind_instruction(field),
        "columns": ("\nColumns: %s" % " | ".join(field.columns)
                    if field.columns else ""),
        "unit": ctx.get("unit_designation", ""),
        "operation_type": ctx.get("operation_type", ""),
    }


def build(plan_id, field, step, ctx, passages, n):
    """Return (system, user_prompt, resolution) for one generation call."""
    res = resolve(plan_id, step.key if step else None, field.key)
    values = values_for(field, step, ctx, passages, n)
    return res["system"], render(res["template"], values), res


def used_placeholders(template):
    return sorted(set(re.findall(r"\{(\w+)\}", template or "")))


def unknown_placeholders(template):
    known = {name for name, _desc in PLACEHOLDERS}
    return [p for p in used_placeholders(template) if p not in known]
