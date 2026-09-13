"""access-and-indexability: each rule's true positive, the false positives its
controls exist to stop, and its not-assessed path.

Every case builds a bundle from the minimal fixture and changes only what the
case is about, so a failure names exactly which control regressed. Every finding
any case produces is also derived and validated against the finding schema, so
a rule cannot emit something the report would refuse.
"""

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
_spec = importlib.util.spec_from_file_location("access_diagnose", ROOT / "skills" / "access-and-indexability" / "scripts" / "diagnose.py")
diagnose = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(diagnose)

BASE = json.loads((ROOT / "tests" / "fixtures" / "evidence" / "minimal.evidence.json").read_text(encoding="utf-8"))
SCHEMAS = {name: json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
           for name in ("evidence.schema.json", "finding.schema.json", "report.schema.json")}
ORIGIN = "http://localhost:8000"
ALL_AGENTS = ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "OAI-SearchBot", "CCBot",
              "Googlebot", "Claude-SearchBot", "Bingbot")


def page(path, page_type="article", status=200, meta=("index", "follow"), xrt=None, canonical="self"):
    template = BASE["pages"][1]
    p = copy.deepcopy(template)
    url = ORIGIN + path
    p.update({"url": url, "final_url": url, "status": status, "page_type": page_type,
              "meta_robots": list(meta), "canonical": url if canonical == "self" else canonical,
              "canonical_self": canonical == "self"})
    p["headers"]["x_robots_tag"] = xrt
    return p


def bundle(pages=None, groups=None, verdicts=None, parse_reason="ok", robots_status=200,
           sitemaps_declared=None, sitemap_records=None, ua_probe=None, domain="localhost"):
    e = copy.deepcopy(BASE)
    if pages is not None:
        e["pages"] = pages
    r = e["robots"]
    r["parse_reason"] = parse_reason
    r["parse_ok"] = parse_reason == "ok"
    r["status"] = robots_status
    r["fetched"] = True
    if groups is not None:
        r["groups"] = groups
    agents = {a: "allowed" for a in ALL_AGENTS}
    agents.update(verdicts or {})
    r["ai_agents"] = agents
    if sitemaps_declared is not None:
        r["sitemaps"] = sitemaps_declared
    if sitemap_records is not None:
        e["sitemaps"] = sitemap_records
    if ua_probe is not None:
        e["ua_probe"] = ua_probe
    e["site"]["registrable_domain"] = domain
    return e


def group(agent, disallow=(), allow=()):
    return {"user_agent": agent, "allow": list(allow), "disallow": list(disallow), "crawl_delay": None}


def home():
    return page("/", "home")


class RuleCase(unittest.TestCase):
    def run_rules(self, evidence):
        self.assertFalse(Validator(SCHEMAS["evidence.schema.json"], SCHEMAS).errors(evidence),
                         "the test bundle itself must be schema-valid")
        result = diagnose.diagnose(evidence)
        for f in result["findings"]:
            derived = sev_mod.derive(copy.deepcopy(f))
            problems = Validator(SCHEMAS["finding.schema.json"], SCHEMAS).errors(derived)
            self.assertFalse(problems, "%s emitted an invalid finding: %s" % (f["rule_id"], problems))
            if f["status"] == "found":
                self.assertTrue(f["false_positive_controls_applied"] and f["exceptions_checked"])
        return result

    def outcome(self, result, rule_id):
        fired = [f for f in result["findings"] if f["rule_id"] == rule_id]
        if fired:
            return "fired", fired
        if any(n["rule_id"] == rule_id for n in result["not_assessed"]):
            return "not_assessed", None
        if any(c["rule_id"] == rule_id for c in result["checks_passed"]):
            return "passed", None
        self.fail("%s produced no outcome at all" % rule_id)

    def assertOutcome(self, evidence, rule_id, expected):
        got, fired = self.outcome(self.run_rules(evidence), rule_id)
        self.assertEqual(got, expected)
        return fired


