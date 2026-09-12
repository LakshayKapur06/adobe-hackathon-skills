"""HTML extraction and URL handling. Every value here lands in PageEvidence."""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "site-evidence-collector" / "scripts"))

import extract  # noqa: E402
import urls  # noqa: E402

BASE = "https://www.shop.example/products/x9"

PAGE = """<!doctype html>
<html lang="en-IN"><head>
<title>Title is not body text</title>
<meta name="robots" content="Index, NoFollow">
<meta property="og:title" content="og is not rdfa structure">
<link rel="canonical" href="/products/x9">
<link rel="alternate" hreflang="hi-IN" href="https://www.shop.example/hi/products/x9">
<script>var notText = "script";</script>
<style>.x{}</style>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product",
 "name":"Velocity X9","offers":{"@type":"Offer","price":"12999.00","priceCurrency":"INR"},
 "sameAs":["https://a.example/x9","https://b.example/x9"]}</script>
</head><body>
<header><a href="/">Shop</a><nav><a href="/collections/shoes">Shoes</a></nav></header>
<main>
  <section id="specs"><h2>Specifications</h2><p>Weight 240 grams. Drop 8 millimetres.</p></section>
  <h1 id="top">Velocity X9</h1>
  <article><header><p>Article header is content, not boilerplate</p></header></article>
  <p>Price ₹12,999 inclusive of taxes. Last updated 1 August 2026, restocked March 3, 2025.</p>
  <div hidden>Hidden text never counts</div>
  <div style="display: none">Nor does this</div>
  <noscript>Enable JavaScript for reviews</noscript>
  <div id="app"><h3>Reviews</h3></div>
  <img src="/img/spec-sheet.png" alt="">
  <img src="/img/hero.jpg">
  <a href="https://shop.example/about" rel="nofollow">About us</a>
  <a href="https://elsewhere.example/">Partner</a>
  <a href="mailto:hi@shop.example">Mail</a>
  <a href="/cart" aria-label="Cart"><img src="/cart.svg" alt="cart"></a>
  <table><tr><td>a<td>b</table><iframe src="/x"></iframe><form></form>
  <div itemscope itemtype="https://schema.org/Thing"></div>
  <div id="onetrust-banner-sdk">We use cookies</div>
  <div role="dialog" aria-modal="true">Sign up</div>
  <div role="dialog" aria-modal="true" hidden>Hidden dialog</div>
</main>
<footer><p>Footer text</p></footer>
</body></html>"""


