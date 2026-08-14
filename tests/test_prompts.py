"""Prompt overrides: the resolution chain, rendering, and failure modes."""

import unittest

from tests.base import DbCase

from harness.agent import prompts as P
from harness.mdmp.flow_def import FLOW


class TestResolution(DbCase):
    def setUp(self):
        super().setUp()
        self.pid = self.make_plan()
        self.other = self.make_plan("OTHER PLAN")
        self.field = FLOW.field("mission_statement")
        self.step_key = FLOW.step_of("mission_statement").key

    def resolve(self, plan_id=None):
        return P.resolve(plan_id if plan_id is not None else self.pid,
                         self.step_key, self.field.key)

    def test_builtin_default_when_nothing_is_set(self):
        r = self.resolve()
        self.assertEqual(r["system"], P.DEFAULT_SYSTEM)
        self.assertEqual(r["template"], P.DEFAULT_TEMPLATE)
        self.assertEqual(r["system_source"], "built-in default")

    def test_global_server_default_applies_everywhere(self):
        P.save("global", "", None, "GLOBAL SYS", "GLOBAL TPL", self.uid)
        self.assertEqual(self.resolve()["system"], "GLOBAL SYS")
        self.assertEqual(self.resolve(self.other)["system"], "GLOBAL SYS")

    def test_step_override_beats_global(self):
        P.save("global", "", None, "GLOBAL", "GLOBAL", self.uid)
        P.save("step", self.step_key, None, "STEP", "STEP", self.uid)
        self.assertEqual(self.resolve()["system"], "STEP")

    def test_field_override_beats_step(self):
        P.save("global", "", None, "GLOBAL", "GLOBAL", self.uid)
        P.save("step", self.step_key, None, "STEP", "STEP", self.uid)
        P.save("field", self.field.key, None, "FIELD", "FIELD", self.uid)
        self.assertEqual(self.resolve()["system"], "FIELD")

    def test_plan_scope_beats_server_scope_at_the_same_level(self):
        P.save("field", self.field.key, None, "SERVER", "SERVER", self.uid)
        P.save("field", self.field.key, self.pid, "PLAN", "PLAN", self.uid)
        self.assertEqual(self.resolve()["system"], "PLAN")
        # ...and does not leak into another plan
        self.assertEqual(self.resolve(self.other)["system"], "SERVER")

    def test_full_precedence_ladder(self):
        """All six levels set at once: the most specific must win, in order."""
        ladder = [
            ("global", "", None, "L6"),
            ("global", "", self.pid, "L5"),
            ("step", self.step_key, None, "L4"),
            ("step", self.step_key, self.pid, "L3"),
            ("field", self.field.key, None, "L2"),
            ("field", self.field.key, self.pid, "L1"),
        ]
        for level, key, plan, text in ladder:
            P.save(level, key, plan, text, text, self.uid)
        expected = ["L1", "L2", "L3", "L4", "L5", "L6"]
        for want in expected:
            self.assertEqual(self.resolve()["system"], want)
            # peel the winner off and check the next one takes over
            level, key, plan, _t = next(
                x for x in ladder if x[3] == want)
            P.clear(level, key, plan)
        self.assertEqual(self.resolve()["system"], P.DEFAULT_SYSTEM)

    def test_system_and_template_resolve_independently(self):
        """Override only the template at field level; system falls through."""
        P.save("step", self.step_key, None, "STEP SYS", "", self.uid)
        P.save("field", self.field.key, None, "", "FIELD TPL", self.uid)
        r = self.resolve()
        self.assertEqual(r["system"], "STEP SYS")
        self.assertEqual(r["template"], "FIELD TPL")

    def test_source_labels_explain_where_it_came_from(self):
        P.save("step", self.step_key, self.pid, "S", "S", self.uid)
        r = self.resolve()
        self.assertIn("step", r["system_source"])
        self.assertIn("this plan", r["system_source"])

    def test_clear_removes_only_the_named_scope(self):
        P.save("field", self.field.key, None, "SERVER", "SERVER", self.uid)
        P.save("field", self.field.key, self.pid, "PLAN", "PLAN", self.uid)
        P.clear("field", self.field.key, self.pid)
        self.assertEqual(self.resolve()["system"], "SERVER")

    def test_saving_twice_updates_rather_than_duplicating(self):
        P.save("field", self.field.key, self.pid, "one", "one", self.uid)
        P.save("field", self.field.key, self.pid, "two", "two", self.uid)
        self.assertEqual(len(P.list_all()), 1)
        self.assertEqual(self.resolve()["system"], "two")

    def test_global_level_ignores_a_stray_key(self):
        P.save("global", "nonsense", None, "G", "G", self.uid)
        self.assertEqual(self.resolve()["system"], "G")

    def test_unknown_level_is_rejected(self):
        with self.assertRaises(ValueError):
            P.save("planet", "x", None, "a", "b", self.uid)

    def test_overrides_for_lists_the_chain(self):
        P.save("step", self.step_key, None, "S", "S", self.uid)
        P.save("field", self.field.key, self.pid, "F", "F", self.uid)
        chain = P.overrides_for(self.pid, self.step_key, self.field.key)
        self.assertEqual(len(chain), 2)
        self.assertTrue(chain[0]["label"].startswith("field"))

    def test_deleting_a_plan_removes_its_prompt_overrides(self):
        from harness import db
        P.save("field", self.field.key, self.pid, "P", "P", self.uid)
        db.ex("DELETE FROM plans WHERE id=?", (self.pid,))
        self.assertEqual(P.list_all(), [])

    def test_saving_two_blank_halves_stores_nothing(self):
        P.save("field", self.field.key, self.pid, "", "   ", self.uid)
        self.assertEqual(P.list_all(), [])

    def test_blanking_an_existing_override_removes_it(self):
        P.save("field", self.field.key, self.pid, "F", "F", self.uid)
        P.save("field", self.field.key, self.pid, "", "", self.uid)
        self.assertEqual(P.list_all(), [])
        self.assertEqual(self.resolve()["system"], P.DEFAULT_SYSTEM)

    def test_hollow_row_is_not_reported_as_an_override(self):
        from harness import db
        db.ex("INSERT INTO prompts(level,scope_key,plan_id,system,template,"
              "updated_by,updated_at) VALUES(?,?,?,?,?,?,?)",
              ("field", self.field.key, self.pid, "", "", self.uid, db.now()))
        self.assertEqual(P.overrides_for(self.pid, self.step_key,
                                         self.field.key), [])


