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

    def test_the_settled_attempt_uses_virtual_time_and_no_navigation_cap(self):
        command = self.renderer._command("https://x.example/", "/tmp/p", settle=True)
        self.assertIn("--virtual-time-budget=%d" % render.QUIET_PERIOD_MS, command)
        self.assertFalse(any(flag.startswith("--timeout") for flag in command))

    def test_the_capped_attempt_uses_real_time_and_no_virtual_clock(self):
        # --timeout runs in virtual time when a virtual-time budget is set, so
        # the two must never be combined: that pairing hangs on a page whose
        # requests never settle.
        command = self.renderer._command("https://x.example/", "/tmp/p", settle=False)
        self.assertIn("--timeout=%d" % render.NAVIGATION_CAP_MS, command)
        self.assertFalse(any(flag.startswith("--virtual-time-budget") for flag in command))

    def test_both_attempts_fit_inside_the_page_cap(self):
        self.assertLessEqual(render.PAGE_TIMEOUT_S, 10.0)
        self.assertLess(render.SETTLE_ATTEMPT_S + render.NAVIGATION_CAP_MS / 1000.0 + 1.0,
                        render.PAGE_TIMEOUT_S)

    def test_the_browser_is_given_nothing_but_a_url(self):
        for settle in (True, False):
            command = self.renderer._command("https://x.example/", "/tmp/p", settle=settle)
            self.assertEqual(command[-2:], ["--dump-dom", "https://x.example/"])
            for flag in command[1:]:
                self.assertFalse(flag.startswith("--remote-debugging"), flag)
                self.assertFalse(flag.startswith("--js-flags"), flag)


class ScriptedAttempts(render.Renderer):
    """A Renderer whose browser runs are scripted, to test the fallback logic anywhere."""

    def __init__(self, settled, capped):
        super().__init__("chrome", fetch.USER_AGENT)
        self.outcomes = {True: settled, False: capped}
        self.attempts = []

    def _attempt(self, url, settle, limit_s):
        self.attempts.append((settle, limit_s))
        return self.outcomes[settle]


class TestFallback(unittest.TestCase):
    def test_a_page_that_settles_is_rendered_once(self):
        renderer = ScriptedAttempts(("<html>settled</html>", None), ("<html>capped</html>", None))
        html, error, _ = renderer.render("https://x.example/")
        self.assertEqual((html, error), ("<html>settled</html>", None))
        self.assertEqual([s for s, _ in renderer.attempts], [True])
        self.assertEqual(renderer.fallbacks, [])

    def test_a_page_that_never_settles_is_rendered_with_the_cap_and_recorded(self):
        renderer = ScriptedAttempts((None, "no DOM within 5.0s"), ("<html>capped</html>", None))
        html, error, _ = renderer.render("https://x.example/")
        self.assertEqual((html, error), ("<html>capped</html>", None))
        self.assertEqual([s for s, _ in renderer.attempts], [True, False])
        self.assertEqual(renderer.fallbacks, ["https://x.example/"])
        # The settled attempt is capped at SETTLE_ATTEMPT_S; the capped attempt
        # gets whatever real time remains of PAGE_TIMEOUT_S. These scripted
        # attempts take no time, so nearly all of it remains. Elapsed wall
        # clock is pinned by the real-browser test below.
        (_, first), (_, second) = renderer.attempts
        self.assertEqual(first, render.SETTLE_ATTEMPT_S)
        self.assertLessEqual(second, render.PAGE_TIMEOUT_S)

    def test_both_attempts_failing_is_an_error_not_an_exception(self):
        renderer = ScriptedAttempts((None, "no DOM within 5.0s"), (None, "browser exited with status 1"))
        html, error, _ = renderer.render("https://x.example/")
        self.assertIsNone(html)
        self.assertIn("settled attempt", error)
        self.assertIn("capped attempt", error)


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
        self.assertEqual(renderer.fallbacks, [site.base + "/"])
        self.assertLess(elapsed, render.PAGE_TIMEOUT_S + 1.0)


if __name__ == "__main__":
    unittest.main()
