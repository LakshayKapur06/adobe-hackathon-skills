"""robots.txt parsing and matching, following RFC 9309.

Every verdict this module produces can become a critical finding, so each
behaviour follows the standard exactly and tests/test_robots.py pins each one.
The same semantics are written out in prose in ../references/robots.md.

Observed content is data. Comments, and every line that is not one of the five
directives below, are discarded during parsing: they never influence a verdict
and never reach the evidence bundle. A comment addressed to "AI agents" is a
comment like any other.

Standard library only.
"""

import functools
import re
import urllib.parse

DIRECTIVES = ("user-agent", "allow", "disallow", "crawl-delay", "sitemap")

# The crawlers the evidence contract tracks, in contract order.
# Claude-SearchBot was added in contracts-v3: it is Anthropic's search crawler,
# separate from ClaudeBot's training collection, and without it an exclusion
# from Claude's search results could not be observed at all.
AI_AGENTS = ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended",
             "OAI-SearchBot", "CCBot", "Googlebot", "Claude-SearchBot")

# The closed vocabulary of robots.parse_reason. The first two outcomes that are
# not "ok" mean no restrictions apply; the last three mean nothing may be
# crawled. A finding must be able to say which one it saw, because they have
# opposite crawl semantics.
PARSE_REASONS = ("ok", "not_plausibly_robots", "absent_4xx", "unreachable",
                 "server_error", "rate_limited")

# RFC 9309 section 2.2.1 asks crawlers to choose tokens of letters, underscores
# and hyphens. Digits are accepted as well, because real crawlers carry them
# (MJ12bot, 360Spider) and a line that names one means that crawler: reading
# "MJ12bot" as "MJ" would apply its group to nobody. No tracked AI crawler, and
# not this audit's own token, reads differently either way.
_PRODUCT_TOKEN = re.compile(r"[A-Za-z0-9_-]+")
_PERCENT = re.compile(r"%[0-9a-fA-F]{2}")
_DIRECTIVE_LINE = re.compile(
    r"^[ \t]*(user-agent|allow|disallow|crawl-delay|sitemap)[ \t]*:", re.I | re.M)
_HTML_START = re.compile(r"<\s*(!doctype|html|head|body|meta|script|div|title)\b", re.I)


class Group:
    """One group: the user-agent lines that head it, and the rules under them."""

    __slots__ = ("agents", "rules", "crawl_delay")

    def __init__(self):
        self.agents = []       # user-agent values as written
        self.rules = []        # (allow: bool, pattern: str), in file order
        self.crawl_delay = None


def product_token(value):
    """The product token of a user-agent line, lower-cased; "" if none.

    ``GPTBot/1.1`` yields ``gptbot``. A line that begins with something other
    than a product token yields its leading token, exactly as a conforming
    crawler would read it.
    """
    match = _PRODUCT_TOKEN.match(value.strip())
    return match.group(0).lower() if match else ""


def parse(text):
    """Parse robots.txt text into (groups, sitemaps)."""
    if text.startswith("﻿"):
        text = text[1:]
    groups, sitemaps = [], []
    current = None
    in_agent_run = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            # Consecutive user-agent lines head one group (RFC 9309 2.1).
            if not in_agent_run:
                current = Group()
                groups.append(current)
            current.agents.append(value)
            in_agent_run = True
        elif key == "sitemap":
            # Sitemap lines are file-global and belong to no group.
            if value:
                sitemaps.append(value)
        elif key in ("allow", "disallow"):
            in_agent_run = False
            if current is not None:        # rules before any user-agent are ignored
                current.rules.append((key == "allow", value))
        elif key == "crawl-delay":
            in_agent_run = False
            if current is not None:
                try:
                    delay = float(value)
                except ValueError:
                    delay = None
                if delay is not None and delay >= 0:
                    current.crawl_delay = delay
        # Any other key is not a directive we act on, and is dropped.
    return groups, sitemaps


