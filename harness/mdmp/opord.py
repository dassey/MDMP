"""OPORD assembly and rendering.

Nothing here asks the staff to retype anything. Every paragraph is drafted from
the answers already in the plan, using the `opord` mapping declared on each
field in flow_def.py. What the staff does in the production phase is refine and
own paragraphs — not transcribe them.
"""

import html as _html

from harness import db
from harness.mdmp import doctrine as D
from harness.mdmp.flow_def import FLOW


# ------------------------------------------------------------- formatting --

def _fmt(value):
    """Render one answer value as OPORD prose."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        if not value:
            return ""
        if isinstance(value[0], list):          # table
            return "\n".join(" | ".join(str(c) for c in row)
                             for row in value)
        return "\n".join("(%d) %s" % (i + 1, str(v).strip())
                         for i, v in enumerate(value))
    return str(value)


def _answers(plan_id):
    rows = db.q("SELECT field_key, value_json FROM answers "
                "WHERE plan_id=? AND current=1", (plan_id,))
    import json
    out = {}
    for r in rows:
        try:
            out[r["field_key"]] = json.loads(r["value_json"])
        except ValueError:
            out[r["field_key"]] = r["value_json"]
    return out


def draft_body(node, answers):
    """Compose the draft text for one OPORD node from the plan's answers."""
    parts = []
    for field_key in node.get("from", []):
        field = FLOW.field(field_key)
        value = answers.get(field_key)
        text = _fmt(value)
        if not text:
            continue
        label = field.label if field else field_key.replace("_", " ").title()
        # A node fed by a single field just takes its text; several fields get
        # labelled sub-blocks so the reader can see where each came from.
        if len(node.get("from", [])) == 1:
            parts.append(text)
        else:
            parts.append("%s: %s" % (label.upper(), text))
    return "\n\n".join(parts)


# ------------------------------------------------------- section materialise --

def ensure_sections(plan_id):
    """Create the OPORD section rows for a plan, drafting each from answers.

    Existing sections are never overwritten — once a human owns a paragraph,
    the machine stops writing it. Empty ones are refreshed so that going back
    and changing an earlier decision still flows through.
    """
    answers = _answers(plan_id)
    existing = {r["key"]: r for r in
                db.q("SELECT * FROM sections WHERE plan_id=?", (plan_id,))}
    conn = db.connect()
    created = 0
    for node in D.OPORD_SKELETON:
        body = draft_body(node, answers)
        row = existing.get(node["key"])
        if row is None:
            conn.execute(
                "INSERT INTO sections(plan_id,key,kind,title,body,status,"
                "owner_hint,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (plan_id, node["key"], "paragraph", node["title"], body,
                 "drafted" if body else "not_started", node["owner"], db.now()))
            created += 1
        elif row["status"] in ("not_started", "drafted") and body \
                and row["body"] != body:
            conn.execute("UPDATE sections SET body=?, status='drafted', "
                         "updated_at=? WHERE id=?",
                         (body, db.now(), row["id"]))
    for letter, title, owner in D.ANNEXES:
        key = "annex_%s" % letter
        if key not in existing:
            conn.execute(
                "INSERT INTO sections(plan_id,key,kind,title,body,status,"
                "owner_hint,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (plan_id, key, "annex", "Annex %s — %s" % (letter, title), "",
                 "not_started", owner, db.now()))
            created += 1
    conn.commit()
    return created


def sections(plan_id, kind=None):
    order = {n["key"]: i for i, n in enumerate(D.OPORD_SKELETON)}
    rows = db.q("SELECT s.*, u.display_name AS owner_name FROM sections s "
                "LEFT JOIN users u ON u.id = s.owner_id "
                "WHERE s.plan_id=?" + (" AND s.kind=?" if kind else ""),
                (plan_id, kind) if kind else (plan_id,))
    rows.sort(key=lambda r: (r["kind"] != "paragraph",
                             order.get(r["key"], 999), r["key"]))
    return rows


# ------------------------------------------------------------------ render --

def _plan(plan_id):
    return db.q1("SELECT * FROM plans WHERE id=?", (plan_id,))