class TestOnlyChanges(DbCase):
    """A half the planner never touched must not be pinned at this level."""

    def setUp(self):
        super().setUp()
        self.pid = self.make_plan()
        self.field = FLOW.field("mission_statement")
        self.step_key = FLOW.step_of("mission_statement").key

    def only(self, level, key, system, template, plan_id=-1):
        return P.only_changes(
            level, key, self.pid if plan_id == -1 else plan_id,
            self.step_key, key if level == "field" else None, system, template)

    def test_echoing_the_builtin_back_stores_nothing(self):
        s, t = self.only("field", self.field.key,
                         P.DEFAULT_SYSTEM, P.DEFAULT_TEMPLATE)
        self.assertEqual((s, t), ("", ""))

    def test_only_the_edited_half_survives(self):
        s, t = self.only("field", self.field.key, P.DEFAULT_SYSTEM, "MY TEMPLATE")
        self.assertEqual(s, "")
        self.assertEqual(t, "MY TEMPLATE")

    def test_inherited_text_from_a_lower_rung_is_not_pinned(self):
        """The editor shows the global override; saving must not copy it down."""
        P.save("global", "", None, "GLOBAL SYS", "GLOBAL TPL", self.uid)
        s, t = self.only("field", self.field.key, "GLOBAL SYS", "EDITED TPL")
        self.assertEqual(s, "")
        self.assertEqual(t, "EDITED TPL")
        P.save("field", self.field.key, self.pid, s, t, self.uid)
        r = P.resolve(self.pid, self.step_key, self.field.key)
        self.assertEqual(r["template"], "EDITED TPL")
        self.assertEqual(r["system"], "GLOBAL SYS")
        # ...and a later change to the global system prompt still reaches it
        P.save("global", "", None, "GLOBAL SYS v2", "GLOBAL TPL", self.uid)
        r = P.resolve(self.pid, self.step_key, self.field.key)
        self.assertEqual(r["system"], "GLOBAL SYS v2")

    def test_rewriting_this_scopes_own_override_keeps_it(self):
        P.save("field", self.field.key, self.pid, "MINE", "MINE", self.uid)
        s, t = self.only("field", self.field.key, "MINE", "MINE")
        self.assertEqual((s, t), ("MINE", "MINE"))

    def test_trailing_whitespace_does_not_count_as_an_edit(self):
        s, t = self.only("field", self.field.key,
                         P.DEFAULT_SYSTEM + "\n\n", P.DEFAULT_TEMPLATE + " ")
        self.assertEqual((s, t), ("", ""))

    def test_server_scope_diffs_against_the_server_chain(self):
        P.save("global", "", None, "GLOBAL SYS", "GLOBAL TPL", self.uid)
        s, t = self.only("field", self.field.key, "GLOBAL SYS", "NEW",
                         plan_id=None)
        self.assertEqual(s, "")
        self.assertEqual(t, "NEW")