class TestEveryRuleHasExactlyOneOutcome(RuleCase):
    def test_minimal_bundle(self):
        result = self.run_rules(bundle())
        ids = ([f["rule_id"] for f in result["findings"]] + [n["rule_id"] for n in result["not_assessed"]]
               + [c["rule_id"] for c in result["checks_passed"]])
        self.assertEqual(sorted(set(ids)), ["ACC-%03d" % i for i in range(1, 10)])

    def test_deterministic(self):
        e = bundle(pages=[home(), page("/a", meta=("noindex",)), page("/b", meta=("noindex",))])
        self.assertEqual(json.dumps(diagnose.diagnose(e), sort_keys=True),
                         json.dumps(diagnose.diagnose(copy.deepcopy(e)), sort_keys=True))


class TestACC001(RuleCase):
    def test_star_group_sweeps_up_search_crawlers(self):
        e = bundle(groups=[group("*", ["/"]), group("Googlebot", allow=["/"])],
                   verdicts={a: "disallowed" for a in ALL_AGENTS if a != "Googlebot"})
        fired = self.assertOutcome(e, "ACC-001", "fired")[0]
        self.assertIn("OAI-SearchBot", fired["evidence"])
        self.assertNotIn("Googlebot,", fired["evidence"].split("through")[0])
        self.assertEqual(fired["impact"]["breadth"], "site")

    def test_named_exclusion_is_not_collateral(self):
        e = bundle(groups=[group("*", allow=["/"]), group("PerplexityBot", ["/"])],
                   verdicts={"PerplexityBot": "disallowed"})
        self.assertOutcome(e, "ACC-001", "passed")

    def test_outage_is_never_read_as_policy(self):
        e = bundle(groups=[], parse_reason="server_error", robots_status=503,
                   verdicts={a: "disallowed" for a in ALL_AGENTS})
        self.assertOutcome(e, "ACC-001", "not_assessed")

    def test_absent_robots_passes(self):
        e = bundle(groups=[], parse_reason="absent_4xx", robots_status=404,
                   verdicts={a: "unspecified" for a in ALL_AGENTS})
        self.assertOutcome(e, "ACC-001", "passed")

    def test_training_only_star_block_does_not_fire(self):
        e = bundle(groups=[group("*", ["/"])] + [group(a, allow=["/"]) for a in diagnose.RETRIEVAL_AGENTS],
                   verdicts={a: "disallowed" for a in diagnose.TRAINING_AGENTS})
        self.assertOutcome(e, "ACC-001", "passed")


class TestACC002(RuleCase):
    def test_server_error_is_a_low_confidence_risk(self):
        e = bundle(groups=[], parse_reason="server_error", robots_status=503,
                   verdicts={a: "disallowed" for a in ALL_AGENTS})
        fired = self.assertOutcome(e, "ACC-002", "fired")[0]
        self.assertEqual((fired["status"], fired["confidence"]), ("risk", "low"))

    def test_no_response_is_not_assessed(self):
        e = bundle(groups=[], parse_reason="unreachable", robots_status=None,
                   verdicts={a: "disallowed" for a in ALL_AGENTS})
        self.assertOutcome(e, "ACC-002", "not_assessed")

    def test_finding_is_citable_with_no_pages(self):
        e = bundle(pages=[], groups=[], parse_reason="rate_limited", robots_status=429,
                   verdicts={a: "disallowed" for a in ALL_AGENTS})
        fired = self.assertOutcome(e, "ACC-002", "fired")[0]
        self.assertEqual(fired["evidence_refs"][0]["retrieved_at"], BASE["run_context"]["started_at"])


