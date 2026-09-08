"""Tests for the build gate's own machinery.

A gate that has never failed proves nothing, and the two checks that matter most
-- rule-block completeness and evidence-field existence -- have no rule blocks
to inspect until Day 3. These tests feed the parsers and the resolver synthetic
input now, so that the checks are known to bite before there is anything real
for them to bite on.
"""

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check as gate  # noqa: E402
from jsonschema_lite import UnsupportedKeyword, Validator, resolve_field_path  # noqa: E402

EVIDENCE = gate.read_json(str(ROOT / "schemas" / "evidence.schema.json"))
REGISTRY = gate.schema_registry()

COMPLETE_RULE = """### ANS-001 — Example rule

- **Mechanism:** a causal sentence about retrieval.
- **Signal:** the observable condition.
- **Evidence read:** `pages[].text.word_count`, `pages[].page_type`
- **Threshold:** fires above 3, because below that it is template variance.
- **Minimum evidence:** at least 5 sampled pages of the type.
- **False-positive controls:** excluded pages returning non-200.
- **Legitimate exceptions:** single-page sites, detected by crawl.discovered.
- **Confidence:** high with 8 or more pages, medium with 5 to 7.
- **Impact inputs:** blocking false; breadth page; content_importance secondary.
- **Status:** found
- **Symptom tags:** invisible
- **Remediation:** change the template so the fact is present in the response.
- **Success criteria:** the token appears in the raw response on every page.
- **Effort:** low
"""


class TestFrontmatterParser(unittest.TestCase):
    def test_folded_scalar_is_joined(self):
        text = "---\nname: x\ndescription: >-\n  one line\n  and another\nlicense: MIT\n---\n# X\n"
        data = gate.parse_frontmatter(text)
        self.assertEqual(data["name"], "x")
        self.assertEqual(data["description"], "one line and another")
        self.assertEqual(data["license"], "MIT")

    def test_missing_frontmatter_is_an_error(self):
        with self.assertRaises(ValueError):
            gate.parse_frontmatter("# No frontmatter here\n")

    def test_unterminated_frontmatter_is_an_error(self):
        with self.assertRaises(ValueError):
            gate.parse_frontmatter("---\nname: x\n")

    def test_every_shipped_skill_parses_and_declares_what_it_must(self):
        for sid in [gate.ENTRYPOINT, gate.COLLECTOR, *gate.DIAGNOSTICS]:
            with self.subTest(skill=sid):
                data = gate.parse_frontmatter((ROOT / "skills" / sid / "SKILL.md").read_text(encoding="utf-8"))
                for key in gate.REQUIRED_FRONTMATTER:
                    self.assertTrue(data.get(key), "%s is missing %s" % (sid, key))
                self.assertEqual(data["name"], sid)


class TestRuleBlockParser(unittest.TestCase):
    def test_complete_block_yields_all_fourteen_fields(self):
        blocks = gate.parse_rule_blocks(COMPLETE_RULE)
        self.assertEqual(len(blocks), 1)
        rule_id, name, fields = blocks[0]
        self.assertEqual(rule_id, "ANS-001")
        self.assertEqual(name, "Example rule")
        self.assertEqual(sorted(fields), sorted(gate.RULE_FIELDS))
        for field in gate.RULE_FIELDS:
            self.assertTrue(fields[field].strip(), field)

    def test_a_missing_field_is_visible_to_the_check(self):
        broken = COMPLETE_RULE.replace("- **Threshold:** fires above 3, because below that it is template variance.\n", "")
        _rid, _name, fields = gate.parse_rule_blocks(broken)[0]
        self.assertNotIn("Threshold", fields)

    def test_an_empty_field_is_visible_to_the_check(self):
        broken = COMPLETE_RULE.replace("- **Effort:** low", "- **Effort:**")
        _rid, _name, fields = gate.parse_rule_blocks(broken)[0]
        self.assertEqual(fields["Effort"], "")

    def test_multiple_blocks_are_separated(self):
        blocks = gate.parse_rule_blocks(COMPLETE_RULE + COMPLETE_RULE.replace("ANS-001", "ANS-002"))
        self.assertEqual([b[0] for b in blocks], ["ANS-001", "ANS-002"])

    def test_declared_count_is_read(self):
        self.assertEqual(gate.declared_rule_count("Rules defined: 3 of a maximum 12."), (3, 12))
        self.assertEqual(gate.declared_rule_count("nothing here"), (None, None))

    def test_shipped_rule_files_declare_a_budget_matching_their_blocks(self):
        for sid in gate.DIAGNOSTICS:
            with self.subTest(skill=sid):
                text = (ROOT / "skills" / sid / "references" / "rules.md").read_text(encoding="utf-8")
                declared, maximum = gate.declared_rule_count(text)
                self.assertEqual(maximum, gate.MAX_RULES_PER_SKILL)
                self.assertEqual(declared, len(gate.parse_rule_blocks(text)))