class TestRendering(unittest.TestCase):
    def test_placeholders_are_filled(self):
        out = P.render("Step {step_num}: {step_title} / {field_label}",
                       {"step_num": 2, "step_title": "Mission Analysis",
                        "field_label": "Mission statement"})
        self.assertEqual(out, "Step 2: Mission Analysis / Mission statement")

    def test_unknown_placeholder_is_left_alone(self):
        out = P.render("keep {wombat} intact", {"field_label": "x"})
        self.assertIn("{wombat}", out)

    def test_unbalanced_brace_degrades_to_the_default(self):
        out = P.render("broken {", {"field_label": "x", "step_num": 1,
                                    "step_title": "s", "field_plain": "p",
                                    "field_doctrine": "d", "context": "c",
                                    "passages": "", "n": 5,
                                    "kind_instruction": "k", "columns": ""})
        self.assertIn("could not be rendered", out)
        self.assertIn("PLANNING STEP", out)   # fell back to the default

    def test_empty_template_renders_empty(self):
        self.assertEqual(P.render("", {}), "")

    def test_used_and_unknown_placeholders(self):
        tpl = "{field_label} {wombat} {n}"
        self.assertEqual(P.used_placeholders(tpl), ["field_label", "n", "wombat"])
        self.assertEqual(P.unknown_placeholders(tpl), ["wombat"])

    def test_every_documented_placeholder_is_actually_provided(self):
        field = FLOW.field("mission_statement")
        step = FLOW.step_of("mission_statement")
        values = P.values_for(field, step, {"unit_designation": "2d BCT"}, [], 5)
        for name, _desc in P.PLACEHOLDERS:
            self.assertIn(name, values, "%s is documented but never supplied" % name)

    def test_default_template_uses_only_documented_placeholders(self):
        self.assertEqual(P.unknown_placeholders(P.DEFAULT_TEMPLATE), [])

    def test_context_block_formats_lists_and_tables(self):
        block = P.context_block({"tasks": ["a", "b"],
                                 "matrix": [["r1c1", "r1c2"], ["r2c1", "r2c2"]]})
        self.assertIn("a; b", block)
        self.assertIn("r1c1 | r1c2", block)

    def test_context_block_truncates_very_long_values(self):
        block = P.context_block({"x": "y" * 5000})
        self.assertLess(len(block), 800)
        self.assertIn("…", block)

    def test_empty_context_says_so(self):
        self.assertIn("no prior decisions", P.context_block({}))

    def test_kind_instruction_covers_every_kind(self):
        from harness.flow import KINDS, Field
        for kind in KINDS:
            f = Field("k", "K", kind=kind, columns=["A", "B"])
            self.assertTrue(P.kind_instruction(f).strip(), kind)


class TestBuild(DbCase):
    def test_build_returns_system_and_rendered_user_prompt(self):
        pid = self.make_plan()
        field = FLOW.field("mission_statement")
        step = FLOW.step_of(field.key)
        system, user, res = P.build(pid, field, step,
                                    {"unit_designation": "2d BCT"}, [], 4)
        self.assertEqual(system, P.DEFAULT_SYSTEM)
        self.assertIn("Mission Analysis", user)
        self.assertIn("2d BCT", user)
        self.assertIn("Produce 4 distinct", user)
        self.assertEqual(res["template_source"], "built-in default")

    def test_an_override_reaches_the_built_prompt(self):
        pid = self.make_plan()
        field = FLOW.field("mission_statement")
        step = FLOW.step_of(field.key)
        P.save("field", field.key, pid,
               "CUSTOM SYSTEM", "Write {n} options for {field_label}.", self.uid)
        system, user, _res = P.build(pid, field, step, {}, [], 3)
        self.assertEqual(system, "CUSTOM SYSTEM")
        self.assertEqual(user, "Write 3 options for Restated mission statement.")

    def test_passages_are_included_when_present(self):
        pid = self.make_plan()
        field = FLOW.field("mission_statement")
        step = FLOW.step_of(field.key)
        _s, user, _r = P.build(
            pid, field, step, {}, [{"title": "FM 5-0", "snippet": "the task"}], 3)
        self.assertIn("FM 5-0", user)
        self.assertIn("the task", user)


if __name__ == "__main__":
    unittest.main()