class TestACC003(RuleCase):
    def test_article_template_noindex_fires(self):
        pages = [home()] + [page("/a%d" % i, meta=("noindex", "follow")) for i in range(3)] + [page("/a9")]
        fired = self.assertOutcome(bundle(pages=pages), "ACC-003", "fired")[0]
        self.assertEqual((fired["scope"]["pages_affected"], fired["scope"]["pages_examined"]), (3, 4))
        self.assertEqual(fired["confidence"], "high")

    def test_single_editorial_noindex_does_not_fire(self):
        pages = [home(), page("/a1", meta=("noindex",))] + [page("/a%d" % i) for i in range(2, 5)]
        self.assertOutcome(bundle(pages=pages), "ACC-003", "passed")

    def test_noindex_home_fires(self):
        self.assertOutcome(bundle(pages=[page("/", "home", meta=("noindex",))]), "ACC-003", "fired")

    def test_category_and_other_never_count(self):
        pages = [home()] + [page("/t%d" % i, "category", meta=("noindex",)) for i in range(3)] \
                + [page("/o%d" % i, "other", meta=("noindex",)) for i in range(3)]
        self.assertOutcome(bundle(pages=pages), "ACC-003", "passed")

    def test_header_scoped_to_another_crawler_is_ignored(self):
        pages = [home()] + [page("/a%d" % i, xrt="bingbot: noindex") for i in range(3)]
        self.assertOutcome(bundle(pages=pages), "ACC-003", "passed")

    def test_header_scoped_to_googlebot_counts(self):
        pages = [home()] + [page("/a%d" % i, xrt="googlebot: noindex, nofollow") for i in range(3)]
        self.assertOutcome(bundle(pages=pages), "ACC-003", "fired")

    def test_harmless_tokens_never_match(self):
        pages = [page("/", "home", meta=("noodp", "max-image-preview:large", "noimageindex"))]
        self.assertOutcome(bundle(pages=pages), "ACC-003", "passed")

    def test_duplicate_declaring_another_canonical_is_excluded(self):
        pages = [home()] + [page("/a%d" % i, meta=("noindex",), canonical=ORIGIN + "/orig%d" % i) for i in range(3)]
        self.assertOutcome(bundle(pages=pages), "ACC-003", "passed")

    def test_refused_pages_are_not_thin_pages(self):
        pages = [home()] + [page("/a%d" % i, status=403, meta=("noindex",)) for i in range(3)]
        self.assertOutcome(bundle(pages=pages), "ACC-003", "passed")

    def test_no_primary_page_is_not_assessed(self):
        self.assertOutcome(bundle(pages=[page("/x", "other")]), "ACC-003", "not_assessed")


class TestACC004(RuleCase):
    def test_nosnippet_template_fires_at_most_medium(self):
        pages = [home()] + [page("/a%d" % i, meta=("nosnippet",)) for i in range(3)]
        fired = self.assertOutcome(bundle(pages=pages), "ACC-004", "fired")[0]
        self.assertEqual(fired["confidence"], "medium")

    def test_max_snippet_zero_matches_and_positive_does_not(self):
        pages = [home()] + [page("/a%d" % i, xrt="max-snippet:0") for i in range(2)]
        self.assertEqual(self.assertOutcome(bundle(pages=pages), "ACC-004", "fired")[0]["confidence"], "low")
        pages = [home()] + [page("/a%d" % i, meta=("max-snippet:160",)) for i in range(3)]
        self.assertOutcome(bundle(pages=pages), "ACC-004", "passed")

    def test_snippet_header_scoped_to_another_crawler_is_ignored(self):
        pages = [home()] + [page("/a%d" % i, xrt="bingbot: nosnippet") for i in range(3)]
        self.assertOutcome(bundle(pages=pages), "ACC-004", "passed")

    def test_noindexed_pages_left_to_acc_003(self):
        pages = [home()] + [page("/a%d" % i, meta=("noindex", "nosnippet")) for i in range(3)]
        result = self.run_rules(bundle(pages=pages))
        self.assertEqual(self.outcome(result, "ACC-003")[0], "fired")
        self.assertEqual(self.outcome(result, "ACC-004")[0], "passed")


