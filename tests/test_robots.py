"""robots.txt semantics. Every case here is a confidently wrong critical finding
if it regresses, so each one is pinned individually."""

import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "site-evidence-collector" / "scripts"))

import robots  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "robots"


def load(name):
    return robots.Robots(*robots.parse((FIXTURES / name).read_text(encoding="utf-8")))


def from_text(text):
    return robots.Robots(*robots.parse(text))


class TestGroupSelection(unittest.TestCase):
    def test_named_group_wins_over_star(self):
        r = from_text("User-agent: *\nDisallow: /\n\nUser-agent: GPTBot\nAllow: /\n")
        self.assertTrue(r.allowed("/page", ("GPTBot",)))
        self.assertFalse(r.allowed("/page", ("ClaudeBot",)))

    def test_star_covers_every_unnamed_crawler(self):
        r = from_text("User-agent: *\nDisallow: /private\n")
        for agent in robots.AI_AGENTS:
            with self.subTest(agent=agent):
                self.assertEqual(r.verdict(agent), "allowed")

    def test_unspecified_only_when_no_group_applies(self):
        r = from_text("User-agent: SomeOtherBot\nDisallow: /\n")
        self.assertEqual(r.verdict("GPTBot"), "unspecified")
        self.assertEqual(r.verdict("SomeOtherBot"), "disallowed")

    def test_never_unspecified_when_a_star_group_exists(self):
        for name in ("shopify-storefront.txt", "media-site.txt"):
            r = load(name)
            for agent in robots.AI_AGENTS:
                with self.subTest(file=name, agent=agent):
                    self.assertNotEqual(r.verdict(agent), "unspecified")

    def test_matching_groups_for_one_token_are_merged(self):
        r = from_text("User-agent: GPTBot\nDisallow: /a\n\nUser-agent: GPTBot\nDisallow: /b\n")
        self.assertFalse(r.allowed("/a", ("GPTBot",)))
        self.assertFalse(r.allowed("/b", ("GPTBot",)))
        self.assertTrue(r.allowed("/c", ("GPTBot",)))

    def test_stacked_user_agent_lines_share_one_group(self):
        r = from_text("User-agent: GPTBot\nUser-agent: ClaudeBot\nDisallow: /\n")
        self.assertEqual(r.verdict("GPTBot"), "disallowed")
        self.assertEqual(r.verdict("ClaudeBot"), "disallowed")
        self.assertEqual(r.verdict("CCBot"), "unspecified")

    def test_product_token_ignores_version_and_case(self):
        r = from_text("user-AGENT: gptbot/1.1\nDISALLOW: /\n")
        self.assertEqual(r.verdict("GPTBot"), "disallowed")

    def test_a_similar_name_is_a_different_product(self):
        # GPTBot's group must not govern OAI-SearchBot, and adsbot-google's
        # group must not govern Googlebot. A substring matcher gets both wrong.
        media = load("media-site.txt")
        self.assertEqual(media.verdict("GPTBot"), "disallowed")
        self.assertEqual(media.verdict("OAI-SearchBot"), "allowed")
        shop = load("shopify-storefront.txt")
        self.assertTrue(shop.allowed("/cart", ("adsbot-google",)))
        self.assertFalse(shop.allowed("/cart", ("Googlebot",)))

    def test_fallback_chain_uses_the_most_specific_named_token(self):
        r = from_text("User-agent: Googlebot\nDisallow: /g\n\nUser-agent: *\nDisallow: /\n")
        # Googlebot-Image has no group of its own and falls back to Googlebot's.
        self.assertTrue(r.allowed("/page", ("Googlebot-Image", "Googlebot")))
        self.assertFalse(r.allowed("/g", ("Googlebot-Image", "Googlebot")))


