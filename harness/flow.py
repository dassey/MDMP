"""The harness: a declarative flow engine.

A *flow* is an ordered list of *steps*; a step holds *fields*. A field is a
single decision the staff has to make. The engine's job is to know, at any
moment:

  * what the plan currently says (the answers),
  * what each field depends on,
  * and therefore which answers have gone stale because someone went back and
    changed something upstream.

Nothing in this module knows anything about MDMP. The MDMP tool is one flow
definition (see harness/mdmp/flow_def.py); another flow — troop leading
procedures, an after action review, a targeting cycle — is a second file that
imports nothing from the first.

Field kinds
-----------
choice   pick exactly one generated option (or write your own)
multi    pick any number of generated options (or write your own)
text     a paragraph; generated drafts are starting points, freely edited
items    an ordered list of short entries, each one selected or written
table    rows with fixed columns; candidate rows are generated
"""

import hashlib
import json

KINDS = ("choice", "multi", "text", "items", "table")


class Field:
    def __init__(self, key, label, kind="text", gen=None, plain="", doctrine="",
                 depends=(), opord=(), required=True, columns=(), placeholder="",
                 min_items=0, owner="s3", example=""):
        if kind not in KINDS:
            raise ValueError("unknown field kind: %s" % kind)
        self.key = key
        self.label = label
        self.kind = kind
        self.gen = gen or key
        self.plain = plain            # plain-English explanation for a novice
        self.doctrine = doctrine      # doctrinal note / reference
        self.depends = list(depends)
        self.opord = list(opord)      # OPORD node keys this feeds
        self.required = required
        self.columns = list(columns)  # for kind == "table"
        self.placeholder = placeholder
        self.min_items = min_items
        self.owner = owner            # default staff section
        self.example = example

    def to_dict(self):
        return {
            "key": self.key, "label": self.label, "kind": self.kind,
            "plain": self.plain, "doctrine": self.doctrine,
            "depends": self.depends, "opord": self.opord,
            "required": self.required, "columns": self.columns,
            "placeholder": self.placeholder, "min_items": self.min_items,
            "owner": self.owner, "example": self.example,
        }


class Step:
    def __init__(self, key, num, title, plain="", purpose="", outputs=(),
                 fields=(), warnord=None):
        self.key = key
        self.num = num
        self.title = title
        self.plain = plain
        self.purpose = purpose
        self.outputs = list(outputs)
        self.fields = list(fields)
        self.warnord = warnord  # WARNORD number issued at the end of this step

    def field(self, key):
        for f in self.fields:
            if f.key == key:
                return f
        return None

    def to_dict(self):
        return {
            "key": self.key, "num": self.num, "title": self.title,
            "plain": self.plain, "purpose": self.purpose,
            "outputs": self.outputs, "warnord": self.warnord,
            "fields": [f.to_dict() for f in self.fields],
        }


class Flow:
    def __init__(self, flow_id, title, description, steps):
        self.id = flow_id
        self.title = title
        self.description = description
        self.steps = list(steps)
        self._fields = {}
        for s in self.steps:
            for f in s.fields:
                if f.key in self._fields:
                    raise ValueError("duplicate field key: %s" % f.key)
                self._fields[f.key] = (s, f)

    # -- lookups ---------------------------------------------------------
    def step(self, key):
        for s in self.steps:
            if s.key == key:
                return s
        return None

    def field(self, key):
        entry = self._fields.get(key)
        return entry[1] if entry else None

    def step_of(self, field_key):
        entry = self._fields.get(field_key)
        return entry[0] if entry else None

    def all_fields(self):
        return [f for s in self.steps for f in s.fields]

    def dependents_of(self, field_key):
        """Fields that consume this field, directly or transitively."""
        direct = [f.key for f in self.all_fields() if field_key in f.depends]
        seen = set(direct)
        queue = list(direct)
        while queue:
            cur = queue.pop()
            for f in self.all_fields():
                if cur in f.depends and f.key not in seen:
                    seen.add(f.key)
                    queue.append(f.key)
        return sorted(seen)

    def to_dict(self):
        return {
            "id": self.id, "title": self.title, "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
        }


# ------------------------------------------------------------------ state --

def dep_hash(field, answers):
    """Stable hash of the values a field was generated/answered against.

    `answers` maps field_key -> value (already decoded from JSON).
    """
    payload = []
    for key in sorted(field.depends):
        payload.append((key, answers.get(key)))
    blob = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def is_empty(value):
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    return False


def field_status(field, answers, stored_hashes):
    """answered | stale | empty for a single field."""
    value = answers.get(field.key)
    if is_empty(value):
        return "empty"
    if not field.depends:
        return "answered"
    if stored_hashes.get(field.key) != dep_hash(field, answers):
        return "stale"
    return "answered"


def step_status(step, answers, stored_hashes):
    """Roll a step up from its fields.

    complete  every required field answered and current
    stale     something upstream changed under an answer here
    partial   some answers present
    empty     nothing yet
    """
    statuses = [field_status(f, answers, stored_hashes) for f in step.fields]
    required = [field_status(f, answers, stored_hashes)
                for f in step.fields if f.required]
    if "stale" in statuses:
        return "stale"
    if required and all(s == "answered" for s in required):
        return "complete"
    if any(s == "answered" for s in statuses):
        return "partial"
    return "empty"


def flow_state(flow, answers, stored_hashes):
    """Everything the UI needs to paint the step rail and gate the wizard."""
    steps = []
    for s in flow.steps:
        fields = {}
        for f in s.fields:
            fields[f.key] = field_status(f, answers, stored_hashes)
        steps.append({
            "key": s.key, "num": s.num, "title": s.title,
            "status": step_status(s, answers, stored_hashes),
            "fields": fields,
        })
    complete = all(x["status"] == "complete" for x in steps)
    # First step that is not complete — where "resume" lands.
    current = next((x["key"] for x in steps if x["status"] != "complete"),
                   flow.steps[-1].key)
    return {"steps": steps, "complete": complete, "current": current}


def context_for(flow, field, answers):
    """The subset of the plan a generator should see for this field.

    Dependencies first (those are the declared inputs), then a little ambient
    context so generated options read like they belong to this plan rather than
    to a generic one.
    """
    ctx = {}
    for key in field.depends:
        if not is_empty(answers.get(key)):
            ctx[key] = answers[key]
    for key in ("echelon", "unit_designation", "operation_type", "oe_framework",
                "opfor_posture", "mission_statement", "intent_purpose"):
        if key not in ctx and not is_empty(answers.get(key)):
            ctx[key] = answers[key]
    return ctx
