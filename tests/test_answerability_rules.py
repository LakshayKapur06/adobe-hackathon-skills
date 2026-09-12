"""answerability: ANS-001's recommendation, the pages it must leave alone, and its
not-assessed path. Every emitted finding is derived and validated."""

import copy
import importlib.util
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "audit-orchestrator" / "scripts"))

import severity as sev_mod  # noqa: E402
from jsonschema_lite import Validator  # noqa: E402

# Loaded by path under a unique name: every diagnostic's script is called
# diagnose.py, and one test process imports several of them.
_spec = importlib.util.spec_from_file_location(
    "answerability_diagnose", ROOT / "skills" / "answerability" / "scripts" / "diagnose.py")
diagnose = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(diagnose)

BASE = json.loads((ROOT / "tests" / "fixtures" / "evidence" / "minimal.evidence.json").read_text(encoding="utf-8"))
SCHEMAS = {name: json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
           for name in ("evidence.schema.json", "finding.schema.json", "report.schema.json")}


def page(path, page_type="article", words=2000, headings=1, status=200, jsonld_type=None):
    p = copy.deepcopy(BASE["pages"][1])
    url = "http://localhost:8000" + path
    p.update({"url": url, "final_url": url, "status": status, "page_type": page_type})
    p["text"]["word_count"] = words
    p["raw"]["headings"] = [{"level": 2, "text": "H%d" % i} for i in range(headings)]
    p["jsonld"] = [{"type": jsonld_type, "valid": True, "errors": [], "fields_present": ["headline"],
                    "values": {"headline": "x"}, "contradicts_visible_text": False}] if jsonld_type else []
    return p


class TestANS001(unittest.TestCase):
    def outcome(self, pages):
        e = copy.deepcopy(BASE)
        e["pages"] = pages
        self.assertFalse(Validator(SCHEMAS["evidence.schema.json"], SCHEMAS).errors(e))
        result = diagnose.diagnose(e)
        for f in result["findings"]:
            derived = sev_mod.derive(copy.deepcopy(f))
            self.assertFalse(Validator(SCHEMAS["finding.schema.json"], SCHEMAS).errors(derived))
            self.assertEqual((derived["severity"], derived["suggested_action"]["priority"]), ("medium", "P2"))
        if result["findings"]:
            return "fired", result["findings"][0]
        if result["not_assessed"]:
            return "not_assessed", None
        self.assertTrue(result["checks_passed"])
        return "passed", None

    def test_unheaded_long_docs_are_recommended_sections(self):
        got, f = self.outcome([page("/d%d" % i, "doc", 2400, 1) for i in range(3)])
        self.assertEqual((got, f["status"], f["scope"]["page_types"]), ("fired", "proactive", ["doc"]))

    def test_sectioned_long_pages_pass(self):
        self.assertEqual(self.outcome([page("/d%d" % i, "doc", 2400, 8) for i in range(3)])[0], "passed")

    def test_news_reporting_is_excluded(self):
        pages = [page("/n%d" % i, "article", 2400, 1, jsonld_type="NewsArticle") for i in range(4)]
        self.assertEqual(self.outcome(pages)[0], "not_assessed")

    def test_short_pages_and_other_types_never_count(self):
        pages = [page("/a%d" % i, "article", 900, 0) for i in range(3)] + \
                [page("/p%d" % i, "product", 3000, 0) for i in range(3)]
        self.assertEqual(self.outcome(pages)[0], "not_assessed")

    def test_minority_does_not_fire(self):
        pages = [page("/a1", "article", 2000, 1)] + [page("/a%d" % i, "article", 2000, 6) for i in range(2, 5)]
        self.assertEqual(self.outcome(pages)[0], "passed")

    def test_refused_pages_never_count(self):
        pages = [page("/d%d" % i, "doc", 2400, 0, status=403) for i in range(3)]
        self.assertEqual(self.outcome(pages)[0], "not_assessed")


if __name__ == "__main__":
    unittest.main()