def _normalise(value):
    """Prepare a path or pattern for octet comparison.

    Non-ASCII characters are percent-encoded as UTF-8, and the hex digits of
    every percent-escape are upper-cased, because escapes compare
    case-insensitively (RFC 3986 2.1): %2b and %2B are the same octet.
    """
    encoded = "".join(ch if ord(ch) < 128 else urllib.parse.quote(ch, safe="") for ch in value)
    return _PERCENT.sub(lambda m: m.group(0).upper(), encoded)


@functools.lru_cache(maxsize=8192)
def _compile(pattern):
    """Compile a rule pattern: ``*`` matches any sequence, a final ``$`` anchors.

    Every other character is literal, including brackets, dots and question
    marks, so ``/[slug]/`` matches the characters it spells and nothing else.
    """
    anchored = pattern.endswith("$")
    body = _normalise(pattern[:-1] if anchored else pattern)
    regex = "".join(".*" if ch == "*" else re.escape(ch) for ch in body)
    return re.compile(regex + ("$" if anchored else ""), re.S)


def decide(rules, path):
    """Apply rules to a path: the longest matching pattern wins, ties go to allow.

    RFC 9309 2.2.2: the most specific match is the one with the most octets, and
    where an allow and a disallow rule are equally specific, allow is used. An
    empty pattern is no rule at all, which is why ``Disallow:`` permits
    everything.
    """
    target = _normalise(path)
    best_length, best_allow = -1, True
    for allow, pattern in rules:
        if not pattern:
            continue
        if _compile(pattern).match(target):
            length = len(_normalise(pattern).encode("utf-8"))
            if length > best_length or (length == best_length and allow):
                best_length, best_allow = length, allow
    return best_allow


class Robots:
    """A parsed robots.txt, queried by product token."""

    def __init__(self, groups, sitemaps):
        self.groups = groups
        self.sitemaps = sitemaps

    def _groups_for(self, tokens):
        """The groups that apply to a crawler, or None if none do.

        ``tokens`` runs most specific first, for crawlers with a documented
        fallback (Googlebot-Image falls back to Googlebot). The first token with
        a named group wins, and every group naming it is merged (RFC 9309 2.2.1).
        Only if no token is named does the ``*`` group apply. A group written for
        a different product never applies, however similar its name:
        ``adsbot-google`` does not govern ``Googlebot``.
        """
        for token in tokens:
            wanted = token.lower()
            named = [g for g in self.groups if any(product_token(a) == wanted for a in g.agents)]
            if named:
                return named
        star = [g for g in self.groups if any(a.strip() == "*" for a in g.agents)]
        return star or None

    def allowed(self, path, tokens):
        if path == "/robots.txt":          # implicitly allowed, RFC 9309 2.2.2
            return True
        groups = self._groups_for(tokens)
        if groups is None:
            return True
        return decide([rule for g in groups for rule in g.rules], path)

    def crawl_delay(self, tokens):
        groups = self._groups_for(tokens) or []
        delays = [g.crawl_delay for g in groups if g.crawl_delay is not None]
        return max(delays) if delays else None

    def verdict(self, token):
        """``allowed``, ``disallowed`` or ``unspecified`` for one crawler.

        ``unspecified`` means no group applies at all: no group names the
        crawler and there is no ``*`` group. A crawler covered only by ``*`` is
        ``allowed`` or ``disallowed`` according to that group, never
        ``unspecified``. The verdict is taken at the site root, ``/``; the full
        groups are recorded alongside it for any finer question.
        """
        if self._groups_for((token,)) is None:
            return "unspecified"
        return "allowed" if self.allowed("/", (token,)) else "disallowed"


def looks_like_robots(body, content_type):
    """Is this response plausibly a robots.txt, or a page served at that path?

    Some sites answer every path with the same HTML shell, /robots.txt
    included. Parsing that shell as robots.txt yields nonsense, so it is
    recognised first. The body decides: an empty body is a legitimate empty
    file, a body that starts like an HTML document is not a robots file whatever
    it contains, and otherwise at least one directive line must be present.

    A body of valid directives served with a text/html content type is accepted.
    Treating a mislabelled but genuine file as absent would crawl paths its
    owner disallowed, which is the worse of the two errors.
    """
    content_type = (content_type or "").split(";")[0].strip().lower() or "none"
    if not body.strip():
        return True, "empty robots.txt"
    if _HTML_START.match(body.lstrip("﻿ \t\r\n")):
        return False, ("not a robots.txt: the body is an HTML document "
                       "(content-type %s); treated as absent, no restrictions" % content_type)
    directives = len(_DIRECTIVE_LINE.findall(body))
    if directives == 0:
        return False, ("not a robots.txt: no directive lines in the body "
                       "(content-type %s); treated as absent, no restrictions" % content_type)
    return True, "%d directive lines" % directives


