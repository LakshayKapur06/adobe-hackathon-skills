"""render-and-extraction: each rule's true positive, the false positives its
controls exist to stop, and its not-assessed path.

Cases are built from the minimal fixture bundle. RND-003 reads the extracted-text
sidecars, so those cases write real sidecar files into a temporary working
directory. Every emitted finding is derived and validated against the finding
schema.
"""

import copy
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "audit-orchestrator" / "scripts"))

import severity as sev_mod  # noqa: E402
from jsonschema_lite import Validator  # noqa: E402

# Loaded by path under a unique name: every diagnostic's script is called
# diagnose.py, and one test process imports several of them.
_spec = importlib.util.spec_from_file_location("render_diagnose", ROOT / "skills" / "render-and-extraction" / "scripts" / "diagnose.py")
diagnose = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(diagnose)

BASE = json.loads((ROOT / "tests" / "fixtures" / "evidence" / "minimal.evidence.json").read_text(encoding="utf-8"))
SCHEMAS = {name: json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
           for name in ("evidence.schema.json", "finding.schema.json", "report.schema.json")}
ORIGIN = "http://localhost:8000"
EMPTY_HASH = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class Workdir:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        (self.root / "evidence" / "pages").mkdir(parents=True)
        self.count = 0

    def sidecar(self, text):
        self.count += 1
        rel = "evidence/pages/%064x.txt" % self.count
        (self.root / rel).write_text(text, encoding="utf-8")
        return rel


def page(path, page_type="article", raw_len=3000, rendered_len=3050, status=200, content_type="text/html",
         rendered=True, confidence=0.9, raw_text_path=None, rendered_text_path=None, jsonld_fields=(),
         raw_hash="sha256:" + "1" * 64, hidden_len=0):
    p = copy.deepcopy(BASE["pages"][1])
    url = ORIGIN + path
    p.update({"url": url, "final_url": url, "status": status, "page_type": page_type,
              "page_type_confidence": confidence, "content_type": content_type})
    p["raw"]["text_len"] = raw_len
    p["raw"]["hidden_text_len"] = hidden_len
    p["raw"]["text_hash"] = raw_hash
    if raw_text_path:
        p["raw"]["text_path"] = raw_text_path
    if rendered:
        delta = round(max(0.0, (rendered_len - raw_len) / rendered_len), 3) if rendered_len else None
        p["rendered"] = {"available": True, "text_len": rendered_len, "text_hash": "sha256:" + "2" * 64,
                         "text_path": rendered_text_path or p["raw"]["text_path"], "headings": [],
                         "delta_ratio": delta}
    else:
        p["rendered"] = {"available": False, "text_len": None, "text_hash": None, "text_path": None,
                         "headings": [], "delta_ratio": None}
    p["jsonld"] = [{"type": "Product", "valid": True, "errors": [], "fields_present": list(jsonld_fields),
                    "values": {}, "contradicts_visible_text": False}] if jsonld_fields else []
    return p


def bundle(pages, js_render=True, soft_404=None, collapsed=0):
    e = copy.deepcopy(BASE)
    e["pages"] = pages
    e["run_context"]["capabilities"]["js_render"] = js_render
    if soft_404 is not None:
        e["discovery"]["soft_404"] = soft_404
    e["discovery"]["collapsed_duplicate_text"] = collapsed
    return e


class RuleCase(unittest.TestCase):
    def run_rules(self, evidence, workdir=None):
        self.assertFalse(Validator(SCHEMAS["evidence.schema.json"], SCHEMAS).errors(evidence))
        result = diagnose.diagnose(evidence, str(workdir or ROOT / "tests" / "fixtures"))
        for f in result["findings"]:
            derived = sev_mod.derive(copy.deepcopy(f))
            self.assertFalse(Validator(SCHEMAS["finding.schema.json"], SCHEMAS).errors(derived))
            self.assertTrue(f["false_positive_controls_applied"] and f["exceptions_checked"])
        ids = sorted({x["rule_id"] for k in ("findings", "not_assessed", "checks_passed") for x in result[k]})
        self.assertEqual(ids, ["RND-001", "RND-002", "RND-003"], "every rule must produce an outcome")
        return result

    def outcome(self, result, rule_id):
        fired = [f for f in result["findings"] if f["rule_id"] == rule_id]
        if fired:
            return "fired", fired
        if any(n["rule_id"] == rule_id for n in result["not_assessed"]):
            return "not_assessed", None
        return "passed", None

    def assertOutcome(self, evidence, rule_id, expected, workdir=None):
        got, fired = self.outcome(self.run_rules(evidence, workdir), rule_id)
        self.assertEqual(got, expected)
        return fired