class TestParseDocument(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = extract.parse_document(PAGE, BASE)

    def test_hidden_text_is_counted_but_never_part_of_the_page_text(self):
        # contracts-v9: visible text is the page text; hidden text is measured
        # separately because a fetcher that ignores CSS still extracts it.
        doc = extract.parse_document(
            '<html><body><p>Visible words here</p><div hidden><p>secret one</p></div>'
            '<div style="display: none"><p>secret two</p></div><script>var x = "never text"</script>'
            '<template><p>template text</p></template></body></html>', "https://x.example/")
        self.assertEqual(doc["text"].strip(), "Visible words here")
        self.assertEqual(doc["hidden_text_len"], len("secret one") + len("secret two"))

    def test_text_excludes_head_script_style_and_hidden(self):
        text = self.doc["text"]
        for absent in ("Title is not body text", "notText", "Hidden text", "Nor does this", "Hidden dialog"):
            self.assertNotIn(absent, text)
        for present in ("Velocity X9", "Weight 240 grams", "Enable JavaScript for reviews"):
            self.assertIn(present, text)
        self.assertEqual(self.doc["text_len"], len(text))
        self.assertEqual(self.doc["text_hash"], extract.text_hash(text))

    def test_headings_in_document_order(self):
        self.assertEqual([(h["level"], h["text"]) for h in self.doc["headings"]],
                         [(2, "Specifications"), (1, "Velocity X9"), (3, "Reviews")])

    def test_anchors_pair_ids_with_the_heading_they_label(self):
        anchors = [(a["id"], a["heading_text"]) for a in self.doc["anchors"]]
        self.assertIn(("specs", "Specifications"), anchors)       # section id -> its first heading
        self.assertIn(("top", "Velocity X9"), anchors)            # heading's own id
        self.assertNotIn("app", [a[0] for a in anchors])          # a div wrapper labels nothing

    def test_links(self):
        links = {l["href"]: l for l in self.doc["links"]}
        self.assertTrue(links["https://shop.example/about"]["internal"])   # apex of www host
        self.assertEqual(links["https://shop.example/about"]["rel"], "nofollow")
        self.assertFalse(links["https://elsewhere.example/"]["internal"])
        self.assertNotIn("mailto:hi@shop.example", links)
        self.assertEqual(links["/cart"]["anchor"], "Cart")             # aria-label fallback
        self.assertNotIn("https://elsewhere.example/", self.doc["resolved_links"])

    def test_images_distinguish_missing_from_empty_alt(self):
        images = {i["src"]: i for i in self.doc["images"]}
        self.assertEqual(images["/img/spec-sheet.png"]["alt"], "")
        self.assertIsNone(images["/img/hero.jpg"]["alt"])
        self.assertTrue(images["/img/spec-sheet.png"]["text_likely"])
        self.assertFalse(images["/img/hero.jpg"]["text_likely"])

    def test_head_metadata(self):
        self.assertEqual(self.doc["meta_robots"], ["index", "nofollow"])
        self.assertEqual(self.doc["canonical"], "https://www.shop.example/products/x9")
        self.assertEqual(self.doc["lang"], "en-IN")
        self.assertEqual(self.doc["hreflang"], ["hi-IN"])

    def test_counts_and_structure_markers(self):
        self.assertEqual((self.doc["tables"], self.doc["iframes"], self.doc["forms"]), (1, 1, 1))
        self.assertTrue(self.doc["microdata_or_rdfa"])

    def test_og_property_alone_is_not_rdfa(self):
        doc = extract.parse_document('<html><head><meta property="og:title" content="x"></head><body>t</body></html>', BASE)
        self.assertFalse(doc["microdata_or_rdfa"])

    def test_boilerplate_counts_page_level_chrome_only(self):
        ratio = self.doc["boilerplate_ratio"]
        self.assertGreater(ratio, 0)
        self.assertLess(ratio, 0.2)
        doc = extract.parse_document("<body><article><header><p>Byline</p></header><p>Body</p></article></body>", BASE)
        self.assertEqual(doc["boilerplate_ratio"], 0.0)

    def test_obstructions(self):
        kinds = {o["kind"]: o["evidence"] for o in self.doc["obstructions"]}
        self.assertIn("onetrust", kinds["cookie_wall"])
        self.assertIn("modal", kinds)

    def test_link_and_image_caps_are_recorded_not_silent(self):
        body = "".join('<a href="/p/%d">p</a>' % i for i in range(501))
        body += "".join('<img src="/i/%d.png" alt="">' % i for i in range(201))
        doc = extract.parse_document("<body>%s</body>" % body, BASE)
        self.assertEqual(len(doc["links"]), 500)
        self.assertEqual(len(doc["images"]), 200)
        self.assertIn(("raw.links", 500, 501), doc["truncations"])
        self.assertIn(("raw.images", 200, 201), doc["truncations"])

    def test_the_fixture_site_parses_as_its_evidence_says(self):
        about = (ROOT / "tests" / "fixtures" / "site" / "about.html").read_text(encoding="utf-8")
        doc = extract.parse_document(about, "http://localhost:8000/about.html")
        self.assertEqual([a["id"] for a in doc["anchors"]], ["calibration", "who-does-it"])
        self.assertEqual(extract.visible_dates(doc["text"]), ["2026-08-01"])


class TestTextHelpers(unittest.TestCase):
    def test_excerpt_cuts_at_a_word_boundary(self):
        text = "word " * 400
        cut = extract.excerpt(text, 23)
        self.assertLessEqual(len(cut), 23)
        self.assertFalse(cut.endswith(" "))
        self.assertTrue(cut.endswith("word"))

    def test_visible_dates_normalise_and_keep_order(self):
        text = "Published 2024-12-31. Updated 1 August 2026 and again March 3, 2025. Not 2024-02-30."
        self.assertEqual(extract.visible_dates(text), ["2024-12-31", "2026-08-01", "2025-03-03"])


class TestJsonLd(unittest.TestCase):
    def test_nodes_values_and_list_joining(self):
        doc = extract.parse_document(PAGE, BASE)
        entries, truncation = extract.jsonld_entries(doc["jsonld_scripts"], doc["text"])
        self.assertIsNone(truncation)
        product = entries[0]
        self.assertEqual(product["type"], "Product")
        self.assertTrue(product["valid"])
        self.assertEqual(product["values"]["offers.price"], "12999.00")
        self.assertEqual(product["values"]["sameAs"], "https://a.example/x9 | https://b.example/x9")
        self.assertIn("offers", product["fields_present"])
        self.assertIn("offers.priceCurrency", product["fields_present"])
        self.assertNotIn("@context", product["values"])

    def test_graph_is_split_into_nodes(self):
        script = '{"@context":"https://schema.org","@graph":[{"@type":"Organization","name":"A"},{"@type":"WebSite","name":"B"}]}'
        entries, _ = extract.jsonld_entries([script], "")
        self.assertEqual([e["type"] for e in entries], ["Organization", "WebSite"])

    def test_invalid_json_and_missing_type(self):
        entries, _ = extract.jsonld_entries(['{"@type": "Product",', '{"name": "x"}'], "")
        self.assertFalse(entries[0]["valid"])
        self.assertTrue(entries[0]["errors"][0].startswith("JSON parse error"))
        self.assertEqual(entries[1]["errors"], ["missing @type"])

    def test_values_cap_keeps_shortest_values_and_reports_it(self):
        node = {"@type": "Thing", "name": "short"}
        node.update({"desc%d" % i: "x" * 300 for i in range(20)})
        entries, truncation = extract.jsonld_entries([__import__("json").dumps(node)], "")
        self.assertEqual(entries[0]["values"]["name"], "short")
        size = sum(len(k) + len(v) for k, v in entries[0]["values"].items())
        self.assertLessEqual(size, extract.JSONLD_VALUES_CAP_BYTES)
        self.assertEqual(truncation[0], "jsonld[].values")

    def test_price_contradiction_is_narrow(self):
        script = '{"@type":"Product","offers":{"price":"12999.00"}}'
        self.assertFalse(extract.jsonld_entries([script], "Now ₹12,999 only")[0][0]["contradicts_visible_text"])
        self.assertTrue(extract.jsonld_entries([script], "Now ₹10,999 only")[0][0]["contradicts_visible_text"])
        self.assertFalse(extract.jsonld_entries([script], "No prices shown here")[0][0]["contradicts_visible_text"])


class TestUrls(unittest.TestCase):
    def test_normalise(self):
        self.assertEqual(urls.normalise("HTTPS://WWW.Example.com:443/Path?utm_source=x&a=1#frag"),
                         "https://www.example.com/Path?a=1")
        self.assertEqual(urls.normalise("/x", "http://example.com:8080/a/b"), "http://example.com:8080/x")
        self.assertEqual(urls.normalise("https://example.com"), "https://example.com/")
        self.assertIsNone(urls.normalise("javascript:alert(1)"))
        self.assertIsNone(urls.normalise("mailto:a@example.com"))

    def test_registrable_domain(self):
        self.assertEqual(urls.registrable_domain("www.shop.example.co.uk"), "example.co.uk")
        self.assertEqual(urls.registrable_domain("store.brand.co.in"), "brand.co.in")
        self.assertEqual(urls.registrable_domain("www.example.com"), "example.com")
        self.assertEqual(urls.registrable_domain("localhost"), "localhost")
        self.assertEqual(urls.registrable_domain("127.0.0.1"), "127.0.0.1")

    def test_twin_and_path(self):
        self.assertEqual(urls.twin_netloc("www.example.com"), "example.com")
        self.assertEqual(urls.twin_netloc("example.com"), "www.example.com")
        self.assertIsNone(urls.twin_netloc("127.0.0.1:8000"))
        self.assertEqual(urls.path_and_query("https://x.example/a?b=1"), "/a?b=1")


if __name__ == "__main__":
    unittest.main()
