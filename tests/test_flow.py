"""The flow engine: dependencies, staleness, and step status."""

import unittest

from tests.base import DbCase

from harness.flow import (Field, Flow, Step, context_for, dep_hash,
                          field_status, flow_state, is_empty, step_status)
from harness.mdmp.flow_def import FLOW


class TestFieldSpec(unittest.TestCase):
    def test_rejects_unknown_kind(self):
        with self.assertRaises(ValueError):
            Field("x", "X", kind="wombat")

    def test_gen_defaults_to_key(self):
        self.assertEqual(Field("mission", "Mission").gen, "mission")
        self.assertEqual(Field("mission", "Mission", gen="other").gen, "other")

    def test_duplicate_field_keys_are_rejected(self):
        s1 = Step("a", 1, "A", fields=[Field("dup", "One")])
        s2 = Step("b", 2, "B", fields=[Field("dup", "Two")])
        with self.assertRaises(ValueError):
            Flow("f", "F", "", [s1, s2])


class TestDependencies(unittest.TestCase):
    def test_hash_ignores_unrelated_fields(self):
        f = Field("c", "C", depends=["a"])
        h1 = dep_hash(f, {"a": 1, "b": 2})
        h2 = dep_hash(f, {"a": 1, "b": 999})
        self.assertEqual(h1, h2)

    def test_hash_changes_with_a_dependency(self):
        f = Field("c", "C", depends=["a"])
        self.assertNotEqual(dep_hash(f, {"a": 1}), dep_hash(f, {"a": 2}))

    def test_hash_is_order_independent(self):
        f = Field("c", "C", depends=["a", "b"])
        self.assertEqual(dep_hash(f, {"a": 1, "b": 2}),
                         dep_hash(f, {"b": 2, "a": 1}))

    def test_hash_handles_lists_and_tables(self):
        f = Field("c", "C", depends=["a"])
        self.assertNotEqual(dep_hash(f, {"a": ["x"]}), dep_hash(f, {"a": ["y"]}))
        self.assertNotEqual(dep_hash(f, {"a": [["x", "y"]]}),
                            dep_hash(f, {"a": [["x", "z"]]}))

    def test_transitive_dependents(self):
        # mission_statement feeds intent, which feeds key tasks, and so on.
        deps = FLOW.dependents_of("mission_statement")
        self.assertIn("intent_purpose", deps)
        self.assertIn("intent_key_tasks", deps)   # via intent_purpose
        self.assertIn("coa_1", deps)
        self.assertIn("concept_of_operations", deps)  # several hops downstream

    def test_no_field_depends_on_itself(self):
        for f in FLOW.all_fields():
            self.assertNotIn(f.key, f.depends, f.key)

    def test_no_dependency_cycles(self):
        for f in FLOW.all_fields():
            self.assertNotIn(f.key, FLOW.dependents_of(f.key),
                             "%s is in its own dependent set" % f.key)

    def test_dependencies_point_backwards_in_the_flow(self):
        """A field may only depend on something at or before its own step."""
        order = {s.key: i for i, s in enumerate(FLOW.steps)}
        for f in FLOW.all_fields():
            mine = order[FLOW.step_of(f.key).key]
            for d in f.depends:
                theirs = order[FLOW.step_of(d).key]
                self.assertLessEqual(
                    theirs, mine,
                    "%s (step %d) depends on %s from later step %d"
                    % (f.key, mine + 1, d, theirs + 1))


class TestStatus(unittest.TestCase):
    def test_is_empty(self):
        for v in (None, "", "   ", [], {}):
            self.assertTrue(is_empty(v), repr(v))
        for v in ("x", [1], {"a": 1}, 0, False):
            self.assertFalse(is_empty(v), repr(v))

    def test_field_status_transitions(self):
        f = Field("c", "C", depends=["a"])
        answers = {"a": 1}
        self.assertEqual(field_status(f, answers, {}), "empty")
        answers["c"] = "done"
        h = {"c": dep_hash(f, answers)}
        self.assertEqual(field_status(f, answers, h), "answered")
        answers["a"] = 2                      # upstream changed
        self.assertEqual(field_status(f, answers, h), "stale")

    def test_field_without_dependencies_never_goes_stale(self):
        f = Field("a", "A")
        self.assertEqual(field_status(f, {"a": "x"}, {}), "answered")

    def test_step_rollup(self):
        step = Step("s", 1, "S", fields=[
            Field("req1", "R1"), Field("req2", "R2"),
            Field("opt1", "O1", required=False)])
        self.assertEqual(step_status(step, {}, {}), "empty")
        self.assertEqual(step_status(step, {"req1": "x"}, {}), "partial")
        self.assertEqual(step_status(step, {"req1": "x", "req2": "y"}, {}),
                         "complete")

    def test_optional_field_does_not_block_completion(self):
        step = Step("s", 1, "S", fields=[
            Field("req", "R"), Field("opt", "O", required=False)])
        self.assertEqual(step_status(step, {"req": "x"}, {}), "complete")

    def test_stale_beats_complete(self):
        f = Field("c", "C", depends=["a"])
        step = Step("s", 1, "S", fields=[f])
        answers = {"a": 1, "c": "done"}
        h = {"c": dep_hash(f, answers)}
        answers["a"] = 2
        self.assertEqual(step_status(step, answers, h), "stale")


