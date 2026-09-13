"""Claim-candidate extraction: observation with provenance, never interpretation.

The bar for candidacy is low by design (D9, W5): identity promotes candidates to
claims, and a candidate that is noise costs one row that nothing promotes. What
these tests pin is that the *provenance* is right, that the same bundle twice
gives the same ids, and that a nested entity is never mistaken for the page's
own subject.
"""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "site-evidence-collector" / "scripts"))

import claims  # noqa: E402


def jsonld(type_name, values):
    return [{"type": type_name, "valid": True, "errors": [], "fields_present": sorted(values),
             "values": values, "contradicts_visible_text": False}]


class TestJsonLd(unittest.TestCase):
    def test_an_organisation_name_is_a_legal_name(self):
        out = []
        claims.from_jsonld(jsonld("Organization", {"name": "Garuda Footwear Pvt Ltd"}),
                           "https://x.example/", out)
        self.assertEqual([(c["kind"], c["value_raw"], c["extraction_method"]) for c in out],
                         [("legal_name", "Garuda Footwear Pvt Ltd", "jsonld")])

    def test_a_product_name_is_a_product_name(self):
        out = []
        claims.from_jsonld(jsonld("Product", {"name": "Ratz Tee"}), "https://x.example/p", out)
        self.assertEqual(out[0]["kind"], "product_name")

    def test_a_nested_brand_is_the_company_not_the_product(self):
        # The trap this was written for: leaf-matching "name" turns every item
        # in a catalogue into a product called after the company.
        out = []
        claims.from_jsonld(jsonld("Product", {"name": "Ratz Tee", "brand.name": "KESTRELWEAR"}),
                           "https://x.example/p", out)
        kinds = {(c["kind"], c["value_raw"]) for c in out}
        self.assertIn(("product_name", "Ratz Tee"), kinds)
        self.assertIn(("legal_name", "KESTRELWEAR"), kinds)
        self.assertNotIn(("product_name", "KESTRELWEAR"), kinds)

    def test_a_nested_name_of_an_unknown_entity_is_not_claimed(self):
        out = []
        claims.from_jsonld(jsonld("Product", {"name": "Tee", "seller.name": "Some Reseller"}),
                           "https://x.example/p", out)
        self.assertNotIn("Some Reseller", [c["value_raw"] for c in out])

    def test_an_address_is_one_claim_not_five_fragments(self):
        out = []
        claims.from_jsonld(jsonld("LocalBusiness", {
            "address.streetAddress": "12 MG Road", "address.addressLocality": "Bengaluru",
            "address.postalCode": "560001"}), "https://x.example/", out)
        addresses = [c for c in out if c["kind"] == "address"]
        self.assertEqual(len(addresses), 1)
        for part in ("12 MG Road", "Bengaluru", "560001"):
            self.assertIn(part, addresses[0]["value_raw"])

    def test_a_founding_date_yields_the_year_alone(self):
        out = []
        claims.from_jsonld(jsonld("Organization", {"foundingDate": "1998-04-02"}),
                           "https://x.example/", out)
        self.assertEqual([(c["kind"], c["value_raw"]) for c in out], [("founded_year", "1998")])


class TestVisibleText(unittest.TestCase):
    def test_a_year_is_a_claim_only_when_a_word_makes_it_one(self):
        out = []
        claims.from_text("Serving customers since 1998. Our 2024 catalogue is out.",
                         "https://x.example/", out)
        self.assertEqual([(c["kind"], c["value_raw"]) for c in out], [("founded_year", "1998")])

    def test_prices_and_counts_are_found_with_their_offsets(self):
        out = []
        claims.from_text("Only Rs. 1,299.00 today. Trusted by 10,000+ customers.",
                         "https://x.example/", out)
        kinds = {c["kind"]: c for c in out}
        self.assertEqual(kinds["price"]["value_raw"], "Rs. 1,299.00")
        self.assertIn("customers", kinds["numeric_claim"]["value_raw"])
        for candidate in out:
            self.assertTrue(candidate["locator"].startswith("text@"))

    def test_a_bare_number_is_not_a_claim(self):
        out = []
        claims.from_text("Section 4 covers 12 topics across 3 chapters.", "https://x.example/", out)
        self.assertEqual(out, [])

    def test_a_long_home_page_heading_is_not_a_tagline(self):
        out = []
        claims.from_headings([{"level": 1, "text": "x" * 200}], "home", "https://x.example/", out)
        self.assertEqual(out, [])
        claims.from_headings([{"level": 1, "text": "Built to Fly"}], "home", "https://x.example/", out)
        self.assertEqual(out[0]["kind"], "tagline")


class TestAggregate(unittest.TestCase):
    def test_the_same_string_seen_twice_is_one_candidate_counted_twice(self):
        out = []
        for url in ("https://x.example/a", "https://x.example/b"):
            claims.from_text("Serving since 1998.", url, out)
        candidates, dropped = claims.aggregate(out)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["observed_count"], 2)
        self.assertEqual(candidates[0]["source_url"], "https://x.example/a")
        self.assertEqual(dropped, 0)

    def test_normalisation_folds_case_and_trailing_punctuation(self):
        out = []
        claims.from_headings([{"level": 1, "text": "Built to Fly"}], "home", "https://x.example/1", out)
        claims.from_headings([{"level": 1, "text": "built to fly."}], "home", "https://x.example/2", out)
        candidates, _ = claims.aggregate(out)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["observed_count"], 2)

    def test_ids_are_stable_across_runs(self):
        def build():
            out = []
            claims.from_text("Rs. 99.00 and Rs. 10.00 and since 2001", "https://x.example/", out)
            return claims.aggregate(out)[0]
        self.assertEqual([(c["id"], c["value_normalized"]) for c in build()],
                         [(c["id"], c["value_normalized"]) for c in build()])

    def test_overflow_is_reported_rather_than_silently_dropped(self):
        out = []
        for n in range(12):
            claims.from_text("Rs. %d.00" % n, "https://x.example/", out)
        candidates, dropped = claims.aggregate(out, cap=5)
        self.assertEqual(len(candidates), 5)
        self.assertEqual(dropped, 7)

    def test_every_candidate_carries_the_fields_the_schema_requires(self):
        out = []
        claims.from_jsonld(jsonld("Organization", {"name": "Acme"}), "https://x.example/", out)
        claims.from_text("Rs. 5.00", "https://x.example/", out)
        for candidate in claims.aggregate(out)[0]:
            self.assertEqual(sorted(candidate), sorted(
                ["id", "kind", "value_raw", "value_normalized", "source_url", "locator",
                 "extraction_method", "observed_count"]))
            self.assertRegex(candidate["id"], r"^CC-\d{3,}$")
            self.assertIn(candidate["extraction_method"], ("visible_text", "jsonld", "meta"))
            self.assertGreaterEqual(candidate["observed_count"], 1)


if __name__ == "__main__":
    unittest.main()
