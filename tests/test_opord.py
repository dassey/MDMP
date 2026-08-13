"""OPORD assembly, section ownership, and every renderer."""

import io
import json
import unittest
import zipfile

from tests.base import DbCase

from harness import db
from harness.mdmp import doctrine as D
from harness.mdmp import opord
from harness.mdmp.flow_def import FLOW


class TestSkeleton(unittest.TestCase):
    def test_five_paragraphs_are_present_and_numbered(self):
        top = [n for n in D.OPORD_SKELETON if n["level"] == 0 and n["num"]]
        self.assertEqual([n["num"] for n in top],
                         ["1.", "2.", "3.", "4.", "5."])
        self.assertEqual([n["title"] for n in top],
                         ["Situation", "Mission", "Execution", "Sustainment",
                          "Command and Signal"])

    def test_every_node_names_an_owning_section(self):
        keys = {k for k, _n, _d in D.STAFF_SECTIONS}
        for n in D.OPORD_SKELETON:
            self.assertIn(n["owner"], keys, n["key"])

    def test_every_node_has_guidance_for_the_drafter(self):
        for n in D.OPORD_SKELETON:
            self.assertTrue(n["guidance"].strip(), n["key"])

    def test_node_keys_are_unique(self):
        keys = [n["key"] for n in D.OPORD_SKELETON]
        self.assertEqual(len(keys), len(set(keys)))

    def test_annex_letters_are_unique_and_sensible(self):
        letters = [a[0] for a in D.ANNEXES]
        self.assertEqual(len(letters), len(set(letters)))
        self.assertEqual(letters[0], "A")
        self.assertIn("Task Organization", D.ANNEXES[0][1])

    def test_risk_matrix_is_complete(self):
        for sev in D.RISK_SEVERITY:
            for prob in D.RISK_PROBABILITY:
                self.assertIn(D.risk_level(sev, prob),
                              ["Extremely High", "High", "Moderate", "Low"])
        self.assertEqual(D.risk_level("nonsense", "nonsense"), "Unknown")

    def test_risk_increases_with_severity_and_probability(self):
        order = ["Low", "Moderate", "High", "Extremely High"]
        self.assertGreater(order.index(D.risk_level("Catastrophic", "Frequent")),
                           order.index(D.risk_level("Negligible", "Unlikely")))

    def test_task_verb_lookup(self):
        self.assertIn("combat-ineffective", D.task_verb_definition("destroy"))
        self.assertEqual(D.task_verb_definition("wombat"), "")

    def test_staff_section_names_resolve(self):
        self.assertEqual(D.staff_section_name("s2"), "S-2 (Intelligence)")
        self.assertEqual(D.staff_section_name("zz"), "ZZ")