class TestACC005(RuleCase):
    def shell_pages(self, target, n=4):
        return [page("/", "home", canonical=target)] + \
            [page("/p%d" % i, "other", canonical=target) for i in range(n)]

    def test_template_canonical_to_home_fires(self):
        e = bundle(pages=self.shell_pages("http://localhost:8000/"))
        fired = self.assertOutcome(e, "ACC-005", "fired")[0]
        self.assertEqual(fired["confidence"], "high")
        self.assertEqual(fired["impact"]["content_importance"], "secondary")

    def test_apex_host_of_same_domain_counts(self):
        pages = [page("/", "home")] + [page("/p%d" % i, "about", canonical="http://example.com/") for i in range(2)]
        for p in pages:
            p["url"] = p["final_url"] = p["url"].replace("localhost:8000", "www.example.com")
        pages[0]["canonical"] = pages[0]["url"]
        self.assertOutcome(bundle(pages=pages, domain="example.com"), "ACC-005", "fired")

    def test_single_consolidated_page_does_not_fire(self):
        pages = [home(), page("/old", canonical=ORIGIN + "/"), page("/a"), page("/b")]
        self.assertOutcome(bundle(pages=pages), "ACC-005", "passed")

    def test_cross_domain_syndication_is_out_of_scope(self):
        e = bundle(pages=[home()] + [page("/p%d" % i, canonical="https://publisher.example/") for i in range(3)])
        self.assertOutcome(e, "ACC-005", "passed")

    def test_root_aliases_are_the_home_page(self):
        pages = [home(), page("/index.html", "home", canonical=ORIGIN + "/"),
                 page("/home", "home", canonical=ORIGIN + "/")]
        self.assertOutcome(bundle(pages=pages), "ACC-005", "not_assessed")


class TestACC006(RuleCase):
    URLS = (ORIGIN + "/", ORIGIN + "/a")

    def probe(self, statuses):
        return [{"url": u, "user_agent": agent, "status": statuses.get((agent, u), 200), "text_len": 10,
                 "text_hash": "sha256:" + "0" * 64}
                for u in self.URLS for agent in ("browser-ua", "GPTBot", "OAI-SearchBot", "Googlebot")]

    def test_consistent_refusal_is_a_low_confidence_risk(self):
        e = bundle(pages=[home(), page("/a")],
                   ua_probe=self.probe({("GPTBot", u): 403 for u in self.URLS}))
        fired = self.assertOutcome(e, "ACC-006", "fired")[0]
        self.assertEqual((fired["status"], fired["confidence"], fired["impact"]["breadth"]), ("risk", "low", "site"))

    def test_refusal_on_one_url_only_does_not_fire(self):
        e = bundle(ua_probe=self.probe({("GPTBot", self.URLS[1]): 403}))
        self.assertOutcome(e, "ACC-006", "passed")

    def test_rate_limit_and_googlebot_are_excluded(self):
        statuses = {("OAI-SearchBot", u): 429 for u in self.URLS}
        statuses.update({("Googlebot", u): 403 for u in self.URLS})
        self.assertOutcome(bundle(ua_probe=self.probe(statuses)), "ACC-006", "passed")

    def test_googlebot_refused_too_reads_as_verification_not_a_block(self):
        statuses = {(a, u): 403 for u in self.URLS for a in ("GPTBot", "OAI-SearchBot", "Googlebot")}
        e = bundle(pages=[home(), page("/a")], ua_probe=self.probe(statuses))
        self.assertOutcome(e, "ACC-006", "not_assessed")
        partial = dict(statuses)
        partial[("Googlebot", self.URLS[1])] = 200
        self.assertOutcome(bundle(pages=[home(), page("/a")], ua_probe=self.probe(partial)), "ACC-006", "fired")

    def test_browser_refused_too_is_not_assessed(self):
        statuses = {(a, u): 403 for u in self.URLS for a in ("browser-ua", "GPTBot", "OAI-SearchBot", "Googlebot")}
        self.assertOutcome(bundle(ua_probe=self.probe(statuses)), "ACC-006", "not_assessed")


class TestACC007(RuleCase):
    def test_share_of_dead_urls_fires(self):
        pages = [home()] + [page("/a%d" % i) for i in range(7)] + [page("/d1", status=404), page("/d2", status=410)]
        fired = self.assertOutcome(bundle(pages=pages), "ACC-007", "fired")[0]
        self.assertEqual((fired["confidence"], fired["impact"]["breadth"]), ("high", "page"))

    def test_client_refusals_are_not_dead_urls(self):
        pages = [home()] + [page("/a%d" % i) for i in range(3)] + [page("/r%d" % i, status=403) for i in range(4)]
        self.assertOutcome(bundle(pages=pages), "ACC-007", "passed")

    def test_one_broken_link_is_background_rot(self):
        pages = [home()] + [page("/a%d" % i) for i in range(3)] + [page("/d", status=404)]
        self.assertOutcome(bundle(pages=pages), "ACC-007", "passed")

    def test_server_errors_lower_confidence(self):
        pages = [home()] + [page("/a%d" % i) for i in range(2)] + [page("/d", status=404), page("/e", status=503)]
        self.assertEqual(self.assertOutcome(bundle(pages=pages), "ACC-007", "fired")[0]["confidence"], "medium")

    def test_small_sample_is_not_assessed(self):
        self.assertOutcome(bundle(pages=[home(), page("/d", status=404), page("/e", status=404)]),
                           "ACC-007", "not_assessed")


