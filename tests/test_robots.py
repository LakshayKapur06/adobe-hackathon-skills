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


def block(status, body, content_type="text/plain", url="https://x.example/robots.txt"):
    mode, parsed, _, reason = robots.interpret(status, body, content_type)
    return robots.evidence_block(url, status, status is not None, mode, parsed, reason)


class TestGroupSelection(unittest.TestCase):
    def test_named_group_wins_over_star(self):
        r = from_text("User-agent: *\nDisallow: /\n\nUser-agent: GPTBot\nAllow: /\n")
        self.assertTrue(r.allowed("/page", ("GPTBot",)))
        self.assertFalse(r.allowed("/page", ("ClaudeBot",)))

    def test_claude_searchbot_and_claudebot_are_separate_products(self):
        # contracts-v3: Anthropic's training and search crawlers are governed
        # independently, so a group for one must never decide the other.
        r = from_text("User-agent: ClaudeBot\nDisallow: /\n")
        self.assertEqual(r.verdict("ClaudeBot"), "disallowed")
        self.assertEqual(r.verdict("Claude-SearchBot"), "unspecified")
        r = from_text("User-agent: *\nDisallow: /\n\nUser-agent: Claude-SearchBot\nAllow: /\n")
        self.assertEqual(r.verdict("Claude-SearchBot"), "allowed")
        self.assertEqual(r.verdict("ClaudeBot"), "disallowed")

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
                mode, parsed, _, reason = robots.interpret(status, "User-agent: *\nDisallow: /\n", "text/plain")
                self.assertEqual((mode, reason), ("absent", "absent_4xx"))
                self.assertIsNone(parsed)

    def test_5xx_429_and_no_response_mean_full_disallow_each_named(self):
        cases = {500: "server_error", 502: "server_error", 503: "server_error",
                 504: "server_error", 429: "rate_limited", None: "unreachable"}
        for status, expected in cases.items():
            with self.subTest(status=status):
                mode, _, text, reason = robots.interpret(status, "", None)
                self.assertEqual(mode, "unreachable")
                self.assertEqual(reason, expected)
                self.assertIn("disallow", text)

    def test_a_redirect_limit_is_unavailable_with_4xx_semantics(self):
        mode, _, _, reason = robots.interpret(301, "", None)
        self.assertEqual((mode, reason), ("absent", "absent_4xx"))

    def test_unreachable_records_every_agent_as_disallowed(self):
        b = block(503, "")
        self.assertEqual(set(b["ai_agents"].values()), {"disallowed"})
        self.assertEqual(b["groups"], [])
        self.assertEqual((b["parse_ok"], b["parse_reason"]), (False, "server_error"))

    def test_absent_records_every_agent_as_unspecified(self):
        b = block(404, "")
        self.assertEqual(set(b["ai_agents"].values()), {"unspecified"})
        self.assertEqual((b["parse_ok"], b["parse_reason"]), (False, "absent_4xx"))

    def test_an_unknown_parse_reason_is_refused(self):
        with self.assertRaises(ValueError):
            robots.evidence_block("https://x.example/robots.txt", 200, True, "parsed", None, "fine")


class TestParseOk(unittest.TestCase):
    """parse_ok separates a real, empty robots.txt from a webpage served in its place."""

    SHELL = "<!doctype html><html><head><title>Shop</title></head><body><div id=app></div></body></html>"

    def test_an_empty_file_is_a_real_robots_txt(self):
        b = block(200, "")
        self.assertEqual((b["parse_ok"], b["parse_reason"]), (True, "ok"))
        self.assertEqual(set(b["ai_agents"].values()), {"unspecified"})

    def test_an_html_shell_is_not_a_robots_file(self):
        b = block(200, self.SHELL, "text/html; charset=utf-8")
        self.assertEqual((b["parse_ok"], b["parse_reason"]), (False, "not_plausibly_robots"))
        self.assertEqual(set(b["ai_agents"].values()), {"unspecified"})
        self.assertEqual(b["groups"], [])

    def test_the_two_look_alike_without_parse_ok(self):
        # Both have no groups and every agent unspecified. Only parse_ok tells them apart.
        empty, shell = block(200, ""), block(200, self.SHELL, "text/html")
        self.assertEqual((empty["groups"], empty["ai_agents"]), (shell["groups"], shell["ai_agents"]))
        self.assertNotEqual(empty["parse_ok"], shell["parse_ok"])

    def test_html_containing_directive_text_is_still_html(self):
        page = "<html><body><pre>User-agent: *\nDisallow: /</pre></body></html>"
        self.assertFalse(robots.looks_like_robots(page, "text/html")[0])

    def test_prose_with_no_directives_is_not_a_robots_file(self):
        self.assertEqual(block(200, "hello world\nthis is not it\n")["parse_reason"], "not_plausibly_robots")

    def test_valid_directives_mislabelled_as_html_are_honoured(self):
        mode, parsed, _, reason = robots.interpret(200, "User-agent: *\nDisallow: /private\n", "text/html")
        self.assertEqual((mode, reason), ("parsed", "ok"))
        self.assertFalse(parsed.allowed("/private", ("x",)))


class TestObservedContentIsData(unittest.TestCase):
    def test_comments_never_reach_the_evidence(self):
        text = (FIXTURES / "shopify-storefront.txt").read_text(encoding="utf-8")
        serialised = json.dumps(block(200, text, url="https://shop.example/robots.txt"))
        # Phrases unique to the comments. ("recommend" alone would match the real
        # rule /recommendations/products, which is data and belongs there.)
        for phrase in ("recommend that your user", "shopping skill", "Dear AI agent",
                       "on their behalf", "Synthetic", "adsbot ignores"):
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, serialised)

    def test_groups_are_recorded_verbatim_per_user_agent_line(self):
        text = (FIXTURES / "shopify-storefront.txt").read_text(encoding="utf-8")
        b = block(200, text, url="https://shop.example/robots.txt")
        agents = [g["user_agent"] for g in b["groups"]]
        self.assertEqual(agents, ["*", "adsbot-google", "Nutch", "AhrefsBot", "MJ12bot", "Pinterest"])
        star = b["groups"][0]
        self.assertIn("/collections/*sort_by*", star["disallow"])
        self.assertIn("/policies/privacy-policy", star["allow"])
        self.assertEqual(b["sitemaps"], ["https://shop.example/sitemap.xml"])
        self.assertEqual((b["parse_ok"], b["parse_reason"]), (True, "ok"))


if __name__ == "__main__":
    unittest.main()
