"""Providers, response parsing, the critique rules, and the fallback chain."""

import itertools
import json
import unittest

from tests.base import DbCase

from harness.agent import engine as E
from harness.agent import providers
from harness.flow import Field
from harness.mdmp import generators as G
from harness.mdmp.flow_def import FLOW


# ------------------------------------------------------------- providers --

class TestResponseParsing(unittest.TestCase):
    """A local 7B model returns messy JSON. None of it may crash the tool."""

    def parse(self, text):
        return providers._parse_options(text)

    def test_clean_json(self):
        out = self.parse(json.dumps({"options": [
            {"label": "A", "value": "a", "rationale": "r", "flags": []}]}))
        self.assertEqual(out[0]["label"], "A")

    def test_fenced_json(self):
        out = self.parse('```json\n{"options":[{"label":"A","value":"a"}]}\n```')
        self.assertEqual(out[0]["value"], "a")

    def test_bare_fence(self):
        out = self.parse('```\n{"options":[{"label":"A","value":"a"}]}\n```')
        self.assertEqual(len(out), 1)

    def test_prose_wrapped_json(self):
        out = self.parse('Sure! Here you go:\n{"options":[{"label":"A",'
                         '"value":"a"}]}\nHope that helps.')
        self.assertEqual(out[0]["label"], "A")

    def test_bare_array_without_the_wrapper(self):
        out = self.parse('{"options": [{"label":"A","value":"a"}]}')
        self.assertEqual(len(out), 1)

    def test_missing_fields_are_defaulted(self):
        out = self.parse('{"options":[{"value":"just a value"}]}')
        self.assertEqual(out[0]["label"], "Option")
        self.assertEqual(out[0]["rationale"], "")
        self.assertEqual(out[0]["flags"], [])

    def test_non_dict_entries_are_skipped(self):
        out = self.parse('{"options":["a string", {"label":"A","value":"a"}]}')
        self.assertEqual(len(out), 1)

    def test_flags_are_capped_and_stringified(self):
        out = self.parse('{"options":[{"label":"A","value":"a",'
                         '"flags":[1,2,3,4,5,6,7]}]}')
        self.assertEqual(len(out[0]["flags"]), 5)
        self.assertEqual(out[0]["flags"][0], "1")

    def test_overlong_label_is_truncated(self):
        out = self.parse(json.dumps({"options": [
            {"label": "x" * 500, "value": "a"}]}))
        self.assertEqual(len(out[0]["label"]), 120)

    def test_empty_response_raises(self):
        for bad in ("", "   ", "not json at all", "{}",
                    '{"options": []}', '{"options": "nope"}'):
            with self.assertRaises(providers.ProviderError, msg=repr(bad)):
                self.parse(bad)

    def test_truncated_json_raises_rather_than_corrupting(self):
        with self.assertRaises(providers.ProviderError):
            self.parse('{"options":[{"label":"A","value":')


class TestProviderConstruction(unittest.TestCase):
    def test_build_defaults_to_offline(self):
        self.assertEqual(providers.build().name, "offline")

    def test_build_by_name(self):
        self.assertEqual(providers.build("ollama").name, "ollama")
        self.assertEqual(providers.build("openai").name, "openai")
        self.assertEqual(providers.build("anthropic").name, "anthropic")
        self.assertEqual(providers.build("nonsense").name, "offline")

    def test_offline_is_always_available(self):
        self.assertTrue(providers.OfflineProvider().available())

    def test_unreachable_local_servers_report_unavailable(self):
        p = providers.OllamaProvider("http://127.0.0.1:1")
        self.assertFalse(p.available())
        p2 = providers.OpenAICompatProvider("http://127.0.0.1:1/v1")
        self.assertFalse(p2.available())

    def test_unreachable_provider_raises_a_provider_error(self):
        p = providers.OllamaProvider("http://127.0.0.1:1")
        with self.assertRaises(providers.ProviderError):
            p.options("sys", "user", 3)

    def test_detect_lists_every_provider(self):
        names = [d["name"] for d in providers.detect()]
        self.assertEqual(set(names),
                         {"offline", "ollama", "openai", "anthropic"})

    def test_anthropic_reports_missing_sdk_clearly(self):
        p = providers.AnthropicProvider(api_key="x")
        try:
            import anthropic  # noqa: F401
        except ImportError:
            self.assertFalse(p.available())
            with self.assertRaises(providers.ProviderError) as cm:
                p.options("s", "u", 3)
            self.assertIn("pip install anthropic", str(cm.exception))


