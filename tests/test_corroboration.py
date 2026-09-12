"""Promotion and the off-site probe: the two halves of D9's second pass.

The network is faked here. What these tests pin is the reasoning: which strings
are worth asking the world about, whether a source is about this brand at all,
and whether prose containing a string is the same as prose asserting it.
"""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "site-evidence-collector" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "identity-and-markup" / "scripts"))

import external  # noqa: E402
import promote  # noqa: E402

NOW = "2026-09-13T00:00:00Z"


def candidate(kind, value, method="jsonld", count=3, cid="CC-001"):
    return {"id": cid, "kind": kind, "value_raw": value, "value_normalized": value.casefold(),
            "source_url": "https://brand.example/", "locator": "name",
            "extraction_method": method, "observed_count": count}


class TestPromotion(unittest.TestCase):
    def test_only_corroborable_kinds_are_promoted(self):
        evidence = {"claim_candidates": [
            candidate("legal_name", "Garuda Footwear"),
            candidate("price", "Rs. 799.00", "visible_text", 90, "CC-002"),
            candidate("numeric_claim", "10,000 customers", "visible_text", 4, "CC-003"),
        ]}
        kinds = [c["kind"] for c in promote.promote(evidence)]
        self.assertEqual(kinds, ["legal_name"])

    def test_structured_and_repeated_is_the_only_high_confidence(self):
        def confidence(method, count):
            claims = promote.promote({"claim_candidates": [candidate("legal_name", "X Ltd", method, count)]})
            return claims[0]["first_party_confidence"]
        self.assertEqual(confidence("jsonld", 5), "high")
        self.assertEqual(confidence("jsonld", 1), "medium")
        self.assertEqual(confidence("visible_text", 5), "medium")
        self.assertEqual(confidence("visible_text", 1), "low")

    def test_a_generic_name_is_flagged_ambiguous(self):
        def ambiguity(name):
            claims = promote.promote({"claim_candidates": [candidate("legal_name", name)]})
            return claims[0]["entity_ambiguity"]
        self.assertEqual(ambiguity("Garuda Footwear Private Limited"), "low")
        self.assertEqual(ambiguity("Aster"), "high")       # one short distinctive token
        self.assertEqual(ambiguity("Online Store India"), "high")   # nothing distinctive
        self.assertEqual(ambiguity("Cloudwright"), "medium")

    def test_the_legal_name_is_ranked_first_whatever_else_repeats(self):
        evidence = {"claim_candidates": [
            candidate("tagline", "Built to fly", "jsonld", 40, "CC-001"),
            candidate("legal_name", "Garuda Footwear", "jsonld", 2, "CC-002"),
        ]}
        claims = promote.promote(evidence)
        self.assertEqual(claims[0]["kind"], "legal_name")
        self.assertEqual(claims[0]["id"], "C-001")

    def test_promotion_is_deterministic_and_bounded(self):
        evidence = {"claim_candidates": [
            candidate("product_name", "Item %d" % n, "jsonld", 1, "CC-%03d" % n) for n in range(1, 30)]}
        first = promote.promote(evidence)
        self.assertEqual(len(first), promote.MAX_CLAIMS)
        self.assertEqual([(c["id"], c["value_normalized"]) for c in first],
                         [(c["id"], c["value_normalized"]) for c in promote.promote(evidence)])


class TestAsserts(unittest.TestCase):
    def test_a_name_is_asserted_by_containing_it(self):
        claim = {"kind": "legal_name", "value_normalized": "garuda footwear"}
        self.assertTrue(external.asserts("Garuda Footwear is an Indian maker of shoes.", claim))
        self.assertFalse(external.asserts("An unrelated company entirely.", claim))

    def test_a_year_needs_a_founding_word_beside_it(self):
        claim = {"kind": "founded_year", "value_normalized": "1932"}
        self.assertTrue(external.asserts("The paper was founded in 1932 in Madras.", claim))
        self.assertTrue(external.asserts("Established 1932.", claim))
        # The failure this was written for: citation dates are four digits too.
        self.assertFalse(external.asserts("Retrieved 18 December 1932. Archived from the original.", claim))

    def test_empty_prose_asserts_nothing(self):
        self.assertFalse(external.asserts("", {"kind": "legal_name", "value_normalized": "x"}))
        self.assertFalse(external.asserts("anything", {"kind": "legal_name", "value_normalized": ""}))