def build_document(plan_id):
    """Return an ordered list of rendered OPORD nodes."""
    rows = {r["key"]: r for r in sections(plan_id)}
    answers = _answers(plan_id)
    doc = []
    for node in D.OPORD_SKELETON:
        row = rows.get(node["key"])
        body = (row["body"] if row else "") or draft_body(node, answers)
        doc.append({
            "key": node["key"], "num": node["num"], "title": node["title"],
            "level": node["level"], "body": body,
            "status": row["status"] if row else "not_started",
            "container": bool(node.get("container")),
            "owner": row["owner_name"] if row and row.get("owner_name")
            else D.staff_section_name(node["owner"]),
        })
    annexes = []
    for letter, title, owner in D.ANNEXES:
        row = rows.get("annex_%s" % letter)
        annexes.append({
            "key": "annex_%s" % letter, "letter": letter, "title": title,
            "body": (row["body"] if row else ""),
            "status": row["status"] if row else "not_started",
            "owner": row["owner_name"] if row and row.get("owner_name")
            else D.staff_section_name(owner),
        })
    return doc, annexes


def render_text(plan_id):
    plan = _plan(plan_id)
    doc, annexes = build_document(plan_id)
    answers = _answers(plan_id)
    unit = answers.get("unit_designation") or "(unit)"

    lines = []
    lines.append("OPERATION ORDER — %s" % (plan["name"] if plan else ""))
    lines.append("Issuing headquarters: %s" % unit)
    lines.append("=" * 72)
    lines.append("")
    for node in doc:
        if node["num"]:
            prefix = "%s " % node["num"]
            indent = "" if node["level"] == 0 else "   "
        else:
            prefix = ""
            indent = ""
        heading = "%s%s%s" % (indent, prefix, node["title"].upper()
                              if node["level"] == 0 else node["title"])
        lines.append(heading)
        body = node["body"].strip()
        if body:
            for para in body.split("\n"):
                lines.append("%s    %s" % (indent, para) if para else "")
        elif not node["container"]:
            lines.append("%s    (to be completed)" % indent)
        lines.append("")
    lines.append("ANNEXES")
    for a in annexes:
        mark = "X" if a["body"].strip() else " "
        lines.append("  [%s] Annex %s — %s (%s)"
                     % (mark, a["letter"], a["title"], a["owner"]))
    lines.append("")
    lines.append("ACKNOWLEDGE.")
    return "\n".join(lines)


def render_markdown(plan_id):
    plan = _plan(plan_id)
    doc, annexes = build_document(plan_id)
    answers = _answers(plan_id)
    out = ["# Operation Order — %s" % (plan["name"] if plan else ""), ""]
    out.append("**Issuing headquarters:** %s"
               % (answers.get("unit_designation") or "(unit)"))
    out.append("")
    for node in doc:
        hashes = "##" if node["level"] == 0 else "###"
        num = (node["num"] + " ") if node["num"] else ""
        out.append("%s %s%s" % (hashes, num, node["title"]))
        out.append("")
        if node["body"].strip():
            out.append(node["body"].strip())
        elif not node["container"]:
            out.append("_(to be completed)_")
        out.append("")
    out.append("## Annexes")
    out.append("")
    for a in annexes:
        state = "drafted" if a["body"].strip() else "not started"
        out.append("- **Annex %s — %s** (%s) — %s"
                   % (a["letter"], a["title"], a["owner"], state))
    out.append("")
    out.append("ACKNOWLEDGE.")
    return "\n".join(out)


