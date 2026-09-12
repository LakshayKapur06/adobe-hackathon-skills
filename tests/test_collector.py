"""The collector end to end, against sites served locally.

Three sites: the fixture site under tests/fixtures/site, an echo site that
serves one byte-identical shell at every path, and a site whose robots.txt
answers 503. The echo site runs twice, with and without rendering, because the
two dedupe behaviours are required to differ.
"""

import html
import http.server
import json
import pathlib
import re
import sys
import tempfile
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "site-evidence-collector" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "audit-orchestrator" / "scripts"))

import collect  # noqa: E402
import render  # noqa: E402
from jsonschema_lite import Validator  # noqa: E402

SCHEMAS = ROOT / "schemas"
REGISTRY = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in SCHEMAS.glob("*.schema.json")}
EVIDENCE_SCHEMA = Validator(REGISTRY["evidence.schema.json"], REGISTRY)
SITE = ROOT / "tests" / "fixtures" / "site"
SHELL = (ROOT / "tests" / "fixtures" / "echo-site" / "shell.html").read_bytes()


class Server:
    """A local HTTP server in a thread, recording every path requested."""

    def __init__(self, respond):
        server = self
        self.requested = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                server.requested.append(self.path)
                status, content_type, body = respond(self.path, server.base)
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = "http://127.0.0.1:%d" % self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


def fixture_site(path, base):
    """Serve tests/fixtures/site, rewriting its fixed localhost:8000 origin."""
    name = path.split("?", 1)[0].lstrip("/") or "index.html"
    target = SITE / name
    if not target.is_file():
        return 404, "text/html", b"<html><body><h1>Not found</h1></body></html>"
    body = target.read_bytes().replace(b"http://localhost:8000", base.encode())
    kind = {".html": "text/html; charset=utf-8", ".xml": "application/xml", ".txt": "text/plain"}
    return 200, kind.get(target.suffix, "application/octet-stream"), body


def echo_site(path, base):
    return 200, "text/html; charset=utf-8", SHELL


def robots_503(path, base):
    if path == "/robots.txt":
        return 503, "text/plain", b"Service Unavailable"
    return 200, "text/html", b"<html><body><p>must never be fetched</p></body></html>"


class StubRenderer:
    """Stands in for Chromium running the echo shell's script, which builds the
    page text from location.pathname. Used so the dedupe behaviour is tested on
    every machine; the real-browser test below covers the browser itself."""

    available = True
    label = "scripted-stand-in"
    unavailable_reason = None

    def __init__(self, fail_on=()):
        self.calls = []
        self.fail_on = fail_on

    def render(self, url):
        self.calls.append(url)
        path = re.sub(r"^https?://[^/]+", "", url) or "/"
        if any(path.startswith(p) for p in self.fail_on):
            return None, "render timed out after 20s", None
        page = html.escape(path)
        return ('<html><body><nav><a href="/">Home</a><a href="/products/alpha">Alpha</a>'
                '<a href="/products/beta">Beta</a><a href="/about">About</a></nav>'
                '<div id="app"><h1>Echo Store page %s</h1><p>Content assembled in the browser for %s.</p>'
                '</div></body></html>' % (page, page)), None, 12.0


class RefusingRenderer(StubRenderer):
    def render(self, url):
        raise AssertionError("--no-render must never consult the renderer")


def run(site, **kwargs):
    with Server(site) as server, tempfile.TemporaryDirectory() as workdir:
        kwargs.setdefault("no_egress", True)
        evidence = collect.collect(server.base, workdir, **kwargs)
        sidecars = {p.name: p.read_bytes() for p in (pathlib.Path(workdir) / "evidence" / "pages").iterdir()}
        written = json.loads((pathlib.Path(workdir) / "evidence" / "evidence.json").read_text(encoding="utf-8"))
        return evidence, written, sidecars, server.requested


def errors(evidence, stage):
    return [e["message"] for e in evidence["errors"] if e["stage"] == stage]


class TestFixtureSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence, cls.written, cls.sidecars, cls.requested = run(fixture_site, no_render=True)

    def test_output_is_exactly_schema_valid(self):
        self.assertEqual(EVIDENCE_SCHEMA.errors(self.written), [])
        self.assertEqual(self.evidence, self.written)

    def test_pages_types_and_robots_gate(self):
        pages = {p["url"].rsplit("/", 1)[-1]: p for p in self.evidence["pages"]}
        self.assertEqual(sorted(pages), ["", "about.html"])
        self.assertEqual(pages[""]["page_type"], "home")
        self.assertEqual(pages["about.html"]["page_type"], "about")
        self.assertNotIn("/cart", self.requested)                       # Disallow: /cart
        self.assertGreaterEqual(self.evidence["crawl"]["blocked_by_robots"], 1)

    def test_star_group_means_allowed_never_unspecified(self):
        self.assertEqual(set(self.evidence["robots"]["ai_agents"].values()), {"allowed"})

    def test_well_known_records_absence_as_an_observation(self):
        entries = {e["path"]: e for e in self.evidence["well_known"]}
        self.assertEqual(sorted(entries), ["/.well-known/ucp", "/agents.md", "/llms.txt"])
        for entry in entries.values():
            self.assertEqual((entry["status"], entry["present"]), (404, False))
        self.assertFalse(errors(self.evidence, "well_known"))

    def test_sidecars_match_their_hashes(self):
        import hashlib
        for page in self.evidence["pages"]:
            name = page["raw"]["text_path"].rsplit("/", 1)[-1]
            data = self.sidecars[name]
            self.assertEqual("sha256:" + hashlib.sha256(data).hexdigest(), page["raw"]["text_hash"])

    def test_no_render_path_is_degraded_not_silent(self):
        self.assertFalse(self.evidence["run_context"]["capabilities"]["js_render"])
        whats = [d["what"] for d in self.evidence["run_context"]["degradations"]]
        self.assertIn("render", whats)
        for page in self.evidence["pages"]:
            self.assertFalse(page["rendered"]["available"])

    def test_no_render_never_consults_a_renderer(self):
        evidence, *_ = run(fixture_site, no_render=True, renderer=RefusingRenderer())
        self.assertFalse(evidence["run_context"]["capabilities"]["js_render"])

    def test_same_fixture_twice_is_identical_except_timings(self):
        again, *_ = run(fixture_site, no_render=True)
        self.assertEqual(normalise(self.evidence), normalise(again))


def normalise(evidence):
    text = json.dumps(evidence, sort_keys=True)
    text = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", "<ts>", text)
    text = re.sub(r'"(ttfb_ms|fetch_ms|render_ms)": [0-9.]+', r'"\1": <ms>', text)
    return re.sub(r"http://127\.0\.0\.1:\d+", "<origin>", text)