class TestRuleMatching(unittest.TestCase):
    def test_longest_match_wins(self):
        r = from_text("User-agent: *\nDisallow: /\nAllow: /public\n")
        self.assertTrue(r.allowed("/public/page", ("x",)))
        self.assertFalse(r.allowed("/private", ("x",)))

    def test_equal_length_tie_goes_to_allow(self):
        r = from_text("User-agent: *\nDisallow: /page\nAllow: /page\n")
        self.assertTrue(r.allowed("/page", ("x",)))

    def test_empty_disallow_permits_everything(self):
        r = from_text("User-agent: *\nDisallow:\n")
        self.assertTrue(r.allowed("/anything", ("x",)))
        self.assertEqual(r.verdict("GPTBot"), "allowed")

    def test_end_anchor(self):
        r = load("media-site.txt")
        self.assertFalse(r.allowed("/story.json", ("ClaudeBot",)))
        self.assertTrue(r.allowed("/story.json?v=2", ("ClaudeBot",)))
        self.assertFalse(r.allowed("/world/amp", ("ClaudeBot",)))
        self.assertTrue(r.allowed("/world/amp/page", ("ClaudeBot",)))

    def test_leading_wildcard_without_a_slash(self):
        r = load("media-site.txt")
        self.assertFalse(r.allowed("/files/report.pdf", ("ClaudeBot",)))
        self.assertTrue(r.allowed("/files/report.pdf?download=1", ("ClaudeBot",)))

    def test_brackets_are_literal(self):
        r = load("media-site.txt")
        self.assertFalse(r.allowed("/[slug]/story", ("ClaudeBot",)))
        self.assertTrue(r.allowed("/s/story", ("ClaudeBot",)))
        self.assertTrue(r.allowed("/slug/story", ("ClaudeBot",)))
        self.assertFalse(r.allowed("/a[preview]b", ("ClaudeBot",)))

    def test_allow_carves_out_of_a_broader_disallow(self):
        media = load("media-site.txt")
        self.assertTrue(media.allowed("/api/public/feed", ("ClaudeBot",)))
        self.assertFalse(media.allowed("/api/private", ("ClaudeBot",)))
        shop = load("shopify-storefront.txt")
        self.assertTrue(shop.allowed("/policies/privacy-policy", ("GPTBot",)))
        self.assertFalse(shop.allowed("/policies/refund-policy", ("GPTBot",)))
        self.assertTrue(shop.allowed("/cdn/wpm/public/app.js", ("GPTBot",)))
        self.assertFalse(shop.allowed("/cdn/wpm/private.js", ("GPTBot",)))

    def test_shopify_sort_by_crawl_traps(self):
        shop = load("shopify-storefront.txt")
        self.assertTrue(shop.allowed("/collections/shoes", ("GPTBot",)))
        self.assertFalse(shop.allowed("/collections/shoes?sort_by=price-ascending", ("GPTBot",)))
        self.assertFalse(shop.allowed("/en-in/collections/shoes?sort_by=best-selling", ("GPTBot",)))

    def test_percent_escapes_compare_case_insensitively(self):
        shop = load("shopify-storefront.txt")
        for path in ("/collections/red+blue", "/collections/red%2Bblue", "/collections/red%2bblue"):
            with self.subTest(path=path):
                self.assertFalse(shop.allowed(path, ("GPTBot",)))

    def test_query_string_is_part_of_the_match(self):
        shop = load("shopify-storefront.txt")
        self.assertFalse(shop.allowed("/products/x?oseid=abc", ("GPTBot",)))
        self.assertTrue(shop.allowed("/products/x", ("GPTBot",)))

    def test_robots_txt_itself_is_always_allowed(self):
        r = from_text("User-agent: *\nDisallow: /\n")
        self.assertTrue(r.allowed("/robots.txt", ("x",)))


class TestParsing(unittest.TestCase):
    def test_bom_crlf_comments_and_rules_before_any_group(self):
        text = "﻿Disallow: /orphan\r\n# comment\r\nUser-agent: *  # trailing\r\nDisallow: /x # why\r\n"
        r = from_text(text)
        self.assertTrue(r.allowed("/orphan", ("x",)))     # rule before any group is ignored
        self.assertFalse(r.allowed("/x", ("x",)))

    def test_crawl_delay_and_case_insensitive_keys(self):
        shop = load("shopify-storefront.txt")
        self.assertEqual(shop.crawl_delay(("AhrefsBot",)), 10.0)
        self.assertEqual(shop.crawl_delay(("MJ12bot",)), 10.0)   # "Crawl-Delay"
        self.assertEqual(shop.crawl_delay(("Pinterest",)), 1.0)
        self.assertIsNone(shop.crawl_delay(("agent-readiness-audit",)))
        self.assertEqual(shop.verdict("Nutch"), "disallowed")

    def test_sitemaps_including_a_news_sitemap(self):
        media = load("media-site.txt")
        self.assertEqual(media.sitemaps, [
            "https://media.example/sitemap-index.xml",
            "https://media.example/news-sitemap.xml",
            "https://media.example/video-sitemap.xml",
        ])