class TestAssembly(DbCase):
    def setUp(self):
        super().setUp()
        self.pid = self.make_plan("OPERATION TEST ANVIL")

    def fill(self):
        """Answer every field from the offline generators."""
        from harness.agent import engine as E
        from harness.flow import context_for
        eng = E.Engine()
        vals = {}
        for step in FLOW.steps:
            for f in step.fields:
                opts, _m = eng.generate(FLOW, f, context_for(FLOW, f, vals), 5,
                                        plan_id=self.pid)
                usable = [o for o in opts
                          if not (isinstance(o["value"], str)
                                  and not o["value"].strip())]
                if f.kind in ("items", "multi"):
                    v = [o["value"] for o in usable[:3]]
                elif f.kind == "table":
                    v = [o["value"] if isinstance(o["value"], list)
                         else [o["value"]] for o in usable[:4]]
                else:
                    v = usable[0]["value"]
                vals[f.key] = v
                self.answer(self.pid, f.key, v)
        return vals

    def test_sections_are_created_once(self):
        created = opord.ensure_sections(self.pid)
        again = opord.ensure_sections(self.pid)
        self.assertEqual(created, len(D.OPORD_SKELETON) + len(D.ANNEXES))
        self.assertEqual(again, 0)

    def test_answers_flow_into_the_draft(self):
        self.answer(self.pid, "mission_statement",
                    "2d BCT attacks at 010500Z to seize OBJECTIVE FALCON.")
        opord.ensure_sections(self.pid)
        row = db.q1("SELECT body FROM sections WHERE plan_id=? AND key='p2'",
                    (self.pid,))
        self.assertIn("OBJECTIVE FALCON", row["body"])

    def test_editing_an_answer_refreshes_an_untouched_paragraph(self):
        self.answer(self.pid, "mission_statement", "First version of it.")
        opord.ensure_sections(self.pid)
        self.answer(self.pid, "mission_statement", "Second version of it.")
        opord.ensure_sections(self.pid)
        row = db.q1("SELECT body, status FROM sections WHERE plan_id=? "
                    "AND key='p2'", (self.pid,))
        self.assertIn("Second version", row["body"])

    def test_a_human_edited_paragraph_is_never_overwritten(self):
        self.answer(self.pid, "mission_statement", "Generated text.")
        opord.ensure_sections(self.pid)
        db.ex("UPDATE sections SET body=?, status='in_progress' "
              "WHERE plan_id=? AND key='p2'", ("Hand written.", self.pid))
        self.answer(self.pid, "mission_statement", "Regenerated text.")
        opord.ensure_sections(self.pid)
        row = db.q1("SELECT body FROM sections WHERE plan_id=? AND key='p2'",
                    (self.pid,))
        self.assertEqual(row["body"], "Hand written.")

    def test_multi_source_paragraph_labels_each_contribution(self):
        self.answer(self.pid, "intent_purpose", "The purpose is to open a door.")
        self.answer(self.pid, "intent_key_tasks", ["Maintain tempo."])
        self.answer(self.pid, "intent_end_state", "FRIENDLY: consolidated.")
        opord.ensure_sections(self.pid)
        body = db.q1("SELECT body FROM sections WHERE plan_id=? AND key='p3a'",
                     (self.pid,))["body"]
        self.assertIn("PURPOSE", body.upper())
        self.assertIn("KEY TASKS", body.upper())
        self.assertIn("END STATE", body.upper())

    def test_list_values_are_numbered(self):
        self.answer(self.pid, "assumptions", ["First one.", "Second one."])
        opord.ensure_sections(self.pid)
        body = db.q1("SELECT body FROM sections WHERE plan_id=? AND key='p1h'",
                     (self.pid,))["body"]
        self.assertIn("(1) First one.", body)
        self.assertIn("(2) Second one.", body)

    def test_table_values_render_as_pipe_separated_rows(self):
        self.answer(self.pid, "pace_plan",
                    [["Command net", "FM", "TACSAT", "Chat", "Runner"]])
        opord.ensure_sections(self.pid)
        body = db.q1("SELECT body FROM sections WHERE plan_id=? AND key='p5c'",
                     (self.pid,))["body"]
        self.assertIn("Command net | FM | TACSAT", body)

    def test_sections_come_back_in_document_order(self):
        opord.ensure_sections(self.pid)
        rows = opord.sections(self.pid)
        paras = [r["key"] for r in rows if r["kind"] == "paragraph"]
        self.assertEqual(paras[:4], ["references", "time_zone", "task_org", "p1"])
        self.assertTrue(all(r["kind"] == "annex" for r in rows[len(paras):]))

    def test_container_paragraphs_are_marked(self):
        opord.ensure_sections(self.pid)
        doc, _annexes = opord.build_document(self.pid)
        containers = [n["key"] for n in doc if n["container"]]
        self.assertEqual(sorted(containers), ["p1", "p3", "p5"])

    def test_completeness_ignores_container_headings(self):
        opord.ensure_sections(self.pid)
        c = opord.completeness(self.pid)
        self.assertEqual(c["paragraphs"], len(D.OPORD_SKELETON) - 3)
        self.assertEqual(c["annexes"], len(D.ANNEXES))


