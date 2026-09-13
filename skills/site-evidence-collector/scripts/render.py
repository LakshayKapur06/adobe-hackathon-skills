"""Headless Chromium rendering: navigate, wait, dump the DOM. Nothing else.

Read-only by construction. The only thing sent to the browser is a URL on the
command line; there is no automation channel, so this module cannot click,
type, submit a form or inject script, and the page's own scripts are the only
scripts that run. Images are not loaded, which lightens the load on the audited
site without changing the text a page assembles.

When the DOM is taken. One attempt per page: ``--timeout=NAVIGATION_CAP_MS``,
which runs in real time, stops the navigation at the cap, fires
DOMContentLoaded and load, and dumps the DOM as it stands. A wall-clock kill at
PAGE_TIMEOUT_S sits outside the browser as the guard of last resort.

Two flags were measured and rejected, against Chrome 153 on an open-source
foundation's home page, on an
ad-supported publisher's article and topic pages, and on a local page whose
iframe never responds:

- ``--dump-dom`` alone dumps at the load event. Fast on an ordinary page
  (that home page: 1.1s), but a page with one resource that never
  finishes never reaches load at all, so nothing is dumped until the outer kill.
- ``--virtual-time-budget`` was meant to add a quiet period after load. Virtual
  time stops advancing while any network request is pending, so on a page with
  a request that never settles it never expires — and ``--timeout`` alongside
  it, measured on the same paused clock, never fires either. That home page hung
  this way until killed at 20s.

That much was known. What a real publisher then showed is that the quiet-period
attempt fails on ordinary pages too: on every sampled page of an ad-supported
news site it returned no DOM within 5s, while a real-time cap returned the full
text in 7.9s. Those pages need about eight seconds to assemble, and third-party
ad and tracker requests keep virtual time from ever advancing.

But a real-time cap dumps at the load event, and a page that assembles itself
*after* load is invisible to it. On that same site's subscription page the
capped attempt returned a 33 KB body containing not one character of text,
while a 5s virtual-time budget returned 3152 characters — the plans, the prices
and the FAQ, all mounted after load. Nothing else available here can see past
the load event: this module has no automation channel by design, so it cannot
wait on a selector or poll the DOM.

So neither flag is right on its own, and the original error was one of order
rather than of choice. The quiet period used to run first, spending half of
every page's budget before the attempt that usually works. Now the capped
attempt runs first, and the quiet period runs only when the capped attempt came
back with almost no text — the one signal that distinguishes "this page really
has no content" from "this page has not assembled it yet". A page that renders
to real text pays nothing for the second attempt, and a page that renders to
nothing gets the only attempt that can help it.

Virtual time is given a small budget with a real-time kill over it, because a
larger budget stalls on pending requests: 5s of virtual time returned in 5.5s,
while 15s of it took 32.6s for identical text.

Discovery is portable: an explicit override first, then the PATH, then each
platform's usual install locations. If nothing is found, rendering is simply
unavailable and the audit proceeds without it.
"""

import concurrent.futures
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

import extract

ENV_OVERRIDES = ("CHROME_PATH", "CHROMIUM_PATH", "BROWSER_PATH")
PATH_NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome",
              "msedge", "microsoft-edge", "microsoft-edge-stable", "brave-browser", "brave")
NAVIGATION_CAP_MS = 8000       # attempt 1: --timeout, real time. Publisher pages need ~8s
CAP_ATTEMPT_S = 11.0           # attempt 1: wall-clock kill, above the navigation cap
QUIET_PERIOD_MS = 5000         # attempt 2: --virtual-time-budget, to see past the load event
SETTLE_ATTEMPT_S = 9.0         # attempt 2: wall-clock kill, the guarantee the flag lacks
HYDRATION_FLOOR = 500          # attempt 1 text below this means "maybe not assembled yet"
PAGE_TIMEOUT_S = 20.0          # both attempts together, for the few pages that need both
MAX_CONCURRENT = 3


def _platform_candidates():
    if sys.platform == "darwin":
        apps = ("Google Chrome.app/Contents/MacOS/Google Chrome",
                "Chromium.app/Contents/MacOS/Chromium",
                "Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "Brave Browser.app/Contents/MacOS/Brave Browser")
        roots = ("/Applications", os.path.expanduser("~/Applications"))
        return [os.path.join(root, app) for root in roots for app in apps]
    if os.name == "nt":
        bases = [os.environ.get(v) for v in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
        rel = (r"Google\Chrome\Application\chrome.exe", r"Microsoft\Edge\Application\msedge.exe",
               r"Chromium\Application\chrome.exe", r"BraveSoftware\Brave-Browser\Application\brave.exe")
        return [os.path.join(b, r) for b in bases if b for r in rel]
    return ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium",
            "/usr/bin/chromium-browser", "/snap/bin/chromium", "/usr/bin/microsoft-edge",
            "/opt/google/chrome/chrome", "/opt/microsoft/msedge/msedge"]


def find_browser():
    """Locate a Chromium-family binary. Returns ``(path or None, note)``."""
    for variable in ENV_OVERRIDES:
        value = os.environ.get(variable)
        if value:
            if os.path.isfile(value):
                return value, "from %s" % variable
            note = "%s points at %s, which does not exist; searched elsewhere" % (variable, value)
            break
    else:
        note = None
    for name in PATH_NAMES:
        found = shutil.which(name)
        if found:
            return found, note or "found on PATH"
    for candidate in _platform_candidates():
        if os.path.isfile(candidate):
            return candidate, note or "found at a standard install location"
    return None, note or "no Chromium-family browser found on PATH or in standard locations"


def _text_len(html, url):
    """How much text a DOM actually yields, by the same extractor the bundle uses.

    Deciding on extracted text rather than on DOM size is the point: the page
    that motivated the second attempt returned a 33 KB body carrying not one
    character of text.
    """
    return extract.parse_document(html, url)["text_len"]


def _kill_tree(process):
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)],
                           capture_output=True, timeout=10)
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        process.kill()
    except OSError:
        pass