class TestACC008(RuleCase):
    def test_named_search_crawler_is_proactive_and_capped(self):
        e = bundle(groups=[group("*", allow=["/"]), group("PerplexityBot", ["/"]), group("GPTBot", ["/"])],
                   verdicts={"PerplexityBot": "disallowed", "GPTBot": "disallowed"})
        fired = self.assertOutcome(e, "ACC-008", "fired")[0]
        self.assertEqual(fired["status"], "proactive")
        self.assertIn("Perplexity", fired["evidence"])
        self.assertIn("GPTBot", fired["evidence"])
        derived = sev_mod.derive(copy.deepcopy(fired))
        self.assertEqual((derived["severity"], derived["suggested_action"]["priority"]), ("medium", "P2"))

    def test_named_training_opt_out_passes_and_is_recorded(self):
        e = bundle(groups=[group("*", allow=["/"]), group("GPTBot", ["/"])], verdicts={"GPTBot": "disallowed"})
        result = self.run_rules(e)
        self.assertEqual(self.outcome(result, "ACC-008")[0], "passed")
        summary = [c["summary"] for c in result["checks_passed"] if c["rule_id"] == "ACC-008"][0]
        self.assertIn("GPTBot", summary)

    def test_claude_searchbot_is_a_retrieval_crawler(self):
        e = bundle(groups=[group("*", allow=["/"]), group("Claude-SearchBot", ["/"])],
                   verdicts={"Claude-SearchBot": "disallowed"})
        self.assertOutcome(e, "ACC-008", "fired")


class TestACC009(RuleCase):
    SM = ORIGIN + "/sitemap.xml"

    def record(self, url, status, parse_ok):
        return {"url": url, "status": status, "url_count": 3 if parse_ok else None,
                "lastmod_present_ratio": None, "parse_ok": parse_ok}

    def test_declared_sitemap_serving_a_shell_fires(self):
        e = bundle(sitemaps_declared=[self.SM], sitemap_records=[self.record(self.SM, 200, False)])
        fired = self.assertOutcome(e, "ACC-009", "fired")[0]
        self.assertEqual((fired["confidence"], fired["impact"]["breadth"]), ("high", "site"))

    def test_fallback_probe_on_undeclared_sitemap_never_fires(self):
        e = bundle(sitemaps_declared=[], sitemap_records=[self.record(self.SM, 404, False)])
        self.assertOutcome(e, "ACC-009", "not_assessed")

    def test_no_response_and_refusals_are_not_assessed(self):
        e = bundle(sitemaps_declared=[self.SM], sitemap_records=[self.record(self.SM, None, False)])
        self.assertOutcome(e, "ACC-009", "not_assessed")
        e = bundle(sitemaps_declared=[self.SM], sitemap_records=[self.record(self.SM, 403, False)])
        self.assertOutcome(e, "ACC-009", "not_assessed")

    def test_index_children_are_not_counted(self):
        child = ORIGIN + "/sitemap-1.xml"
        e = bundle(sitemaps_declared=[self.SM],
                   sitemap_records=[self.record(self.SM, 200, True), self.record(child, 500, False)])
        self.assertOutcome(e, "ACC-009", "passed")

    def test_partial_failure_is_section_and_5xx_is_medium(self):
        other = ORIGIN + "/news.xml"
        e = bundle(sitemaps_declared=[self.SM, other],
                   sitemap_records=[self.record(self.SM, 200, True), self.record(other, 502, False)])
        fired = self.assertOutcome(e, "ACC-009", "fired")[0]
        self.assertEqual((fired["confidence"], fired["impact"]["breadth"]), ("medium", "section"))


if __name__ == "__main__":
    unittest.main()