# --------------------------------------------------------------- critique --

class TestCritique(unittest.TestCase):
    def problems(self, field_key, text, prior=()):
        field = FLOW.field(field_key)
        return E._critique(field, {"value": text}, prior)

    def test_good_mission_statement_passes(self):
        good = ("2d Brigade Combat Team attacks along AXIS EAGLE at 010500Z to "
                "seize OBJECTIVE FALCON in order to enable the division's "
                "exploitation east.")
        self.assertEqual(self.problems("mission_statement", good), [])

    def test_mission_statement_without_a_time(self):
        bad = ("2d Brigade Combat Team attacks to seize OBJECTIVE FALCON in "
               "order to enable the division's exploitation.")
        self.assertTrue(any("WHEN" in p for p in
                            self.problems("mission_statement", bad)))

    def test_mission_statement_without_a_purpose(self):
        bad = "2d BCT attacks at 010500Z to seize OBJECTIVE FALCON."
        self.assertTrue(any("WHY" in p for p in
                            self.problems("mission_statement", bad)))

    def test_mission_statement_without_a_doctrinal_verb(self):
        bad = ("2d BCT goes to the hill at 010500Z in order to make things "
               "better for everyone involved in the operation.")
        self.assertTrue(any("task verb" in p for p in
                            self.problems("mission_statement", bad)))

    def test_indistinguishable_coa_is_caught(self):
        coa = ("The brigade attacks along the northern axis with two "
               "battalions forward, breaches the obstacle belt at two lanes, "
               "and seizes the objective while the reserve follows.")
        near = ("The brigade attacks along the northern axis with two "
                "battalions forward, breaches the obstacle belt at two lanes, "
                "and seizes the objective while the reserve trails.")
        self.assertTrue(any("distinguishable" in p
                            for p in self.problems("coa_2", near, [coa])))

    def test_genuinely_different_coa_passes_the_similarity_check(self):
        coa1 = ("DECISIVE OPERATION: penetration in the north with two "
                "battalions forward breaching the obstacle belt.")
        coa2 = ("DECISIVE OPERATION: infiltration by dismounted companies "
                "through the southern canals at night, bypassing all "
                "prepared defences entirely.")
        self.assertFalse(any("distinguishable" in p
                             for p in self.problems("coa_2", coa2, [coa1])))

    def test_coa_must_name_the_decisive_operation(self):
        vague = ("The brigade will move forward and fight the enemy until the "
                 "objective is taken by whichever unit gets there first.")
        self.assertTrue(any("decisive operation" in p
                            for p in self.problems("coa_1", vague)))

    def test_pir_must_link_to_a_decision(self):
        bad = "What colour are the enemy vehicles?"
        self.assertTrue(any("linked decision" in p
                            for p in self.problems("ccir_pir", bad)))

    def test_good_pir_passes(self):
        good = ("PIR 1: Will the threat commit its reserve east of PHASE LINE "
                "BLUE? (Decision: commit our own reserve.)")
        self.assertEqual(self.problems("ccir_pir", good), [])

    def test_assumption_must_be_confirmable(self):
        bad = "ASSUMPTION: The weather will be fine."
        self.assertTrue(any("confirmed" in p
                            for p in self.problems("assumptions", bad)))

    def test_end_state_must_describe_conditions(self):
        bad = "We will win the battle decisively and go home."
        self.assertTrue(self.problems("intent_end_state", bad))

    def test_key_task_naming_a_unit_is_flagged(self):
        bad = "1st Battalion seizes the bridge."
        self.assertTrue(any("named unit" in p
                            for p in self.problems("intent_key_tasks", bad)))

    def test_blank_value_is_never_criticised(self):
        self.assertEqual(self.problems("mission_statement", ""), [])

    def test_short_text_is_rejected(self):
        self.assertTrue(any("too short" in p
                            for p in self.problems("problem_statement", "hmm")))

    def test_similarity_is_symmetric_and_bounded(self):
        a, b = "alpha bravo charlie delta", "alpha bravo charlie echo"
        self.assertAlmostEqual(E._similarity(a, b), E._similarity(b, a))
        self.assertEqual(E._similarity("", "anything"), 0.0)
        self.assertEqual(E._similarity(a, a), 1.0)


# ----------------------------------------------------------------- engine --