class TestEchoSite(unittest.TestCase):
    """One byte-identical shell at every path. The two capabilities must dedupe differently."""

    def test_without_rendering_the_echo_collapses_to_one_page(self):
        evidence, written, _, _ = run(echo_site, no_render=True)
        self.assertEqual(EVIDENCE_SCHEMA.errors(written), [])
        self.assertEqual(len(evidence["pages"]), 1)
        self.assertEqual(evidence["crawl"]["fetched"], 1)
        self.assertEqual(sum(s["sampled"] for s in evidence["crawl"]["sampling"]["strata"]), 1)
        discovery = errors(evidence, "discovery")
        self.assertTrue(any(m.startswith("soft-404 baseline sha256:") for m in discovery))
        self.assertTrue(any(m.startswith("collapsed 3 of 4") for m in discovery))
        whats = [d["what"] for d in evidence["run_context"]["degradations"]]
        self.assertIn("page-content", whats)

    def test_with_rendering_every_page_is_kept_and_raw_identity_is_the_observation(self):
        evidence, written, _, _ = run(echo_site, renderer=StubRenderer())
        self.assertEqual(EVIDENCE_SCHEMA.errors(written), [])
        pages = evidence["pages"]
        self.assertEqual(len(pages), 4)
        self.assertEqual(len({p["raw"]["text_hash"] for p in pages}), 1)
        self.assertEqual(len({p["rendered"]["text_hash"] for p in pages}), 4)
        self.assertFalse(any(m.startswith("collapsed") for m in errors(evidence, "discovery")))
        self.assertNotIn("page-content", [d["what"] for d in evidence["run_context"]["degradations"]])

    def test_the_two_behaviours_differ_as_specified(self):
        without, *_ = run(echo_site, no_render=True)
        with_render, *_ = run(echo_site, renderer=StubRenderer())
        self.assertEqual((len(without["pages"]), len(with_render["pages"])), (1, 4))

    def test_a_shell_at_robots_txt_is_treated_as_absent(self):
        evidence, *_ = run(echo_site, no_render=True)
        self.assertEqual(set(evidence["robots"]["ai_agents"].values()), {"unspecified"})
        self.assertEqual(evidence["robots"]["groups"], [])
        self.assertTrue(any("not a robots.txt" in m for m in errors(evidence, "robots")))
        self.assertEqual([s["parse_ok"] for s in evidence["sitemaps"]], [False])

    def test_a_render_failure_degrades_one_page_and_never_fails_the_run(self):
        evidence, written, _, _ = run(echo_site, renderer=StubRenderer(fail_on=("/products/beta",)))
        self.assertEqual(EVIDENCE_SCHEMA.errors(written), [])
        by_path = {p["url"].split("/", 3)[-1]: p for p in evidence["pages"]}
        self.assertFalse(by_path["products/beta"]["rendered"]["available"])
        self.assertTrue(by_path["products/alpha"]["rendered"]["available"])
        self.assertTrue(any("failed to render" in d["reason"] for d in evidence["run_context"]["degradations"]))

    @unittest.skipUnless(render.find_browser()[0], "no Chromium-family browser on this machine")
    def test_with_a_real_browser(self):
        evidence, written, _, _ = run(echo_site, max_pages=4)
        self.assertEqual(EVIDENCE_SCHEMA.errors(written), [])
        if not evidence["run_context"]["capabilities"]["js_render"]:
            self.skipTest("browser present but failed its render probe")
        rendered = [p["rendered"] for p in evidence["pages"] if p["rendered"]["available"]]
        self.assertGreaterEqual(len(rendered), 2)
        self.assertEqual(len({r["text_hash"] for r in rendered}), len(rendered))


class TestUnreachableRobots(unittest.TestCase):
    def test_503_is_full_disallow_and_nothing_else_is_requested(self):
        evidence, written, _, requested = run(robots_503, no_render=True)
        self.assertEqual(EVIDENCE_SCHEMA.errors(written), [])
        self.assertEqual(set(requested), {"/robots.txt"})
        self.assertEqual(evidence["pages"], [])
        self.assertEqual(set(evidence["robots"]["ai_agents"].values()), {"disallowed"})
        self.assertEqual(evidence["robots"]["status"], 503)
        self.assertIn("crawl", [d["what"] for d in evidence["run_context"]["degradations"]])
        self.assertTrue(any("full disallow" in m for m in errors(evidence, "robots")))


def refusing_site(path, base):
    """Every path answers 403 with an edge block page, as a real CDN block does.

    Modelled on the Akamai page a live run met: a short HTML body carrying a
    reference number, served 403 with a text/html content type. To anything that
    does not check the status it is perfectly plausible page content, which is
    what makes it dangerous — extracted, it reads as a thin, link-less,
    markup-free home page, and every rule about thin content would fire on a
    site whose real home page we never saw.
    """
    return 403, "text/html", (b"<html><body><h1>Access Denied</h1><p>You don't have permission to "
                              b"access \"/\" on this server.</p><p>Reference #18.4c6c3f17</p>"
                              b"</body></html>")


