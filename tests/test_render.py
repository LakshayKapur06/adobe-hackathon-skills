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

    def test_the_navigation_cap_runs_in_real_time_with_no_virtual_clock(self):
        # --timeout is measured in virtual time whenever a virtual-time budget
        # is set, so the two must never appear together: that pairing waits
        # forever on a page whose requests never settle. The budget is not used
        # at all now, having returned no DOM on any sampled page of a real
        # ad-supported site, but the combination stays pinned against a revival.
        command = self.renderer._command("https://x.example/", "/tmp/p")
        self.assertIn("--timeout=%d" % render.NAVIGATION_CAP_MS, command)
        self.assertFalse(any(flag.startswith("--virtual-time-budget") for flag in command))

    def test_the_wall_clock_kill_sits_above_the_navigation_cap(self):
        # The kill is the guard of last resort: if it fired first it would end
        # navigations the cap was about to dump cleanly.
        self.assertGreater(render.PAGE_TIMEOUT_S, render.NAVIGATION_CAP_MS / 1000.0 + 1.0)

    def test_the_cap_allows_the_time_real_pages_need(self):
        # Measured: an ad-supported publisher's pages produced a DOM at 7.9s and
        # nothing at 5s. A cap below that silently renders less than the page has.
        self.assertGreaterEqual(render.NAVIGATION_CAP_MS, 8000)

    def test_the_browser_is_given_nothing_but_a_url(self):
        command = self.renderer._command("https://x.example/", "/tmp/p")
        self.assertEqual(command[-2:], ["--dump-dom", "https://x.example/"])
        for flag in command[1:]:
            self.assertFalse(flag.startswith("--remote-debugging"), flag)
            self.assertFalse(flag.startswith("--js-flags"), flag)


class ScriptedAttempt(render.Renderer):
    """A Renderer whose single browser run is scripted, to test render() anywhere."""

    def __init__(self, outcome):
        super().__init__("chrome", fetch.USER_AGENT)
        self.outcome = outcome
        self.attempts = []

    def _attempt(self, url, limit_s):
        self.attempts.append(limit_s)
        return self.outcome


class TestOneAttempt(unittest.TestCase):
    def test_a_page_is_rendered_in_exactly_one_attempt(self):
        renderer = ScriptedAttempt(("<html>dumped</html>", None))
        html, error, _ = renderer.render("https://x.example/")
        self.assertEqual((html, error), ("<html>dumped</html>", None))
        self.assertEqual(renderer.attempts, [render.PAGE_TIMEOUT_S])

    def test_a_failure_is_not_retried_and_not_an_exception(self):
        # A second attempt used to exist because the first could hang without
        # producing anything. Nothing hangs now, and a retry would spend another
        # page's worth of the render budget for a page that just produced none.
        renderer = ScriptedAttempt((None, "browser exited with status 1"))
        html, error, _ = renderer.render("https://x.example/")
        self.assertIsNone(html)
        self.assertEqual(len(renderer.attempts), 1)
        self.assertIn("browser exited with status 1", error)


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
        self.assertLess(elapsed, render.PAGE_TIMEOUT_S + 1.0)
        # The regression this guards: with a virtual-time budget set, neither
        # the budget nor --timeout ever expires on this page, and the run had to
        # be killed from outside with nothing to show. The real-time cap dumps
        # both scripts' output instead.


if __name__ == "__main__":
    unittest.main()
