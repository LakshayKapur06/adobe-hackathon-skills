"""Rendering must not wait on a page that never finishes loading.

On a client-rendered site every page is the shell, so a render that waits for
the load event, or for a virtual-time budget that never expires, produces
nothing on exactly the site type that most needs a raw-versus-rendered
comparison.
"""

import http.server
import pathlib
import sys
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "site-evidence-collector" / "scripts"))

import fetch  # noqa: E402
import render  # noqa: E402

# Text written at DOMContentLoaded and again 800ms later, and an iframe whose
# server never answers, so neither the load event nor virtual time ever
# arrives on its own.
PAGE = b"""<!doctype html><html><head><title>never finishes</title>
<script>
document.addEventListener("DOMContentLoaded", function () {
  var p = document.createElement("p"); p.textContent = "written-at-dcl"; document.body.appendChild(p);
  setTimeout(function () {
    var q = document.createElement("p"); q.textContent = "written-after-800ms"; document.body.appendChild(q);
  }, 800);
});
</script></head><body><h1>Never finishes loading</h1><iframe src="/hang"></iframe></body></html>"""


class _Quiet(http.server.ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def handle_error(self, request, client_address):
        pass     # the hanging request is abandoned by the browser, by design


class HangingSite:
    def __enter__(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/hang":
                    time.sleep(30)
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(PAGE)))
                self.end_headers()
                self.wfile.write(PAGE)

            def log_message(self, *args):
                pass

        self.httpd = _Quiet(("127.0.0.1", 0), Handler)
        self.base = "http://127.0.0.1:%d" % self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


class TestRenderCommand(unittest.TestCase):
    """Runs everywhere: the flags each attempt uses, and the time they are given."""

    def setUp(self):
        self.renderer = render.Renderer("chrome", fetch.USER_AGENT)

    def test_the_two_clocks_are_never_combined(self):
        # --timeout is measured in virtual time whenever a virtual clock is
        # running, so the pair waits forever on a page whose requests never
        # settle. Each attempt uses exactly one of them.
        capped = self.renderer._command("https://x.example/", "/tmp/p", settle=False)
        self.assertIn("--timeout=%d" % render.NAVIGATION_CAP_MS, capped)
        self.assertFalse(any(f.startswith("--virtual-time-budget") for f in capped))
        settled = self.renderer._command("https://x.example/", "/tmp/p", settle=True)
        self.assertIn("--virtual-time-budget=%d" % render.QUIET_PERIOD_MS, settled)
        self.assertFalse(any(f.startswith("--timeout") for f in settled))

    def test_every_wall_clock_kill_sits_above_the_flag_it_bounds(self):
        # A kill that fired first would end navigations the cap was about to
        # dump cleanly; over the settle attempt it is the only bound there is.
        self.assertGreater(render.CAP_ATTEMPT_S, render.NAVIGATION_CAP_MS / 1000.0 + 1.0)
        self.assertGreater(render.SETTLE_ATTEMPT_S, render.QUIET_PERIOD_MS / 1000.0 + 1.0)
        self.assertGreaterEqual(render.PAGE_TIMEOUT_S, render.CAP_ATTEMPT_S + render.SETTLE_ATTEMPT_S)

    def test_the_cap_allows_the_time_real_pages_need(self):
        # Measured: an ad-supported publisher's pages produced a DOM at 7.9s and
        # nothing at 5s. A cap below that silently renders less than the page has.
        self.assertGreaterEqual(render.NAVIGATION_CAP_MS, 8000)

    def test_the_browser_is_given_nothing_but_a_url(self):
        for settle in (False, True):
            command = self.renderer._command("https://x.example/", "/tmp/p", settle=settle)
            self.assertEqual(command[-2:], ["--dump-dom", "https://x.example/"])
            for flag in command[1:]:
                self.assertFalse(flag.startswith("--remote-debugging"), flag)
                self.assertFalse(flag.startswith("--js-flags"), flag)


def _page(text):
    return "<html><body><p>%s</p></body></html>" % text


class ScriptedAttempts(render.Renderer):
    """A Renderer whose browser runs are scripted, to test render() anywhere."""

    def __init__(self, capped, settled):
        super().__init__("chrome", fetch.USER_AGENT)
        self.outcomes = {False: capped, True: settled}
        self.attempts = []

    def _attempt(self, url, settle, limit_s):
        self.attempts.append(settle)
        return self.outcomes[settle]


class TestSecondAttemptIsConditional(unittest.TestCase):
    """The settle attempt is paid for only where it can help."""

    def test_a_page_with_real_text_is_rendered_once(self):
        renderer = ScriptedAttempts((_page("x" * render.HYDRATION_FLOOR), None), (_page("later"), None))
        html, error, _ = renderer.render("https://x.example/")
        self.assertIn("x" * 20, html)
        self.assertIsNone(error)
        self.assertEqual(renderer.attempts, [False])

    def test_a_page_that_renders_to_nothing_gets_the_settle_attempt(self):
        # The case that motivated this: a 33 KB body with no text in it, whose
        # content mounts after the load event the capped attempt dumps at.
        renderer = ScriptedAttempts((_page(""), None), (_page("y" * 900), None))
        html, error, _ = renderer.render("https://x.example/")
        self.assertIn("y" * 20, html)
        self.assertIsNone(error)
        self.assertEqual(renderer.attempts, [False, True])

    def test_the_capped_result_is_kept_when_settling_finds_no_more(self):
        # A page can legitimately have almost nothing to say. Settling must not
        # replace a real result with a worse one.
        renderer = ScriptedAttempts((_page("short but real"), None), (_page(""), None))
        html, _, _ = renderer.render("https://x.example/")
        self.assertIn("short but real", html)
        self.assertEqual(renderer.attempts, [False, True])

    def test_both_attempts_failing_is_an_error_not_an_exception(self):
        renderer = ScriptedAttempts((None, "no DOM within 11.0s"), (None, "browser exited with status 1"))
        html, error, _ = renderer.render("https://x.example/")
        self.assertIsNone(html)
        self.assertIn("capped attempt", error)
        self.assertIn("settle attempt", error)


@unittest.skipUnless(render.find_browser()[0], "no Chromium-family browser on this machine")
class TestRealBrowser(unittest.TestCase):
    def test_a_page_that_never_finishes_loading_is_still_dumped(self):
        renderer = render.Renderer(render.find_browser()[0], fetch.USER_AGENT)
        with HangingSite() as site:
            started = time.monotonic()
            html, error, _ = renderer.render(site.base + "/")
            elapsed = time.monotonic() - started
        self.assertIsNone(error, error)
        self.assertIn("written-at-dcl", html)
        self.assertIn("written-after-800ms", html)
        # Bounded by the page timeout plus browser start-up, which varies with
        # machine load: one second of slack failed on a busy machine at 22.3s.
        self.assertLess(elapsed, render.PAGE_TIMEOUT_S + 5.0)
        # The regression this guards: with a virtual-time budget set, neither
        # the budget nor --timeout ever expires on this page, and the run had to
        # be killed from outside with nothing to show. The real-time cap dumps
        # both scripts' output instead.


if __name__ == "__main__":
    unittest.main()