class TestRefusedSite(unittest.TestCase):
    """A site that refuses us must never read as a site with nothing on it."""

    def test_the_block_page_text_reaches_no_part_of_the_bundle(self):
        evidence, written, _, _ = run(refusing_site, no_render=True)
        self.assertEqual(EVIDENCE_SCHEMA.errors(written), [])
        self.assertNotIn("Access Denied", json.dumps(written))
        self.assertNotIn("Reference #", json.dumps(written))

    def test_the_home_page_is_recorded_with_its_status_and_no_content(self):
        evidence, *_ = run(refusing_site, no_render=True)
        self.assertEqual(len(evidence["pages"]), 1)
        page = evidence["pages"][0]
        self.assertEqual(page["status"], 403)
        self.assertEqual(page["raw"]["text_len"], 0)
        self.assertEqual(page["raw"]["links"], [])
        self.assertEqual(page["raw"]["headings"], [])
        self.assertEqual(page["jsonld"], [])
        self.assertFalse(page["rendered"]["available"])

    def test_the_refusal_is_counted_and_degraded_never_silent(self):
        evidence, *_ = run(refusing_site, no_render=True)
        self.assertIn("crawl", [d["what"] for d in evidence["run_context"]["degradations"]])
        self.assertTrue(any("403" in d["reason"] for d in evidence["run_context"]["degradations"]))
        self.assertTrue(any("403" in m for m in errors(evidence, "fetch")))
        self.assertEqual(evidence["crawl"]["errors"], 1)
        # Fetched may never exceed discovered: that describes no possible crawl.
        self.assertEqual(evidence["crawl"]["discovered"], evidence["crawl"]["fetched"])

    def test_the_crawl_stops_at_the_front_door(self):
        _, _, _, requested = run(refusing_site, no_render=True)
        self.assertEqual(set(requested), {"/robots.txt", "/"})

    def test_a_refused_well_known_probe_records_no_entry(self):
        """Refused is not absent: the contract's missing entry means no answer."""
        def refuses_only_probes(path, base):
            if path in ("/llms.txt", "/agents.md", "/.well-known/ucp"):
                return 403, "text/html", b"<html><body>Access Denied</body></html>"
            return fixture_site(path, base)

        evidence, *_ = run(refuses_only_probes, no_render=True)
        self.assertEqual(evidence["well_known"], [])

    def test_a_rendered_block_page_is_never_a_javascript_only_verdict(self):
        """With a browser, the error document must not become a render delta."""
        evidence, *_ = run(refusing_site, renderer=StubRenderer())
        page = evidence["pages"][0]
        self.assertFalse(page["rendered"]["available"])
        self.assertIsNone(page["rendered"]["delta_ratio"])