class Renderer:
    """Renders pages with a local Chromium-family browser, if one works."""

    def __init__(self, binary, user_agent, page_timeout=PAGE_TIMEOUT_S):
        self.binary = binary
        self.user_agent = user_agent
        self.page_timeout = page_timeout
        self.available = False
        self.unavailable_reason = None
        self._lock = threading.Lock()
        name = os.path.splitext(os.path.basename(binary))[0] if binary else None
        self.label = "system-chromium:%s" % name if name else None

    def _command(self, url, profile, settle):
        command = [self.binary, "--headless=new", "--disable-gpu", "--no-first-run",
                   "--no-default-browser-check", "--disable-extensions", "--disable-sync",
                   "--disable-background-networking", "--mute-audio", "--hide-scrollbars",
                   "--blink-settings=imagesEnabled=false",
                   "--user-agent=%s" % self.user_agent, "--user-data-dir=%s" % profile]
        # Never both: --timeout is measured in virtual time whenever a virtual
        # clock is running, so the pair waits forever on a page whose requests
        # never settle. The wall-clock kill is what bounds the settle attempt.
        command.append("--virtual-time-budget=%d" % QUIET_PERIOD_MS if settle
                       else "--timeout=%d" % NAVIGATION_CAP_MS)
        command += ["--dump-dom", url]
        if os.name != "nt" and hasattr(os, "geteuid") and os.geteuid() == 0:
            command.insert(1, "--no-sandbox")     # Chromium refuses to sandbox as root
        return command

    def _attempt(self, url, settle, limit_s):
        """One browser run. Returns ``(html or None, error or None)``."""
        profile = tempfile.mkdtemp(prefix="ara-render-")    # a fresh, throwaway browser profile
        try:
            kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.DEVNULL}
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                kwargs["start_new_session"] = True
            try:
                process = subprocess.Popen(self._command(url, profile, settle), **kwargs)
            except OSError as exc:
                return None, "browser failed to start: %s" % exc
            try:
                out, _ = process.communicate(timeout=limit_s)
            except subprocess.TimeoutExpired:
                _kill_tree(process)
                process.communicate()
                return None, "no DOM within %.1fs" % limit_s
        finally:
            shutil.rmtree(profile, ignore_errors=True)
        if process.returncode != 0 or not out.strip():
            return None, "browser exited with status %s and no DOM" % process.returncode
        return out.decode("utf-8", errors="replace"), None

    def render(self, url):
        """Return ``(html or None, error or None, render_ms)`` within PAGE_TIMEOUT_S.

        The capped attempt first. The settle attempt only if that came back with
        almost no text, and then whichever found more of it: a page really can
        have nothing to say, and the second attempt is how we tell that apart
        from a page that had not finished saying it.
        """
        started = time.monotonic()
        html, error = self._attempt(url, False, min(CAP_ATTEMPT_S, self.page_timeout))
        if html is not None and _text_len(html, url) >= HYDRATION_FLOOR:
            return html, None, round((time.monotonic() - started) * 1000, 1)

        remaining = self.page_timeout - (time.monotonic() - started)
        if remaining > 1.0:
            settled, settle_error = self._attempt(url, True, min(SETTLE_ATTEMPT_S, remaining))
            if settled is not None and (html is None or _text_len(settled, url) > _text_len(html, url)):
                html = settled
            elif html is None:
                error = "capped attempt: %s; settle attempt: %s" % (error, settle_error)
        elapsed = round((time.monotonic() - started) * 1000, 1)
        if html is None:
            return None, "render failed within %.0fs (%s)" % (self.page_timeout, error), elapsed
        return html, None, elapsed

    def probe(self):
        """Confirm the browser actually renders, not merely that it exists."""
        html, error, _ = self.render("data:text/html,<p>render-probe-ok</p>")
        self.available = bool(html and "render-probe-ok" in html)
        if not self.available:
            self.unavailable_reason = "browser found but failed its render probe: %s" % (error or "no output")
        return self.available


def render_many(renderer, urls, budget_s, max_workers=MAX_CONCURRENT):
    """Render in page order, at most ``max_workers`` at once, within ``budget_s``.

    Returns ``{url: (html, error, render_ms)}``. A URL the budget did not reach
    is absent from the result; the caller marks it fetch-only and degraded.
    """
    deadline = time.monotonic() + budget_s
    results = {}
    pending = list(urls)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        running = {}
        while pending or running:
            while pending and len(running) < max_workers and time.monotonic() < deadline:
                url = pending.pop(0)
                running[pool.submit(renderer.render, url)] = url
            if not running:
                break
            done, _ = concurrent.futures.wait(
                running, timeout=max(0.1, deadline - time.monotonic()),
                return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                results[running.pop(future)] = future.result()
            if time.monotonic() >= deadline and not done:
                break
    return results