class TestStatusSemantics(unittest.TestCase):
    def test_4xx_means_no_restrictions(self):
        for status in (401, 403, 404, 410):
            with self.subTest(status=status):
                mode, parsed, _ = robots.interpret(status, "User-agent: *\nDisallow: /\n", "text/plain")
                self.assertEqual(mode, "absent")
                self.assertIsNone(parsed)

    def test_5xx_timeout_and_429_mean_full_disallow(self):
        for status in (500, 502, 503, 504, 429, None):
            with self.subTest(status=status):
                mode, _, reason = robots.interpret(status, "", None)
                self.assertEqual(mode, "unreachable")
                self.assertIn("full disallow", reason)

    def test_unreachable_records_every_agent_as_disallowed(self):
        block = robots.evidence_block("https://x.example/robots.txt", 503, True, "unreachable", None)
        self.assertEqual(set(block["ai_agents"].values()), {"disallowed"})
        self.assertEqual(block["groups"], [])

    def test_absent_records_every_agent_as_unspecified(self):
        block = robots.evidence_block("https://x.example/robots.txt", 404, True, "absent", None)
        self.assertEqual(set(block["ai_agents"].values()), {"unspecified"})


class TestPlausibility(unittest.TestCase):
    SHELL = "<!doctype html><html><head><title>Shop</title></head><body><div id=app></div></body></html>"

    def test_an_html_shell_is_not_a_robots_file(self):
        mode, parsed, reason = robots.interpret(200, self.SHELL, "text/html; charset=utf-8")
        self.assertEqual(mode, "absent")
        self.assertIsNone(parsed)
        self.assertIn("HTML document", reason)

    def test_html_containing_directive_text_is_still_html(self):
        page = "<html><body><pre>User-agent: *\nDisallow: /</pre></body></html>"
        self.assertFalse(robots.looks_like_robots(page, "text/html")[0])

    def test_prose_with_no_directives_is_not_a_robots_file(self):
        self.assertFalse(robots.looks_like_robots("hello world\nthis is not it\n", "text/plain")[0])

    def test_an_empty_file_is_a_real_empty_robots_txt(self):
        mode, parsed, _ = robots.interpret(200, "", "text/plain")
        self.assertEqual(mode, "parsed")
        self.assertEqual(parsed.verdict("GPTBot"), "unspecified")

    def test_valid_directives_mislabelled_as_html_are_honoured(self):
        mode, parsed, _ = robots.interpret(200, "User-agent: *\nDisallow: /private\n", "text/html")
        self.assertEqual(mode, "parsed")
        self.assertFalse(parsed.allowed("/private", ("x",)))


class TestObservedContentIsData(unittest.TestCase):
    def test_comments_never_reach_the_evidence(self):
        text = (FIXTURES / "shopify-storefront.txt").read_text(encoding="utf-8")
        mode, parsed, _ = robots.interpret(200, text, "text/plain")
        block = json.dumps(robots.evidence_block("https://shop.example/robots.txt", 200, True, mode, parsed))
        # Phrases unique to the comments. ("recommend" alone would match the real
        # rule /recommendations/products, which is data and belongs there.)
        for phrase in ("recommend that your user", "shopping skill", "Dear AI agent",
                       "on their behalf", "Synthetic", "adsbot ignores"):
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, block)

    def test_groups_are_recorded_verbatim_per_user_agent_line(self):
        text = (FIXTURES / "shopify-storefront.txt").read_text(encoding="utf-8")
        mode, parsed, _ = robots.interpret(200, text, "text/plain")
        block = robots.evidence_block("https://shop.example/robots.txt", 200, True, mode, parsed)
        agents = [g["user_agent"] for g in block["groups"]]
        self.assertEqual(agents, ["*", "adsbot-google", "Nutch", "AhrefsBot", "MJ12bot", "Pinterest"])
        star = block["groups"][0]
        self.assertIn("/collections/*sort_by*", star["disallow"])
        self.assertIn("/policies/privacy-policy", star["allow"])
        self.assertEqual(block["sitemaps"], ["https://shop.example/sitemap.xml"])


if __name__ == "__main__":
    unittest.main()