def interpret(status, body, content_type):
    """Turn a robots.txt fetch outcome into a crawl policy.

    Returns ``(mode, robots, reason, parse_reason)``. ``mode`` is one of:

    - ``parsed``: a real file; ``robots`` holds it. parse_reason ``ok``.
    - ``absent``: no restrictions apply (RFC 9309 2.3.1.3). A 4xx
      (``absent_4xx``), or a 2xx that is not a robots file
      (``not_plausibly_robots``).
    - ``unreachable``: nothing may be crawled (RFC 9309 2.3.1.4). A 5xx
      (``server_error``), a 429 (``rate_limited``), or no response at all
      (``unreachable``).

    429 is read as unreachable rather than as a 4xx. It is a rate-limit signal,
    and reading it as "crawl freely" would answer "slow down" by speeding up.

    A final status that is none of these, in practice a redirect chain longer
    than five hops, is unavailable under RFC 9309 2.3.1.2 and so has exactly the
    semantics of a 4xx. The parse_reason vocabulary is closed, and it is
    recorded as ``absent_4xx``, the value whose meaning it shares.
    """
    if status is None:
        return ("unreachable", None,
                "robots.txt could not be fetched (no response); treated as full disallow per RFC 9309",
                "unreachable")
    if status == 429:
        return ("unreachable", None,
                "robots.txt returned 429; a rate limit is treated as full disallow", "rate_limited")
    if 500 <= status <= 599:
        return ("unreachable", None,
                "robots.txt returned %d; treated as full disallow per RFC 9309" % status, "server_error")
    if 400 <= status <= 499:
        return "absent", None, "robots.txt returned %d; no restrictions apply" % status, "absent_4xx"
    if 200 <= status <= 299:
        plausible, reason = looks_like_robots(body or "", content_type)
        if not plausible:
            return "absent", None, reason, "not_plausibly_robots"
        groups, sitemaps = parse(body or "")
        return "parsed", Robots(groups, sitemaps), reason, "ok"
    return ("absent", None,
            "robots.txt ended on status %d; treated as unavailable, no restrictions" % status,
            "absent_4xx")


def evidence_block(url, status, fetched, mode, robots, parse_reason):
    """The ``robots`` object of the evidence bundle.

    Groups are recorded verbatim, one entry per user-agent line, so a rule can
    ask any question the verdicts do not answer. Comments are not recorded.
    ``parse_ok`` separates "a real robots.txt, perhaps with no rules" from
    "we were served something else", which the groups alone cannot.
    """
    if parse_reason not in PARSE_REASONS:
        raise ValueError("unknown parse_reason %r" % (parse_reason,))
    groups = []
    if robots is not None:
        for group in robots.groups:
            for agent in group.agents:
                groups.append({
                    "user_agent": agent,
                    "allow": [p for allow, p in group.rules if allow],
                    "disallow": [p for allow, p in group.rules if not allow],
                    "crawl_delay": group.crawl_delay,
                })
    if mode == "unreachable":
        verdicts = {agent: "disallowed" for agent in AI_AGENTS}
    elif mode == "absent" or robots is None:
        verdicts = {agent: "unspecified" for agent in AI_AGENTS}
    else:
        verdicts = {agent: robots.verdict(agent) for agent in AI_AGENTS}
    return {
        "fetched": fetched,
        "url": url,
        "status": status,
        "parse_ok": parse_reason == "ok",
        "parse_reason": parse_reason,
        "groups": groups,
        "ai_agents": verdicts,
        "sitemaps": list(robots.sitemaps) if robots is not None else [],
    }