class TestDiscoveryRecord(unittest.TestCase):
    """discovery is the structured record rules read; errors[] stays free text."""

    def test_normal_404s_mean_no_soft_404(self):
        evidence, *_ = run(fixture_site, no_render=True)
        soft = evidence["discovery"]["soft_404"]
        self.assertFalse(soft["detected"])
        self.assertIsNone(soft["baseline_text_hash"])
        self.assertEqual(len(soft["probe_paths"]), 2)
        for path in soft["probe_paths"]:
            self.assertRegex(path, r"^/[0-9a-f]{16}$")
        # One collapse, and not from soft-404: /index.html has the same text as
        # / and / names it as canonical, so it is the same document twice.
        self.assertEqual(evidence["discovery"]["collapsed_duplicate_text"], 1)
        self.assertEqual(evidence["discovery"]["collapsed_redirect_target"], 0)

    def test_probe_paths_are_the_same_on_every_run(self):
        first, *_ = run(fixture_site, no_render=True)
        second, *_ = run(fixture_site, no_render=True)
        self.assertEqual(first["discovery"]["soft_404"]["probe_paths"],
                         second["discovery"]["soft_404"]["probe_paths"])

    def test_echo_site_without_rendering(self):
        evidence, *_ = run(echo_site, no_render=True)
        soft = evidence["discovery"]["soft_404"]
        self.assertTrue(soft["detected"])
        self.assertEqual(soft["baseline_text_hash"], evidence["pages"][0]["raw"]["text_hash"])
        self.assertEqual(evidence["discovery"]["collapsed_duplicate_text"], 3)
        self.assertEqual(evidence["discovery"]["collapsed_redirect_target"], 0)

    def test_echo_site_with_rendering_collapses_nothing(self):
        evidence, *_ = run(echo_site, renderer=StubRenderer())
        self.assertTrue(evidence["discovery"]["soft_404"]["detected"])
        self.assertEqual(evidence["discovery"]["collapsed_duplicate_text"], 0)

    def test_well_known_files_that_are_the_shell_are_not_present(self):
        evidence, *_ = run(echo_site, no_render=True)
        for entry in evidence["well_known"]:
            with self.subTest(path=entry["path"]):
                self.assertEqual(entry["status"], 200)
                self.assertFalse(entry["present"])

    def test_robots_parse_fields(self):
        fixture, *_ = run(fixture_site, no_render=True)
        self.assertEqual((fixture["robots"]["parse_ok"], fixture["robots"]["parse_reason"]), (True, "ok"))
        echo, *_ = run(echo_site, no_render=True)
        self.assertEqual((echo["robots"]["parse_ok"], echo["robots"]["parse_reason"]),
                         (False, "not_plausibly_robots"))
        down, *_ = run(robots_503, no_render=True)
        self.assertEqual((down["robots"]["parse_ok"], down["robots"]["parse_reason"]), (False, "server_error"))


def redirect_site(path, base):
    """/a and /b both redirect to /target; the home page links to all three."""
    if path == "/robots.txt":
        return 200, "text/plain", b"User-agent: *\nDisallow:\n"
    if path == "/":
        return 200, "text/html", (b'<html><body><h1>Home</h1><a href="/a">A</a> <a href="/b">B</a> '
                                  b'<a href="/target">Target</a></body></html>')
    if path in ("/a", "/b"):
        return 301, "text/html", b""
    if path == "/target":
        return 200, "text/html", b"<html><body><h1>Target</h1><p>The one real page.</p></body></html>"
    return 404, "text/html", b"<html><body>Not found</body></html>"


class RedirectServer(Server):
    """Server, plus the Location header a 301 needs."""

    def __init__(self, respond):
        super().__init__(respond)
        handler = self.httpd.RequestHandlerClass
        original_send = handler.send_response

        def send_response(this, code, message=None):
            original_send(this, code, message)
            if code == 301:
                this.send_header("Location", "/target")
        handler.send_response = send_response


class TestRedirectKey(unittest.TestCase):
    def test_a_final_url_already_held_is_never_fetched_again(self):
        with RedirectServer(redirect_site) as server, tempfile.TemporaryDirectory() as workdir:
            evidence = collect.collect(server.base, workdir, no_render=True, no_egress=True)
            requested = list(server.requested)
        self.assertEqual([p["url"].rsplit("/", 1)[-1] for p in evidence["pages"]], ["", "a"])
        self.assertEqual(evidence["pages"][1]["final_url"], server.base + "/target")
        # /a is fetched and lands on /target. /b redirects there too, and the hop
        # is refused rather than followed; /target itself is never requested
        # directly. Both are counted.
        self.assertEqual(evidence["discovery"]["collapsed_redirect_target"], 2)
        self.assertEqual(requested.count("/target"), 1)
        self.assertEqual(EVIDENCE_SCHEMA.errors(evidence), [])


if __name__ == "__main__":
    unittest.main()