class _FakeProvider(providers.Provider):
    """Stands in for a model so the engine can be tested deterministically."""

    def __init__(self, payload=None, raise_with=None):
        self.name = "fake"
        self.payload = payload or []
        self.raise_with = raise_with
        self.calls = []

    def available(self):
        return True

    def describe(self):
        return "fake provider"

    def options(self, system, user, n):
        self.calls.append({"system": system, "user": user, "n": n})
        if self.raise_with:
            raise self.raise_with
        return self.payload


class TestEngine(DbCase):
    def setUp(self):
        super().setUp()
        self.pid = self.make_plan()

    def gen(self, provider, field_key="mission_statement", ctx=None, n=5,
            prior=()):
        field = FLOW.field(field_key)
        return E.Engine(provider).generate(FLOW, field, ctx or {}, n, prior,
                                           plan_id=self.pid)

    def test_offline_provider_always_returns_options(self):
        opts, meta = self.gen(providers.OfflineProvider())
        self.assertTrue(opts)
        self.assertEqual(meta["provider"], "offline")

    def test_provider_failure_falls_back_to_templates(self):
        p = _FakeProvider(raise_with=providers.ProviderError("connection refused"))
        opts, meta = self.gen(p)
        self.assertTrue(opts, "fallback produced nothing")
        self.assertEqual(meta["provider"], "offline")
        self.assertTrue(any("connection refused" in n for n in meta["notes"]))

    def test_unexpected_provider_exception_also_falls_back(self):
        p = _FakeProvider(raise_with=RuntimeError("kaboom"))
        opts, meta = self.gen(p)
        self.assertTrue(opts)
        self.assertEqual(meta["provider"], "offline")

    def test_model_options_survive_when_they_are_good(self):
        p = _FakeProvider([
            {"label": "Model option %d" % i,
             "value": ("2d BCT attacks along AXIS EAGLE at 010500Z to seize "
                       "OBJECTIVE %d in order to enable the exploitation." % i),
             "rationale": "because", "flags": []}
            for i in range(5)])
        opts, meta = self.gen(p)
        self.assertEqual(meta["provider"], "fake")
        self.assertGreaterEqual(
            len([o for o in opts if o["label"].startswith("Model option")]), 5)

    def test_weak_options_are_flagged_not_hidden(self):
        p = _FakeProvider([
            {"label": "No purpose", "value":
             "2d BCT attacks at 010500Z and seizes the objective quickly.",
             "rationale": "", "flags": []}] * 1)
        opts, _meta = self.gen(p)
        flagged = [o for o in opts if any(f.startswith("check:")
                                          for f in o["flags"])]
        self.assertTrue(flagged, "a weak option should be flagged for review")

    def test_backfill_tops_up_a_thin_response(self):
        p = _FakeProvider([
            {"label": "Only one",
             "value": ("2d BCT attacks along AXIS EAGLE at 010500Z to seize "
                       "OBJECTIVE FALCON in order to enable exploitation."),
             "rationale": "", "flags": []}])
        opts, meta = self.gen(p, n=5)
        self.assertGreater(len(opts), 1)
        self.assertTrue(any("topped up" in n for n in meta["notes"]))

    def test_every_option_carries_an_id_and_provider(self):
        opts, _m = self.gen(providers.OfflineProvider())
        for o in opts:
            self.assertIn("id", o)
            self.assertIn("provider", o)
            self.assertIsInstance(o["flags"], list)

    def test_prompt_override_reaches_the_provider(self):
        from harness.agent import prompts as P
        P.save("field", "mission_statement", self.pid, "SYS OVERRIDE",
               "TPL for {field_label}", self.uid)
        p = _FakeProvider(raise_with=providers.ProviderError("stop here"))
        self.gen(p)
        self.assertEqual(p.calls[0]["system"], "SYS OVERRIDE")
        self.assertEqual(p.calls[0]["user"],
                         "TPL for Restated mission statement")

    def test_meta_reports_which_prompt_was_used(self):
        from harness.agent import prompts as P
        P.save("step", "mission_analysis", self.pid, "", "T", self.uid)
        _opts, meta = self.gen(providers.OfflineProvider())
        self.assertIn("step", meta["prompt"]["template_source"])

    def test_table_rows_from_a_model_are_coerced_to_cells(self):
        field = FLOW.field("pace_plan")
        p = _FakeProvider([{"label": "Net", "flags": [], "rationale": "",
                            "value": "Command net | FM | TACSAT | Chat | Runner"}])
        opts, _m = E.Engine(p).generate(FLOW, field, {}, 3, plan_id=self.pid)
        row = opts[0]["value"]
        self.assertIsInstance(row, list)
        self.assertEqual(len(row), len(field.columns))
        self.assertEqual(row[0], "Command net")

    def test_short_model_table_rows_are_padded(self):
        field = FLOW.field("pace_plan")
        p = _FakeProvider([{"label": "Net", "flags": [], "rationale": "",
                            "value": "Command net | FM"}])
        opts, _m = E.Engine(p).generate(FLOW, field, {}, 3, plan_id=self.pid)
        self.assertEqual(len(opts[0]["value"]), len(field.columns))

    def test_list_value_for_a_text_field_is_joined(self):
        p = _FakeProvider([{"label": "L", "flags": [], "rationale": "",
                            "value": ["line one", "line two"]}])
        opts, _m = self.gen(p, "problem_statement")
        self.assertIsInstance(opts[0]["value"], str)