class TestEvidenceFieldResolution(unittest.TestCase):
    def test_resolves_real_paths(self):
        for path in (
            "robots",
            "robots.ai_agents.GPTBot",
            "crawl.sampling.strata[].page_type",
            "pages[].raw.text_len",
            "pages[].raw.headings[].level",
            "pages[].jsonld[].fields_present",
            "pages[].dates.visible_dates",
            "external.hits[].matches_current",
            "link_graph.orphans",
        ):
            with self.subTest(path=path):
                self.assertIsInstance(resolve_field_path(EVIDENCE, path, REGISTRY), dict)

    def test_rejects_an_invented_field(self):
        with self.assertRaises(KeyError):
            resolve_field_path(EVIDENCE, "pages[].text.reading_grade_level", REGISTRY)

    def test_rejects_an_invented_top_level_key(self):
        with self.assertRaises(KeyError):
            resolve_field_path(EVIDENCE, "lighthouse.performance", REGISTRY)

    def test_rejects_array_notation_on_an_object(self):
        # dates is an object, so pages[].dates[].visible_dates is wrong even
        # though every name in it exists.
        with self.assertRaises(KeyError):
            resolve_field_path(EVIDENCE, "pages[].dates[].visible_dates", REGISTRY)

    def test_every_allow_list_entry_in_every_skill_resolves(self):
        for sid in gate.DIAGNOSTICS:
            text = (ROOT / "skills" / sid / "references" / "rules.md").read_text(encoding="utf-8")
            section = text.split("## Evidence this skill may read", 1)[1].split("\n## ", 1)[0]
            entries = [t for line in section.splitlines() if line.startswith("- ")
                       for t in gate.backticked(line)]
            self.assertTrue(entries, "%s declares no readable evidence" % sid)
            for entry in entries:
                with self.subTest(skill=sid, path=entry):
                    resolve_field_path(EVIDENCE, entry, REGISTRY)


class TestFindingInvariants(unittest.TestCase):
    """The rules the finding schema deliberately does not encode.

    The schema allows an empty false_positive_controls_applied so that a
    proactive recommendation is not forced to write "n/a" in two arrays. That
    relaxation is only safe because the build gate still requires both arrays on
    an observed defect, which is the case where they matter.
    """

    @staticmethod
    def finding(status, controls, exceptions, severity="medium", priority="P2"):
        return {
            "id": "F-001", "rule_id": "IDM-004", "status": status,
            "severity": severity,
            "suggested_action": {"priority": priority},
            "false_positive_controls_applied": controls,
            "exceptions_checked": exceptions,
        }

    def test_found_requires_both_arrays(self):
        self.assertFalse(gate.finding_invariant_problems(
            self.finding("found", ["price normalisation"], ["quote-on-request"]), "test"))
        for controls, exceptions in (([], ["x"]), (["x"], []), ([], [])):
            with self.subTest(controls=controls, exceptions=exceptions):
                self.assertTrue(gate.finding_invariant_problems(
                    self.finding("found", controls, exceptions), "test"))

    def test_proactive_may_leave_both_empty(self):
        self.assertFalse(gate.finding_invariant_problems(
            self.finding("proactive", [], []), "test"))

    def test_risk_may_leave_both_empty(self):
        self.assertFalse(gate.finding_invariant_problems(
            self.finding("risk", [], [], severity="high", priority="P1"), "test"))

    def test_status_semantics_are_rechecked_on_the_emitted_finding(self):
        self.assertTrue(gate.finding_invariant_problems(
            self.finding("risk", ["x"], ["y"], severity="critical", priority="P0"), "test"))
        self.assertTrue(gate.finding_invariant_problems(
            self.finding("proactive", [], [], severity="high", priority="P2"), "test"))

    def test_every_shipped_fixture_finding_satisfies_them(self):
        for path in sorted((ROOT / "tests" / "fixtures" / "findings").glob("*.json")):
            for finding in gate.read_json(str(path)).get("findings", []):
                self.assertFalse(gate.finding_invariant_problems(finding, path.name))


class TestLiteValidator(unittest.TestCase):
    def test_refuses_a_schema_it_cannot_fully_enforce(self):
        with self.assertRaises(UnsupportedKeyword):
            Validator({"type": "object", "propertyNames": {"pattern": "^a"}})
        # additionalProperties: true would let an invented field through
        # unchecked, which is precisely what the evidence schema exists to stop.
        with self.assertRaises(UnsupportedKeyword):
            Validator({"type": "object", "additionalProperties": True})
        with self.assertRaises(UnsupportedKeyword):
            Validator({"type": "object", "additionalProperties": {"multipleOf": 2}})

    def test_free_form_maps_have_their_values_checked(self):
        # The shape jsonld[].values uses: any key, but every value a string.
        v = Validator({"type": "object", "additionalProperties": {"type": "string"}})
        self.assertTrue(v.is_valid({"offers.price": "12999.00", "name": "X9"}))
        self.assertFalse(v.is_valid({"offers.price": 12999}))

    def test_enforces_the_keywords_our_schemas_rely_on(self):
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["a"],
            "properties": {
                "a": {"type": "string", "minLength": 1, "maxLength": 4, "pattern": "^x"},
                "b": {"type": "array", "minItems": 1, "items": {"enum": ["p", "q"]}},
                "c": {"type": ["integer", "null"], "minimum": 0, "maximum": 3},
            },
        }
        v = Validator(schema)
        self.assertTrue(v.is_valid({"a": "xy", "b": ["p"], "c": None}))
        self.assertFalse(v.is_valid({}))
        self.assertFalse(v.is_valid({"a": "xy", "z": 1}))
        self.assertFalse(v.is_valid({"a": "yy"}))
        self.assertFalse(v.is_valid({"a": "xy", "b": []}))
        self.assertFalse(v.is_valid({"a": "xy", "b": ["r"]}))
        self.assertFalse(v.is_valid({"a": "xy", "c": 9}))
        self.assertFalse(v.is_valid({"a": "xy", "c": True}))
        # maxLength is what stops a collector inlining page text into
        # visible_excerpt and defeating the text-sidecar design.
        self.assertFalse(v.is_valid({"a": "xyzzy"}))

    def test_booleans_are_not_integers(self):
        v = Validator({"type": "integer"})
        self.assertFalse(v.is_valid(True))
        self.assertTrue(v.is_valid(3))


if __name__ == "__main__":
    unittest.main()
