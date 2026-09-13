"""freshness-and-corroboration: each rule's true positive, the look-alikes its
controls exist to stop, and its not-assessed path. Every emitted finding is
derived and validated against the finding schema."""

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
    "freshness_diagnose", ROOT / "skills" / "freshness-and-corroboration" / "scripts" / "diagnose.py")
diagnose = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(diagnose)

BASE = json.loads((ROOT / "tests" / "fixtures" / "evidence" / "minimal.evidence.json").read_text(encoding="utf-8"))
SCHEMAS = {name: json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
           for name in ("evidence.schema.json", "finding.schema.json", "report.schema.json")}
NOW = "2026-09-13T00:00:00Z"


def article(path, confidence=0.9, published=None, visible=(), status=200, page_type="article", lang="en"):
    p = copy.deepcopy(BASE["pages"][1])
    url = "http://localhost:8000" + path
    p.update({"url": url, "final_url": url, "status": status, "page_type": page_type,
              "page_type_confidence": confidence, "lang": lang})
    p["dates"] = {"visible_dates": list(visible), "schema_date_modified": None,
                  "schema_date_published": published, "http_last_modified": "Fri, 11 Sep 2026 08:09:09 GMT"}
    return p


def claim(confidence="high", ambiguity="low", value="1932"):
    return {"id": "C-001", "from_candidates": ["CC-001"], "kind": "founded_year", "value_normalized": value,
            "first_party_confidence": confidence, "entity_ambiguity": ambiguity}


def hit(origin, asserted, matches, url="https://www.wikidata.org/wiki/Q1"):
    return {"claim_id": "C-001", "origin": origin, "url": url, "asserted_value": asserted,
            "matches_current": matches, "retrieved_at": NOW}


def bundle(pages=None, claims=(), hits=(), egress=True, attempted=True):
    e = copy.deepcopy(BASE)
    if pages is not None:
        e["pages"] = pages
    e["run_context"]["capabilities"]["egress"] = egress
    e["canonical_claims"] = list(claims)
    e["external"].update({"attempted": attempted, "method": "keyless" if attempted else "none",
                          "frontier_size": len(hits), "hits": list(hits),
                          "origins": [{"registrable_domain": h["origin"], "source_type": "encyclopedic",
                                       "urls": [h["url"]], "syndication_cluster": None, "brand_owned": False}
                                      for h in hits]})
    return e


class RuleCase(unittest.TestCase):
    def outcome(self, evidence, rule_id):
        self.assertFalse(Validator(SCHEMAS["evidence.schema.json"], SCHEMAS).errors(evidence))
        result = diagnose.diagnose(evidence)
        for f in result["findings"]:
            self.assertFalse(Validator(SCHEMAS["finding.schema.json"], SCHEMAS).errors(sev_mod.derive(copy.deepcopy(f))))
            self.assertTrue(f["false_positive_controls_applied"] and f["exceptions_checked"])
        ids = sorted({x["rule_id"] for k in ("findings", "not_assessed", "checks_passed") for x in result[k]})
        self.assertEqual(ids, ["FRC-001", "FRC-002"])
        fired = [f for f in result["findings"] if f["rule_id"] == rule_id]
        if fired:
            return "fired", fired[0]
        if any(n["rule_id"] == rule_id for n in result["not_assessed"]):
            return "not_assessed", None
        return "passed", None


class TestFRC001(RuleCase):
    def test_undated_article_template_fires(self):
        got, f = self.outcome(bundle([article("/a%d" % i) for i in range(3)]), "FRC-001")
        self.assertEqual((got, f["scope"]["pages_affected"]), ("fired", 3))

    def test_any_visible_or_structured_date_counts(self):
        pages = [article("/a1", visible=["2026-09-01"]), article("/a2", published="2026-09-01T00:00:00Z"),
                 article("/a3")]
        self.assertEqual(self.outcome(bundle(pages), "FRC-001")[0], "passed")

    def test_http_last_modified_is_not_an_article_date(self):
        got, _ = self.outcome(bundle([article("/a%d" % i) for i in range(2)]), "FRC-001")
        self.assertEqual(got, "fired")

    def test_low_confidence_listings_never_count(self):
        pages = [article("/blog%d" % i, confidence=0.6) for i in range(4)]
        self.assertEqual(self.outcome(bundle(pages), "FRC-001")[0], "not_assessed")

    def test_dates_in_languages_the_audit_cannot_read_are_never_called_absent(self):
        hindi = [article("/hi%d" % i, lang="hi-IN") for i in range(3)]
        got, _ = self.outcome(bundle(hindi), "FRC-001")
        self.assertEqual(got, "not_assessed", "a date written in Hindi is invisible to the extractor, not absent")
        result = diagnose.diagnose(bundle(hindi))
        self.assertIn("3 further pages", [n for n in result["not_assessed"] if n["rule_id"] == "FRC-001"][0]["reason"])
        english = [article("/en%d" % i, lang="en-GB") for i in range(2)] + [article("/x", lang=None)]
        self.assertEqual(self.outcome(bundle(english), "FRC-001")[0], "fired")

    def test_refused_pages_never_count(self):
        self.assertEqual(self.outcome(bundle([article("/a%d" % i, status=403) for i in range(3)]), "FRC-001")[0],
                         "not_assessed")


class TestFRC002(RuleCase):
    def test_wikidata_disagreement_is_a_risk(self):
        e = bundle(claims=[claim()], hits=[hit("wikidata.org", "inception 1931", False)])
        got, f = self.outcome(e, "FRC-002")
        self.assertEqual((got, f["status"], f["confidence"]), ("fired", "risk", "medium"))
        self.assertEqual(f["evidence_refs"][0]["layer"], "third_party")
        self.assertIn("not a survey of the open web", f["evidence"])

    def test_wayback_and_prose_hits_are_never_contradictions(self):
        e = bundle(claims=[claim()], hits=[hit("web.archive.org", "first archived snapshot 1997", False,
                                               "https://web.archive.org/web/1997/x"),
                                           hit("en.wikipedia.org", "an article without the year", False,
                                               "https://en.wikipedia.org/wiki/X")])
        self.assertEqual(self.outcome(e, "FRC-002")[0], "not_assessed")

    def test_agreement_passes(self):
        e = bundle(claims=[claim()], hits=[hit("wikidata.org", "inception 1932", True)])
        self.assertEqual(self.outcome(e, "FRC-002")[0], "passed")

    def test_ambiguous_or_low_confidence_claims_are_not_checked(self):
        for c in (claim(ambiguity="high"), claim(confidence="low")):
            e = bundle(claims=[c], hits=[hit("wikidata.org", "inception 1931", False)])
            self.assertEqual(self.outcome(e, "FRC-002")[0], "not_assessed")

    def test_no_egress_is_not_assessed_never_unsupported(self):
        e = bundle(claims=[claim()], egress=False, attempted=False)
        self.assertEqual(self.outcome(e, "FRC-002")[0], "not_assessed")


if __name__ == "__main__":
    unittest.main()
