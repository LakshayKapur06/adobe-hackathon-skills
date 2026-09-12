"""Headless Chromium rendering: navigate, wait, dump the DOM. Nothing else.

Read-only by construction. The only thing sent to the browser is a URL on the
command line; there is no automation channel, so this module cannot click,
type, submit a form or inject script, and the page's own scripts are the only
scripts that run. Images are not loaded, which lightens the load on the audited
site without changing the text a page assembles.

When the DOM is taken, and why it takes two attempts. Each flag has a failure
mode, established against Chrome 153 on python.org's home page and on a local
page whose iframe never responds:

- ``--dump-dom`` alone dumps at the load event. That is fast on an ordinary
  page (python.org's home page: 1.1s), but a page with a resource that never
  finishes never reaches load, and content a client-rendered page assembles
  just after load can be missed.
- ``--virtual-time-budget`` adds a quiet period, letting the page's timers and
  fetches settle before the dump. But virtual time stops advancing while a
  network request is pending, so on a page with a request that never settles it
  never expires, and ``--timeout`` set alongside it, measured in the same
  virtual time, never fires either. python.org's home page hung this way until
  killed at 20s.
- ``--timeout`` without a virtual-time budget runs in real time: it stops the
  navigation, fires DOMContentLoaded and load, and the DOM is dumped as it
  stands. The never-responding page returned in under 4s, with text written at
  DOMContentLoaded and again 800ms later.

So each page gets up to PAGE_TIMEOUT_S in two attempts. The first settles: load
plus QUIET_PERIOD_MS of virtual quiet, killed at SETTLE_ATTEMPT_S of real time.
If that returns nothing, the second is capped: ``--timeout=NAVIGATION_CAP_MS``
and no virtual clock. A page rendered the second way is listed in ``fallbacks``,
so the evidence can say that it had no quiet period.

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

ENV_OVERRIDES = ("CHROME_PATH", "CHROMIUM_PATH", "BROWSER_PATH")
PATH_NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome",
              "msedge", "microsoft-edge", "microsoft-edge-stable", "brave-browser", "brave")
PAGE_TIMEOUT_S = 10.0          # wall clock for one page, both attempts together
SETTLE_ATTEMPT_S = 5.0         # attempt 1 is killed at this point if it has not returned
QUIET_PERIOD_MS = 2000         # attempt 1: --virtual-time-budget after load
NAVIGATION_CAP_MS = 3000       # attempt 2: --timeout, in real time
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
        self.fallbacks = []                 # URLs rendered by the capped attempt
        self._lock = threading.Lock()
        name = os.path.splitext(os.path.basename(binary))[0] if binary else None
        self.label = "system-chromium:%s" % name if name else None

    def _command(self, url, profile, settle):
        command = [self.binary, "--headless=new", "--disable-gpu", "--no-first-run",
                   "--no-default-browser-check", "--disable-extensions", "--disable-sync",
                   "--disable-background-networking", "--mute-audio", "--hide-scrollbars",
                   "--blink-settings=imagesEnabled=false",
                   "--user-agent=%s" % self.user_agent, "--user-data-dir=%s" % profile]
        if settle:
            command.append("--virtual-time-budget=%d" % QUIET_PERIOD_MS)
        else:
            command.append("--timeout=%d" % NAVIGATION_CAP_MS)
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
        """Return ``(html or None, error or None, render_ms)`` within PAGE_TIMEOUT_S."""
        started = time.monotonic()
        html, error = self._attempt(url, True, min(SETTLE_ATTEMPT_S, self.page_timeout))
        if html is None:
            remaining = self.page_timeout - (time.monotonic() - started)
            if remaining > 1.0:
                html, second = self._attempt(url, False, remaining)
                if html is not None:
                    with self._lock:
                        self.fallbacks.append(url)
                else:
                    error = "settled attempt: %s; capped attempt: %s" % (error, second)
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
        with self._lock:
            self.fallbacks = []
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