class TestOriginBookkeeping(unittest.TestCase):
    def test_source_types_come_from_the_closed_vocabulary(self):
        for domain, expected in (("wikipedia.org", "encyclopedic"), ("web.archive.org", "directory"),
                                 ("linkedin.com", "social"), ("amazon.in", "retailer"),
                                 ("trustpilot.com", "review"), ("reddit.com", "forum"),
                                 ("thehindubusinessline.com", "directory")):
            with self.subTest(domain=domain):
                self.assertIn(external.classify_origin(domain),
                              ("encyclopedic", "retailer", "directory", "news",
                               "review", "forum", "social"))
                self.assertEqual(external.classify_origin(domain), expected)

    def test_the_brands_own_domain_is_marked_brand_owned(self):
        probe = external.Probe("brand.example")
        probe.note_origin("https://brand.example/about")
        probe.note_origin("https://en.wikipedia.org/wiki/Brand")
        owned = {o["registrable_domain"]: o["brand_owned"] for o in probe.result(True, "keyless")["origins"]}
        self.assertTrue(owned["brand.example"])
        self.assertFalse(owned["wikipedia.org"])

    def test_hits_are_bounded_and_the_truncation_is_declared(self):
        probe = external.Probe("brand.example")
        claim = {"id": "C-001", "kind": "legal_name", "value_normalized": "brand"}
        for n in range(external.MAX_HITS + 5):
            probe.note_hit(claim, "wikipedia.org", "https://x/%d" % n, "brand", NOW)
        result = probe.result(True, "keyless")
        self.assertEqual(len(result["hits"]), external.MAX_HITS)
        self.assertTrue(result["truncated"])

    def test_frontier_size_counts_what_was_looked_at_not_what_matched(self):
        probe = external.Probe("brand.example")
        for n in range(4):
            probe.note_origin("https://en.wikipedia.org/wiki/Article%d" % n)
        result = probe.result(True, "keyless")
        self.assertEqual(result["frontier_size"], 4)
        self.assertEqual(result["hits"], [])
        self.assertEqual(len(result["origins"]), 1)      # one domain, four urls


class FakeResponse:
    def __init__(self, text, status=200):
        self.text, self.status = text, status
        self.body = text.encode()
        self.ok = 200 <= status <= 299
        self.content_type = "text/html"


class FakeRun:
    """A Run whose network is a dictionary and whose robots.txt allows all."""

    def __init__(self, pages, blocked=()):
        self.pages, self.blocked, self.asked = pages, set(blocked), []
        run = self

        class Fetcher:
            def get(self, url, **kwargs):
                run.asked.append(url)
                return FakeResponse(*run.pages.get(url, ("", 404)))
        self.fetcher = Fetcher()

    def allowed(self, url, deadline=None):
        return url not in self.blocked


class TestSameAsVerification(unittest.TestCase):
    def test_a_dead_declared_profile_is_recorded_against_the_claim(self):
        claim = {"id": "C-001", "kind": "legal_name", "value_normalized": "garuda footwear"}
        probe = external.Probe("brand.example")
        run = FakeRun({"https://linkedin.com/company/garuda": ("", 404)})
        external._same_as(run, probe, [claim], ["https://linkedin.com/company/garuda"], 1e9, NOW)
        hit = probe.result(True, "keyless")["hits"][0]
        self.assertIn("404", hit["asserted_value"])
        self.assertFalse(hit["matches_current"])

    def test_a_profile_that_does_not_name_the_brand_is_a_broken_link_in_the_graph(self):
        claim = {"id": "C-001", "kind": "legal_name", "value_normalized": "garuda footwear"}
        probe = external.Probe("brand.example")
        run = FakeRun({"https://x.com/someoneelse": ("<html><body>A different company</body></html>", 200)})
        external._same_as(run, probe, [claim], ["https://x.com/someoneelse"], 1e9, NOW)
        hit = probe.result(True, "keyless")["hits"][0]
        self.assertFalse(hit["matches_current"])
        self.assertIn("does not name the brand", hit["asserted_value"])

    def test_a_profile_disallowed_by_its_own_robots_is_not_fetched(self):
        claim = {"id": "C-001", "kind": "legal_name", "value_normalized": "garuda"}
        probe = external.Probe("brand.example")
        target = "https://blocked.example/profile"
        run = FakeRun({target: ("garuda", 200)}, blocked=[target])
        external._same_as(run, probe, [claim], [target], 1e9, NOW)
        self.assertEqual(run.asked, [])
        self.assertEqual(probe.result(True, "keyless")["hits"], [])


if __name__ == "__main__":
    unittest.main()