class TestFlowState(DbCase):
    def test_current_step_is_the_first_incomplete_one(self):
        state = flow_state(FLOW, {}, {})
        self.assertEqual(state["current"], "receipt")
        self.assertFalse(state["complete"])
        self.assertEqual(len(state["steps"]), 7)

    def test_completing_step_one_advances_the_cursor(self):
        pid = self.make_plan()
        for f in FLOW.step("receipt").fields:
            if f.required:
                self.answer(pid, f.key, "x" if f.kind in ("text", "choice")
                            else ([["a"]] if f.kind == "table" else ["x"]))
        state = flow_state(FLOW, self.answers(pid), self.hashes(pid))
        self.assertEqual(state["steps"][0]["status"], "complete")
        self.assertEqual(state["current"], "mission_analysis")

    def test_changing_an_early_answer_makes_later_steps_stale(self):
        pid = self.make_plan()
        self.answer(pid, "operation_type", "Offensive Operation: Attack")
        self.answer(pid, "specified_tasks", ["Attack along AXIS EAGLE."])
        before = flow_state(FLOW, self.answers(pid), self.hashes(pid))
        self.assertNotEqual(before["steps"][1]["status"], "stale")

        self.answer(pid, "operation_type", "Defensive Operation: Area Defense")
        after = flow_state(FLOW, self.answers(pid), self.hashes(pid))
        self.assertEqual(after["steps"][1]["status"], "stale")
        self.assertEqual(after["steps"][1]["fields"]["specified_tasks"], "stale")


class TestContext(unittest.TestCase):
    def test_context_includes_dependencies_and_ambient_facts(self):
        f = FLOW.field("mission_statement")
        answers = {"essential_tasks": ["Seize OBJECTIVE FALCON."],
                   "unit_designation": "2d BCT",
                   "civil_considerations": ["irrelevant to this field"]}
        ctx = context_for(FLOW, f, answers)
        self.assertIn("essential_tasks", ctx)
        self.assertIn("unit_designation", ctx)      # ambient
        self.assertNotIn("civil_considerations", ctx)

    def test_context_skips_empty_values(self):
        f = FLOW.field("mission_statement")
        ctx = context_for(FLOW, f, {"essential_tasks": [], "higher_one_up": ""})
        self.assertEqual(ctx, {})


class TestFlowIntegrity(unittest.TestCase):
    """Guards that the shipped MDMP flow stays coherent as it is edited."""

    def test_every_field_has_a_registered_generator(self):
        from harness.mdmp import generators
        missing = [f.gen for f in FLOW.all_fields()
                   if f.gen not in generators.REGISTRY]
        self.assertEqual(missing, [])

    def test_every_field_has_a_plain_english_explanation(self):
        for f in FLOW.all_fields():
            self.assertTrue(f.plain.strip(), "%s has no plain text" % f.key)
            self.assertGreater(len(f.plain), 30, f.key)

    def test_every_opord_reference_resolves(self):
        from harness.mdmp import doctrine as D
        keys = {n["key"] for n in D.OPORD_SKELETON}
        for f in FLOW.all_fields():
            for k in f.opord:
                self.assertIn(k, keys, "%s -> %s" % (f.key, k))

    def test_table_fields_declare_columns(self):
        for f in FLOW.all_fields():
            if f.kind == "table":
                self.assertTrue(f.columns, "%s is a table with no columns" % f.key)

    def test_steps_are_numbered_in_order(self):
        self.assertEqual([s.num for s in FLOW.steps], [1, 2, 3, 4, 5, 6, 7])

    def test_flow_serialises_for_the_api(self):
        d = FLOW.to_dict()
        self.assertEqual(len(d["steps"]), 7)
        self.assertTrue(all("fields" in s for s in d["steps"]))


if __name__ == "__main__":
    unittest.main()