def render_html(plan_id):
    plan = _plan(plan_id)
    doc, annexes = build_document(plan_id)
    answers = _answers(plan_id)
    esc = _html.escape

    parts = ["""<!doctype html><html><head><meta charset="utf-8">
<title>OPORD — %s</title>
<style>
 body{font:12pt/1.45 Georgia,'Times New Roman',serif;max-width:47em;
      margin:3em auto;padding:0 1.5em;color:#111}
 h1{font-size:17pt;text-align:center;letter-spacing:.04em}
 h2{font-size:13pt;margin-top:1.6em;border-bottom:1px solid #999;
    padding-bottom:.2em}
 h3{font-size:12pt;margin-top:1.1em;font-weight:600}
 .meta{text-align:center;color:#444;margin-bottom:2.5em}
 .body{white-space:pre-wrap;margin:.35em 0 .9em 1.2em}
 .todo{color:#a00;font-style:italic}
 .owner{float:right;font-size:9pt;color:#666;font-style:italic}
 ul{margin-left:1em} li{margin:.2em 0}
 @media print{body{margin:0;max-width:none} .owner{display:none}}
</style></head><body>""" % esc(plan["name"] if plan else "OPORD")]
    parts.append("<h1>Operation Order</h1>")
    parts.append('<div class="meta">%s<br>%s</div>'
                 % (esc(plan["name"] if plan else ""),
                    esc(answers.get("unit_designation") or "")))
    for node in doc:
        tag = "h2" if node["level"] == 0 else "h3"
        num = (esc(node["num"]) + " ") if node["num"] else ""
        parts.append('<%s><span class="owner">%s</span>%s%s</%s>'
                     % (tag, esc(node["owner"]), num, esc(node["title"]), tag))
        body = node["body"].strip()
        if body:
            parts.append('<div class="body">%s</div>' % esc(body))
        elif not node["container"]:
            parts.append('<div class="body todo">(to be completed)</div>')
    parts.append("<h2>Annexes</h2><ul>")
    for a in annexes:
        state = "drafted" if a["body"].strip() else "not started"
        parts.append("<li><b>Annex %s — %s</b> (%s) — %s</li>"
                     % (esc(a["letter"]), esc(a["title"]), esc(a["owner"]),
                        state))
    parts.append("</ul><p>ACKNOWLEDGE.</p></body></html>")
    return "".join(parts)


def render_docx(plan_id):
    """Minimal Office Open XML .docx, built with zipfile only.

    Not a full Word feature set — headings, paragraphs, and a title. That is
    what an order needs, and it opens in Word, LibreOffice, and Google Docs.
    """
    import io
    import zipfile

    doc, annexes = build_document(plan_id)
    plan = _plan(plan_id)
    answers = _answers(plan_id)

    def esc(t):
        return (str(t).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))

    def para(text, style=None, bold=False):
        ppr = ""
        if style:
            ppr += '<w:pStyle w:val="%s"/>' % style
        rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
        runs = ""
        for i, line in enumerate(str(text).split("\n")):
            if i:
                runs += "<w:r><w:br/></w:r>"
            runs += '<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>' % (
                rpr, esc(line))
        return "<w:p><w:pPr>%s</w:pPr>%s</w:p>" % (ppr, runs)

    body = [para("OPERATION ORDER", "Title", True),
            para(plan["name"] if plan else "", None, True),
            para(answers.get("unit_designation") or "")]
    for node in doc:
        num = (node["num"] + " ") if node["num"] else ""
        body.append(para(num + node["title"],
                         "Heading1" if node["level"] == 0 else "Heading2",
                         True))
        text = node["body"].strip()
        if text or not node["container"]:
            body.append(para(text or "(to be completed)"))
    body.append(para("ANNEXES", "Heading1", True))
    for a in annexes:
        body.append(para("Annex %s — %s (%s)%s"
                         % (a["letter"], a["title"], a["owner"],
                            "" if a["body"].strip() else " — not started")))
    body.append(para("ACKNOWLEDGE."))

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main"><w:body>%s'
        '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>'
        '</w:sectPr></w:body></w:document>' % "".join(body))

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
        'content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats'
        '-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>')
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        'relationships"><Relationship Id="rId1" Type="http://schemas.'
        'openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>')

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)
    return buf.getvalue()


def completeness(plan_id):
    """How much of the order is actually done."""
    doc, annexes = build_document(plan_id)
    real = [n for n in doc if not n["container"]]
    filled = sum(1 for n in real if n["body"].strip())
    approved = sum(1 for n in real if n["status"] == "approved")
    return {"paragraphs": len(real), "filled": filled, "approved": approved,
            "annexes": len(annexes),
            "annexes_started": sum(1 for a in annexes if a["body"].strip())}