class TestRND001(RuleCase):
    def test_client_rendered_site_fires_site_wide_at_high_confidence(self):
        pages = [page("/", "home", 0, 269)] + [page("/p%d" % i, "other", 0, 1500) for i in range(4)]
        fired = self.assertOutcome(bundle(pages), "RND-001", "fired")[0]
        self.assertEqual((fired["impact"]["breadth"], fired["confidence"], fired["impact"]["content_importance"]),
                         ("site", "high", "primary"))
        self.assertEqual(sev_mod.derive(copy.deepcopy(fired))["severity"], "critical")

    def test_one_client_rendered_listing_template_is_not_the_whole_site(self):
        # A stratified sample can draw half its rendered pages from one listing
        # template. JavaScript-built listings alone must not read as site-wide.
        pages = [page("/", "home")] + [page("/a%d" % i) for i in range(2)] + \
                [page("/c%d" % i, "category", 200, 3000) for i in range(3)]
        result = self.run_rules(bundle(pages))
        self.assertFalse([f for f in result["findings"] if f["rule_id"] == "RND-001"
                          and f["impact"]["breadth"] == "site"])

    def test_hydrated_widgets_do_not_fire(self):
        pages = [page("/", "home", 18516, 18522)] + [page("/p%d" % i, "product", 2400, 3200) for i in range(6)]
        self.assertOutcome(bundle(pages), "RND-001", "passed")

    def test_single_js_page_on_a_server_rendered_site_does_not_fire(self):
        pages = [page("/", "home")] + [page("/a%d" % i) for i in range(8)] + [page("/subscribe", "doc", 0, 3152)]
        self.assertOutcome(bundle(pages), "RND-001", "passed")

    def test_product_template_fires_as_a_section(self):
        pages = [page("/", "home")] + [page("/a%d" % i) for i in range(6)] + \
                [page("/x%d" % i, "product", 300, 4000) for i in range(3)]
        fired = self.assertOutcome(bundle(pages), "RND-001", "fired")[0]
        self.assertEqual((fired["impact"]["breadth"], fired["scope"]["page_types"], fired["confidence"]),
                         ("section", ["product"], "medium"))
        self.assertEqual(fired["title"], "Page content exists only after JavaScript runs (product)")

    def test_a_shared_path_names_the_application_not_the_guessed_type(self):
        pages = [page("/", "home")] + [page("/a%d" % i) for i in range(6)] + \
                [page("/cli/%s" % name, "doc", 300, 4000) for name in ("docs", "help")] + [page("/api", "doc")]
        fired = self.assertOutcome(bundle(pages), "RND-001", "fired")[0]
        self.assertEqual(fired["title"], "Page content exists only after JavaScript runs (pages under /cli/)")
        self.assertIn("on doc pages under /cli/", fired["evidence"])
        self.assertIn("/cli/", fired["suggested_action"]["where"])

    def test_text_hidden_in_the_server_response_is_not_javascript_only(self):
        # Server sends the whole text in a display:none container and script
        # reveals it: visible server text is zero, but a fetcher that ignores CSS
        # reads everything, so "absent from the server response" would be false.
        pages = [page("/", "home", 0, 3000, hidden_len=2900)] + [
            page("/p%d" % i, "other", 0, 1500, hidden_len=1450) for i in range(4)]
        self.assertOutcome(bundle(pages), "RND-001", "passed")

    def test_tiny_gain_is_not_substance(self):
        pages = [page("/", "home", 20, 150)] + [page("/p%d" % i, "other", 10, 180) for i in range(3)]
        self.assertOutcome(bundle(pages), "RND-001", "passed")

    def test_refused_and_non_html_pages_never_compare(self):
        pages = [page("/", "home"), page("/a", "article", 0, 3000, status=403),
                 page("/agents.md", "other", 0, 900, content_type="text/markdown")]
        self.assertOutcome(bundle(pages), "RND-001", "not_assessed")

    def test_no_browser_is_not_assessed_with_a_hint(self):
        result = self.run_rules(bundle([page("/", "home", rendered=False)], js_render=False))
        entry = [n for n in result["not_assessed"] if n["rule_id"] == "RND-001"][0]
        self.assertIn("Chromium", entry["enable_hint"])