# ------------------------------------------------------------ generators --

class TestGenerators(unittest.TestCase):
    """Every generator, against every plausible plan shape."""

    @classmethod
    def setUpClass(cls):
        ops = ["Offensive Operation: Attack",
               "Offensive Operation: Movement to Contact",
               "Defensive Operation: Area Defense",
               "Defensive Operation: Mobile Defense",
               "Stability Operation: Establish Civil Security",
               "Defense Support of Civil Authorities: Provide Support for "
               "Domestic Disasters"]
        postures = ["Peer", "Near-Peer", "Hybrid", "Irregular", "Combination"]
        envs = ["DATE Caucasus", "DATE Pacific", "DATE Europe", "DATE Africa",
                "Custom / Home Station"]
        echelons = ["Corps", "Division", "Brigade Combat Team (BCT)",
                    "Battalion / Squadron", "Company / Troop / Battery",
                    "Platoon"]
        cls.contexts = [
            {"operation_type": o, "opfor_posture": p, "oe_framework": e,
             "echelon": ec, "unit_designation": "2d Brigade Combat Team",
             "eval_criteria": ["Mission Accomplishment", "Risk to Force"]}
            for o, p, e, ec in itertools.product(ops, postures, envs, echelons)
        ]
        cls.contexts.append({})            # a brand-new plan
        cls.contexts.append({"operation_type": "", "echelon": None})

    def test_no_generator_raises_and_all_offer_something_usable(self):
        broken = {}
        for key, fn in sorted(G.REGISTRY.items()):
            for ctx in self.contexts:
                try:
                    out = fn(ctx, 6)
                except Exception as exc:
                    broken.setdefault(key, set()).add(
                        "%s: %s" % (type(exc).__name__, exc))
                    continue
                usable = [o for o in out if not (isinstance(o.get("value"), str)
                                                 and not o["value"].strip())]
                if not usable:
                    broken.setdefault(key, set()).add("no usable option")
        self.assertEqual(broken, {},
                         "generators failed: %s" % json.dumps(
                             {k: sorted(v) for k, v in broken.items()}, indent=2))

    def test_option_shape_is_always_correct(self):
        for key, fn in sorted(G.REGISTRY.items()):
            for o in fn(self.contexts[0], 6):
                self.assertIn("label", o, key)
                self.assertIn("value", o, key)
                self.assertIn("rationale", o, key)
                self.assertIsInstance(o["flags"], list, key)
                self.assertIsInstance(o["label"], str, key)

    def test_table_generators_return_rows_of_the_right_width(self):
        for f in FLOW.all_fields():
            if f.kind != "table":
                continue
            for o in G.generate(f.gen, self.contexts[0], 6):
                if isinstance(o["value"], list):
                    self.assertLessEqual(
                        len(o["value"]), len(f.columns) + 1,
                        "%s row is wider than its columns" % f.key)

    def test_generators_react_to_the_operation_type(self):
        off = G.generate("coa_statement",
                         {"operation_type": "Offensive Operation: Attack"}, 4)
        deff = G.generate("coa_statement",
                          {"operation_type": "Defensive Operation: Area Defense"},
                          4)
        self.assertNotEqual(off[0]["value"], deff[0]["value"])
        self.assertIn("defen", deff[0]["value"].lower())

    def test_generators_react_to_the_echelon(self):
        bct = G.generate("task_organization",
                         {"echelon": "Brigade Combat Team (BCT)"}, 4)
        bn = G.generate("task_organization",
                        {"echelon": "Battalion / Squadron"}, 4)
        self.assertNotEqual(bct[0]["value"], bn[0]["value"])

    def test_generators_use_the_selected_environment(self):
        pac = G.generate("enemy_composition", {"oe_framework": "DATE Pacific",
                                               "opfor_posture": "Peer"}, 3)
        text = " ".join(str(o["value"]) for o in pac)
        self.assertTrue("OLVANA" in text.upper() or "BELESIA" in text.upper()
                        or "TORBIA" in text.upper())

    def test_unknown_generator_degrades_gracefully(self):
        out = G.generate("no_such_generator", {}, 5)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["value"], "")

    def test_a_raising_generator_is_contained(self):
        G.REGISTRY["_explode"] = lambda ctx, n: 1 / 0
        try:
            out = G.generate("_explode", {}, 3)
            self.assertEqual(len(out), 1)
            self.assertIn("Template error", out[0]["rationale"])
        finally:
            del G.REGISTRY["_explode"]

    # Ask for far more options than any generator holds, so nothing is hidden
    # behind the n cut. Several generators reorder their list by threat
    # posture, which means a low n shows only whatever floats to the top —
    # exactly how an offending option can sit unnoticed for a year.
    SWEEP_N = 40

    def _every_option_text(self):
        """Every word every generator can emit, across every context."""
        for key, fn in sorted(G.REGISTRY.items()):
            for ctx in self.contexts:
                for o in fn(ctx, self.SWEEP_N):
                    yield key, " ".join([
                        str(o.get("label") or ""), str(o.get("value") or ""),
                        str(o.get("rationale") or ""),
                        " ".join(str(f) for f in (o.get("flags") or [])),
                    ]).lower()

    def test_notional_names_only(self):
        """No generator may name a real country or a real current operation."""
        real = ["russia", "ukraine", "china", "iran", "north korea", "iraq",
                "afghanistan", "syria", "taiwan", "israel", "gaza"]
        for key, blob in self._every_option_text():
            for name in real:
                self.assertNotIn(name, blob, "%s mentions %s" % (key, name))

    def test_no_generator_mentions_classification(self):
        """Marking, handling, and release are decisions for people.

        The tool takes no position on them, so no generated option may raise
        the subject — not as a marking, not as a caveat, not in passing.
        """
        for key, blob in self._every_option_text():
            for word in CLASSIFICATION_WORDS:
                self.assertNotIn(word, blob, "%s mentions %s" % (key, word))