class TestRenderers(DbCase):
    def setUp(self):
        super().setUp()
        self.pid = self.make_plan("OPERATION RENDER")
        self.answer(self.pid, "unit_designation", "2d Brigade Combat Team")
        self.answer(self.pid, "mission_statement",
                    "2d BCT attacks at 010500Z to seize OBJECTIVE FALCON in "
                    "order to enable the exploitation east.")
        self.answer(self.pid, "assumptions", ["The bridge survives."])
        self.answer(self.pid, "pace_plan",
                    [["Command net", "FM", "TACSAT", "Chat", "Runner"]])
        opord.ensure_sections(self.pid)

    def test_text_render(self):
        out = opord.render_text(self.pid)
        for marker in ["OPERATION ORDER", "1. SITUATION", "2. MISSION",
                       "3. EXECUTION", "4. SUSTAINMENT", "5. COMMAND AND SIGNAL",
                       "ANNEXES", "ACKNOWLEDGE."]:
            self.assertIn(marker, out, marker)
        self.assertIn("OBJECTIVE FALCON", out)

    def test_container_headings_are_not_marked_to_be_completed(self):
        out = opord.render_text(self.pid)
        situation = out.split("1. SITUATION")[1].split("a. Area of Interest")[0]
        self.assertNotIn("to be completed", situation)

    def test_unfilled_paragraph_is_marked(self):
        self.assertIn("(to be completed)", opord.render_text(self.pid))

    def test_markdown_render(self):
        out = opord.render_markdown(self.pid)
        self.assertTrue(out.startswith("# Operation Order"))
        self.assertIn("## 2. Mission", out)
        self.assertIn("### a. Area of Interest", out)
        self.assertIn("OBJECTIVE FALCON", out)

    def test_html_render_is_escaped_and_self_contained(self):
        self.answer(self.pid, "mission_statement",
                    'Sneaky <script>alert("x")</script> & more')
        opord.ensure_sections(self.pid)
        db.ex("UPDATE sections SET body=? WHERE plan_id=? AND key='p2'",
              ('Sneaky <script>alert("x")</script> & more', self.pid))
        out = opord.render_html(self.pid)
        self.assertIn("&lt;script&gt;", out)
        self.assertNotIn("<script>alert", out)
        self.assertIn("<style>", out)          # styles are inline
        self.assertNotIn("http://", out)       # no external references

    def test_docx_is_a_valid_openxml_package(self):
        blob = opord.render_docx(self.pid)
        self.assertEqual(blob[:2], b"PK")
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            self.assertIsNone(z.testzip())
            names = z.namelist()
            for required in ("[Content_Types].xml", "_rels/.rels",
                             "word/document.xml"):
                self.assertIn(required, names)
            body = z.read("word/document.xml").decode()
            self.assertTrue(body.startswith("<?xml"))
            self.assertIn("OBJECTIVE FALCON", body)
            self.assertIn("Heading1", body)

    def test_docx_escapes_xml_metacharacters(self):
        db.ex("UPDATE sections SET body=? WHERE plan_id=? AND key='p2'",
              ("Fires & effects <danger> \"quoted\"", self.pid))
        blob = opord.render_docx(self.pid)
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            body = z.read("word/document.xml").decode()
        self.assertIn("&amp;", body)
        self.assertIn("&lt;danger&gt;", body)

    def test_docx_preserves_line_breaks(self):
        db.ex("UPDATE sections SET body=? WHERE plan_id=? AND key='p2'",
              ("line one\nline two", self.pid))
        with zipfile.ZipFile(io.BytesIO(opord.render_docx(self.pid))) as z:
            body = z.read("word/document.xml").decode()
        self.assertIn("<w:br/>", body)

    def test_every_renderer_survives_a_completely_empty_plan(self):
        empty = self.make_plan("EMPTY")
        opord.ensure_sections(empty)
        self.assertIn("OPERATION ORDER", opord.render_text(empty))
        self.assertIn("# Operation Order", opord.render_markdown(empty))
        self.assertIn("<html>", opord.render_html(empty))
        self.assertEqual(opord.render_docx(empty)[:2], b"PK")

    def test_every_renderer_survives_unicode(self):
        db.ex("UPDATE sections SET body=? WHERE plan_id=? AND key='p2'",
              ("Attaque — 5 km, «objectif», 目標, ​zero-width", self.pid))
        self.assertIn("目標", opord.render_text(self.pid))
        self.assertIn("目標", opord.render_markdown(self.pid))
        self.assertIn("目標", opord.render_html(self.pid))
        with zipfile.ZipFile(io.BytesIO(opord.render_docx(self.pid))) as z:
            self.assertIn("目標", z.read("word/document.xml").decode())


if __name__ == "__main__":
    unittest.main()