class TestRND002(RuleCase):
    SOFT = {"detected": True, "baseline_text_hash": EMPTY_HASH, "probe_paths": ["/a", "/b"]}

    def test_single_shell_without_browser_fires_high(self):
        e = bundle([page("/", "home", 0, rendered=False, raw_hash=EMPTY_HASH)], js_render=False,
                   soft_404=self.SOFT, collapsed=4)
        fired = self.assertOutcome(e, "RND-002", "fired")[0]
        self.assertEqual(fired["confidence"], "high")
        self.assertIn("4 further URLs", fired["evidence"])

    def test_empty_but_not_a_shared_shell_is_medium(self):
        e = bundle([page("/", "home", 40, rendered=False)], js_render=False)
        self.assertEqual(self.assertOutcome(e, "RND-002", "fired")[0]["confidence"], "medium")

    def test_hidden_server_text_is_not_an_empty_response(self):
        e = bundle([page("/", "home", 0, rendered=False, hidden_len=2400)], js_render=False)
        self.assertOutcome(e, "RND-002", "passed")

    def test_any_page_with_real_text_passes(self):
        e = bundle([page("/", "home", 0, rendered=False), page("/a", "article", 531, rendered=False)], js_render=False)
        self.assertOutcome(e, "RND-002", "passed")

    def test_refused_home_page_is_not_assessed(self):
        e = bundle([page("/", "home", 0, rendered=False, status=403)], js_render=False)
        self.assertOutcome(e, "RND-002", "not_assessed")

    def test_rendered_comparison_supersedes_it(self):
        pages = [page("/", "home", 0, 269)] + [page("/p%d" % i, "other", 0, 1500) for i in range(4)]
        result = self.run_rules(bundle(pages))
        self.assertEqual(self.outcome(result, "RND-001")[0], "fired")
        self.assertEqual(self.outcome(result, "RND-002")[0], "not_assessed")


class TestRND003(RuleCase):
    def work(self):
        work = Workdir()
        self.addCleanup(work.tmp.cleanup)
        return work

    def products(self, work, n, raw_text, rendered_text, fields=()):
        return [page("/", "home")] + [
            page("/products/p%d" % i, "product", 2400, 2600, raw_text_path=work.sidecar(raw_text),
                 rendered_text_path=work.sidecar(rendered_text), jsonld_fields=fields)
            for i in range(n)]

    def test_hydrated_price_fires(self):
        work = self.work()
        e = bundle(self.products(work, 8, "Velocity X9 running shoe. Add to cart.",
                                 "Velocity X9 running shoe. ₹12,999.00 Add to cart."))
        fired = self.assertOutcome(e, "RND-003", "fired", work.root)[0]
        self.assertEqual((fired["confidence"], fired["scope"]["pages_affected"]), ("high", 8))
        self.assertIn("₹12,999.00", fired["evidence"])

    def test_server_json_ld_price_excludes_the_page(self):
        work = self.work()
        e = bundle(self.products(work, 6, "Shoe.", "Shoe. $120", fields=("offers.price", "offers.priceCurrency")))
        self.assertOutcome(e, "RND-003", "passed", work.root)

    def test_server_rendered_price_passes(self):
        work = self.work()
        e = bundle(self.products(work, 6, "Shoe. Rs. 1,499", "Shoe. Rs. 1,499"))
        self.assertOutcome(e, "RND-003", "passed", work.root)

    def test_quote_on_request_never_matches(self):
        work = self.work()
        e = bundle(self.products(work, 6, "Industrial pump. Request a quote.", "Industrial pump. Request a quote."))
        self.assertOutcome(e, "RND-003", "passed", work.root)

    def test_fewer_than_five_products_is_not_assessed(self):
        work = self.work()
        e = bundle(self.products(work, 4, "Shoe.", "Shoe. €80"))
        self.assertOutcome(e, "RND-003", "not_assessed", work.root)

    def test_minority_of_products_does_not_fire(self):
        work = self.work()
        pages = self.products(work, 3, "Shoe.", "Shoe. $99") + [
            page("/products/q%d" % i, "product", 2400, 2600, raw_text_path=work.sidecar("Shoe $50"),
                 rendered_text_path=work.sidecar("Shoe $50")) for i in range(4)]
        self.assertOutcome(bundle(pages), "RND-003", "passed", work.root)


if __name__ == "__main__":
    unittest.main()