CLASSIFICATION_WORDS = [
    "classified", "classification", "unclassified", "declassif",
    "top secret", "noforn", "fouo", "for official use only",
    "controlled unclassified", "releasable to", "rel to usa",
]


class TestNoClassificationAnywhere(unittest.TestCase):
    """The constraint holds across the whole tool, not only the generators.

    Field labels, plain-English help, doctrinal notes, the OPORD skeleton, the
    default prompts, and the interface text are all places the tool speaks in
    its own voice. None of them may raise classification. The doctrine corpus
    is exempt — those are source documents, not the tool talking.
    """

    def _assert_clean(self, text, where):
        low = (text or "").lower()
        for word in CLASSIFICATION_WORDS:
            self.assertNotIn(word, low, "%s mentions %s" % (where, word))

    def test_flow_definition_is_clean(self):
        from harness.mdmp.flow_def import FLOW
        for step in FLOW.steps:
            self._assert_clean("%s %s" % (step.title, step.purpose or ""),
                               "step %s" % step.key)
            for f in step.fields:
                self._assert_clean(
                    " ".join([f.label, f.plain or "", f.doctrine or "",
                              " ".join(f.columns or [])]),
                    "field %s" % f.key)

    def test_opord_skeleton_is_clean(self):
        from harness.mdmp import doctrine
        for node in doctrine.OPORD_SKELETON:
            self._assert_clean(
                " ".join(str(node.get(k) or "")
                         for k in ("title", "guidance")),
                "opord node %s" % node.get("key"))

    def test_default_prompts_are_clean(self):
        from harness.agent import prompts as P
        self._assert_clean(P.DEFAULT_SYSTEM, "default system prompt")
        self._assert_clean(P.DEFAULT_TEMPLATE, "default task template")

    def test_interface_text_is_clean(self):
        import os
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name in ("static/app.js", "static/index.html", "static/style.css"):
            path = os.path.join(root, name)
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8") as fh:
                self._assert_clean(fh.read(), name)


if __name__ == "__main__":
    unittest.main()
