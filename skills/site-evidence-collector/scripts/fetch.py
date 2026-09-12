"""Polite, read-only HTTP for the collector. Standard library only.

Politeness is enforced here rather than trusted to callers:

- one request at a time per host, however many threads ask;
- the host's ``Crawl-delay`` as the minimum interval between requests;
- an honest User-Agent that names the audit;
- at most one retry, and only for a transient failure;
- GET only. There is no code path here that can send a body.

Redirects are followed by hand, so that every hop is recorded and the caller
can refuse a hop that leaves the site or that robots.txt disallows.
"""

import datetime
import gzip
import http.client
import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

ROBOTS_TOKEN = "agent-readiness-audit"
USER_AGENT = ("agent-readiness-audit/0.1 (read-only website audit; respects robots.txt; "
              "recommend-only, never modifies the site)")

MAX_BODY_BYTES = 5 * 1024 * 1024
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
TRANSIENT_STATUSES = frozenset({502, 503, 504})
RETRY_PAUSE_S = 1.0

_META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?([A-Za-z0-9_\-]+)""", re.I)


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Response:
    __slots__ = ("url", "final_url", "status", "headers", "body", "text", "content_type",
                 "redirect_chain", "error", "ttfb_ms", "fetch_ms", "truncated", "fetched_at")

    def __init__(self, url):
        self.url = url
        self.final_url = url
        self.status = None
        self.headers = {}
        self.body = b""
        self.text = ""
        self.content_type = None
        self.redirect_chain = []
        self.error = None
        self.ttfb_ms = None
        self.fetch_ms = None
        self.truncated = False
        self.fetched_at = utc_now()

    @property
    def ok(self):
        return self.status is not None and 200 <= self.status <= 299


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Surface every 3xx to the caller instead of following it silently."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _decode(body, content_type):
    charset = None
    if content_type and "charset=" in content_type.lower():
        charset = content_type.lower().split("charset=", 1)[1].split(";")[0].strip().strip('"\'')
    if not charset:
        match = _META_CHARSET.search(body[:4096])
        if match:
            charset = match.group(1).decode("ascii", "ignore").lower()
    for candidate in (charset, "utf-8"):
        if not candidate:
            continue
        try:
            return body.decode(candidate, errors="replace")
        except LookupError:
            continue
    return body.decode("utf-8", errors="replace")


class Fetcher:
    def __init__(self, user_agent=USER_AGENT, timeout=10.0):
        self.user_agent = user_agent
        self.timeout = timeout
        self._opener = urllib.request.build_opener(_NoRedirect)
        self._guard = threading.Lock()
        self._host_locks = {}
        self._last_request = {}
        self._delays = {}

    def set_crawl_delay(self, netloc, seconds):
        if seconds:
            self._delays[netloc.lower()] = float(seconds)

    def _lock_for(self, netloc):
        with self._guard:
            return self._host_locks.setdefault(netloc, threading.Lock())

    def get(self, url, may_follow=None, max_redirects=5, deadline=None, user_agent=None):
        """GET ``url``, following up to ``max_redirects`` hops ``may_follow`` permits."""
        chain = []
        current = url
        response = None
        for _ in range(max_redirects + 1):
            response = self._get_with_retry(current, deadline, user_agent)
            location = response.headers.get("location")
            if response.status in REDIRECT_STATUSES and location:
                nxt = urllib.parse.urljoin(current, location)
                chain.append(current)
                if may_follow is not None and not may_follow(nxt):
                    response.final_url = nxt
                    break
                current = nxt
                continue
            response.final_url = current
            break
        else:
            response.error = response.error or "more than %d redirects" % max_redirects
        response.url = url
        response.redirect_chain = chain
        return response

    def _get_with_retry(self, url, deadline, user_agent):
        response = self._get_once(url, deadline, user_agent)
        transient = response.status in TRANSIENT_STATUSES or (
            response.status is None and response.error and "budget" not in response.error)
        if transient and (deadline is None or time.monotonic() + RETRY_PAUSE_S < deadline):
            time.sleep(RETRY_PAUSE_S)
            response = self._get_once(url, deadline, user_agent)
        return response

    def _get_once(self, url, deadline, user_agent):
        response = Response(url)
        netloc = urllib.parse.urlsplit(url).netloc.lower()
        with self._lock_for(netloc):
            delay = self._delays.get(netloc, 0.0)
            wait = self._last_request.get(netloc, 0.0) + delay - time.monotonic()
            if wait > 0:
                if deadline is not None and time.monotonic() + wait >= deadline:
                    response.error = "budget exhausted before the crawl-delay elapsed"
                    return response
                time.sleep(wait)
            timeout = self.timeout
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0.2:
                    response.error = "budget exhausted"
                    return response
                timeout = min(timeout, remaining)
            request = urllib.request.Request(url, method="GET", headers={
                "User-Agent": user_agent or self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
                "Accept-Encoding": "gzip",
            })
            response.fetched_at = utc_now()
            started = time.monotonic()
            raw = None
            try:
                try:
                    handle = self._opener.open(request, timeout=timeout)
                except urllib.error.HTTPError as exc:
                    handle = exc
                response.ttfb_ms = round((time.monotonic() - started) * 1000, 1)
                response.status = handle.getcode() if hasattr(handle, "getcode") else handle.code
                response.headers = {k.lower(): v for k, v in (handle.headers or {}).items()}
                raw = handle.read(MAX_BODY_BYTES + 1) if hasattr(handle, "read") else b""
                handle.close()
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError,
                    http.client.HTTPException, ssl.SSLError, OSError, ValueError) as exc:
                response.error = "%s: %s" % (type(exc).__name__, getattr(exc, "reason", exc))
            finally:
                self._last_request[netloc] = time.monotonic()
            response.fetch_ms = round((time.monotonic() - started) * 1000, 1)
        if raw is not None:
            if len(raw) > MAX_BODY_BYTES:
                raw, response.truncated = raw[:MAX_BODY_BYTES], True
            encoding = response.headers.get("content-encoding", "").lower()
            try:
                if encoding == "gzip":
                    raw = gzip.decompress(raw)
                elif encoding == "deflate":
                    raw = zlib.decompress(raw)
            except (OSError, zlib.error, EOFError):
                pass
            response.body = raw
            response.content_type = response.headers.get("content-type")
            response.text = _decode(raw, response.content_type)
        return response
