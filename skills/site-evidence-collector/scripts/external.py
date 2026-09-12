"""Pass 2: ask the world what it says about this brand, without privileged search.

Four keyless providers, all writing one schema. Nothing downstream branches on
which of them ran, only on the coverage label and the confidence gate, so a host
that later volunteers a search capability changes the breadth of this and not
the shape of it.

- **Wikipedia** — prose, and the source most assistants demonstrably read.
  Searched through ``api.wikimedia.org``, then *verified by outbound link*: an
  article is only accepted as being about this brand if it links to this brand's
  domain. A name search alone will happily return a village in Bavaria, or in
  one real case both "The Indian Express" and "The New Indian Express".
- **Declared sameAs targets** — the profiles the site itself points at. The
  cheapest high-value check available: a `sameAs` naming a page that does not
  exist, or does not mention the brand, is a broken identity graph.
- **Wayback CDX** — coarse signals only: first-seen date and snapshot cadence.
  A content digest changes on any byte, rotating tokens included, so it can
  never be read as "last substantive change" (the Wayback correction in
  docs/DECISIONS.md).

**The coverage bound is disclosed, never hidden.** Without privileged search
there is no open-web recall. Breadth is measured over an *enumerable frontier* —
encyclopedic entries, the profiles the brand itself points to, its own archived
history — and ``frontier_size`` reports how large that frontier was. A report
built on this may say "of the sources we could enumerate", and may never imply
omniscience.

**Wikidata is deliberately absent, and this is why.** It would be the best
source here — a machine-readable public record, verifiable by its official-website
property, immune to the namesake problem. Every endpoint that can reach it is
disallowed by Wikidata's own robots.txt for crawlers: ``/w/api.php``,
``/w/rest.php``, ``Special:Search``, and ``query.wikidata.org/sparql``. Only
``Special:EntityData/{id}.json`` is permitted, and that needs an entity id we
have no permitted way to look up. So it is not used. Auditing sites on their
crawler policy while quietly making an exception for ourselves is the one
inconsistency this project cannot afford, and the coverage lost is reported in
``frontier_size`` rather than hidden.

**robots.txt is respected on third-party hosts too.** That is easy to forget and
it is the exact guardrail this audit exists to check for: auditing someone's
crawler policy while ignoring everyone else's would be indefensible. It is not
theoretical — it is what removed Wikidata above.

Standard library only.
"""

import json
import re
import time
import urllib.parse

import extract
import urls

WIKIPEDIA_SEARCH = "https://api.wikimedia.org/core/v1/wikipedia/en/search/page"
WIKIPEDIA_ARTICLE = "https://en.wikipedia.org/wiki/"
MAX_ARTICLES = 3
WAYBACK_CDX = "https://web.archive.org/cdx/search/cdx"
MAX_ORIGINS = 24
MAX_HITS = 60
MAX_SAMEAS = 8
SNIPPET_CHARS = 400

# Where a corroborating URL came from, mapped to the closed source_type
# vocabulary. Anything unrecognised is a directory listing as far as we can
# honestly say, which is the least load-bearing of the seven.
SOURCE_TYPES = (
    (("wikidata.org", "wikipedia.org", "dbpedia.org", "britannica.com"), "encyclopedic"),
    (("web.archive.org",), "directory"),
    (("twitter.com", "x.com", "facebook.com", "instagram.com", "linkedin.com",
      "youtube.com", "tiktok.com", "pinterest.com", "threads.net"), "social"),
    (("amazon.com", "amazon.in", "flipkart.com", "ebay.com", "etsy.com",
      "myntra.com", "ajio.com", "walmart.com"), "retailer"),
    (("trustpilot.com", "g2.com", "capterra.com", "yelp.com", "glassdoor.com"), "review"),
    (("reddit.com", "quora.com", "stackexchange.com", "stackoverflow.com"), "forum"),
)


def classify_origin(domain):
    for domains, kind in SOURCE_TYPES:
        if any(domain == d or domain.endswith("." + d) for d in domains):
            return kind
    return "news" if domain.count(".") and _looks_like_press(domain) else "directory"


def _looks_like_press(domain):
    return any(word in domain for word in ("news", "times", "post", "herald", "journal",
                                           "express", "tribune", "gazette", "wire"))


def _get_json(run, url, deadline):
    """Fetch JSON, obeying the third-party host's robots.txt. None on any failure."""
    if not run.allowed(url, deadline):
        return None
    response = run.fetcher.get(url, deadline=deadline)
    if not response.ok:
        return None
    try:
        return json.loads(response.text)
    except (ValueError, TypeError):
        return None


def _norm(value):
    return " ".join((value or "").split()).strip().casefold()


# A year is four digits and will appear in every citation date on an
# encyclopedic page. Containing the string is not asserting the claim, so a
# founding year counts only where a founding word stands next to it.
_FOUNDING = r"(?:founded|established|inception|launched|formed|started|since|est\.)"


def asserts(text, claim):
    """Does this prose assert the claim, or merely contain its characters?

    Substring matching is right for a name or a tagline: an encyclopedic
    sentence states them inside prose, and demanding equality would record every
    correct source as a contradiction. It is wrong for a bare number, which is
    why one publisher's citation dates were briefly recorded as corroborating
    its founding year.
    """
    value = _norm(claim.get("value_normalized"))
    body = _norm(text)
    if not value or not body:
        return False
    if claim.get("kind") == "founded_year":
        return re.search(_FOUNDING + r"\D{0,40}" + re.escape(value), body) is not None
    return value in body


class Probe:
    """Accumulates origins and hits, bounded, deduplicated, in a stable order."""

    def __init__(self, registrable_domain):
        self.brand_domain = registrable_domain
        self.origins = {}
        self.hits = []
        self.frontier = set()
        self.truncated = False

    def note_origin(self, url, source_type=None):
        domain = urls.registrable_domain(urls.host(url) or "")
        if not domain:
            return None
        self.frontier.add(url)
        entry = self.origins.get(domain)
        if entry is None:
            if len(self.origins) >= MAX_ORIGINS:
                self.truncated = True
                return domain
            entry = {"registrable_domain": domain,
                     "source_type": source_type or classify_origin(domain),
                     "urls": [], "syndication_cluster": None,
                     "brand_owned": domain == self.brand_domain}
            self.origins[domain] = entry
        if url not in entry["urls"]:
            entry["urls"].append(url)
        return domain

    def note_hit(self, claim, origin, url, asserted, retrieved_at, matches=None):
        if len(self.hits) >= MAX_HITS:
            self.truncated = True
            return
        asserted = " ".join((asserted or "").split())[:SNIPPET_CHARS]
        self.hits.append({
            "claim_id": claim["id"], "origin": origin, "url": url,
            "asserted_value": asserted,
            "matches_current": asserts(asserted, claim) if matches is None else bool(matches),
            "retrieved_at": retrieved_at,
        })

    def result(self, attempted, method):
        origins = [self.origins[k] for k in sorted(self.origins)]
        return {"attempted": attempted, "method": method,
                "frontier_size": len(self.frontier), "truncated": self.truncated,
                "origins": origins,
                "hits": sorted(self.hits, key=lambda h: (h["claim_id"], h["origin"], h["url"]))}


def _wikipedia(run, probe, claims, name_claim, site_domain, deadline, now):
    """Search by name, then keep only an article that links to this brand's site.

    Name search is a sieve, not an answer: one real query returned both "The
    Indian Express" and "The New Indian Express", which are different companies.
    The outbound-link check is what separates them, and it is why D8 puts
    identity before corroboration -- an ambiguous name poisons every match made
    from it.

    An article that matches by name but does not link here is recorded as an
    origin and nothing more. It is part of the frontier we looked at; it is not
    evidence about this brand.
    """
    query = urllib.parse.urlencode({"q": name_claim["value_normalized"], "limit": MAX_ARTICLES})
    found = _get_json(run, WIKIPEDIA_SEARCH + "?" + query, deadline)
    for page in ((found or {}).get("pages") or [])[:MAX_ARTICLES]:
        if time.monotonic() >= deadline:
            probe.truncated = True
            return
        key = page.get("key")
        if not key:
            continue
        url = WIKIPEDIA_ARTICLE + urllib.parse.quote(key)
        origin = probe.note_origin(url, "encyclopedic")
        if not run.allowed(url, deadline):
            continue
        response = run.fetcher.get(url, deadline=deadline)
        if not response.ok:
            continue
        # Verified against the response itself, not against parsed links: an
        # encyclopedic article carries hundreds of them and its official-website
        # link sits near the end, past the 500-link cap the bundle imposes for
        # its own size. A bound meant for storage silently defeated this check
        # until the article was read by hand.
        if site_domain and site_domain not in (response.text or ""):
            continue                      # a namesake: looked at, not evidence
        text = extract.parse_document(response.text, url)["text"]
        for claim in claims:
            if asserts(text, claim):
                probe.note_hit(claim, origin, url,
                               _sentence_around(text, claim["value_normalized"]), now, matches=True)
            elif claim["kind"] in ("legal_name", "founded_year"):
                # Silence from a verified article is itself an observation: the
                # encyclopedic record of this brand does not carry this claim.
                probe.note_hit(claim, origin, url, "the article does not assert this value", now)


def _sentence_around(text, value, window=200):
    """The prose the value sits in, so a reader can judge the match themselves."""
    position = _norm(text).find(_norm(value))
    if position < 0:
        return ""
    start = max(0, position - window // 2)
    return text[start:start + window]


def _same_as(run, probe, claims, jsonld_sameas, deadline, now):
    """Verify the profiles the site itself points at.

    A sameAs is the brand's own assertion that an off-site page is it. Checking
    them costs one request each and catches a dead or wrong link in the identity
    graph, which no amount of searching would reveal.
    """
    for target in jsonld_sameas[:MAX_SAMEAS]:
        if time.monotonic() >= deadline:
            probe.truncated = True
            return
        if not run.allowed(target, deadline):
            continue
        response = run.fetcher.get(target, deadline=deadline)
        origin = probe.note_origin(target)
        if origin is None:
            continue
        if not response.ok:
            for claim in claims:
                if claim["kind"] == "legal_name":
                    probe.note_hit(claim, origin, target,
                                   "declared sameAs returned HTTP %s" % response.status, now)
            continue
        text = response.text or ""
        for claim in claims:
            if claim["kind"] == "legal_name":
                probe.note_hit(claim, origin, target,
                               claim["value_normalized"] if _norm(claim["value_normalized"]) in _norm(text)
                               else "page does not name the brand", now)


def _wayback(run, probe, claims, origin_url, deadline, now):
    """First-seen date and snapshot count. Coarse by design: see the module note."""
    query = urllib.parse.urlencode({"url": origin_url, "output": "json", "limit": 1,
                                    "fl": "timestamp,digest", "collapse": "digest"})
    rows = _get_json(run, WAYBACK_CDX + "?" + query, deadline)
    if not rows or len(rows) < 2:
        return
    first = rows[1][0] if rows[1] else ""
    url = "https://web.archive.org/web/%s/%s" % (first, origin_url)
    probe.note_origin(url, "directory")
    for claim in claims:
        if claim["kind"] == "founded_year" and len(first) >= 4:
            # Not proof of a founding date: it is the first time anyone archived
            # the site, which bounds the claim from one side and nothing more.
            probe.note_hit(claim, "web.archive.org", url,
                           "first archived snapshot %s" % first[:4], now)


def probe_external(run, evidence, canonical_claims, deadline, now):
    """Run every keyless provider that fits in the budget. Never raises."""
    site = evidence["site"]
    domain = site.get("registrable_domain") or ""
    probe = Probe(domain)
    claims = list(canonical_claims)
    names = [c for c in claims if c["kind"] == "legal_name"]

    same_as = []
    for page in evidence.get("pages") or []:
        for entry in page.get("jsonld") or []:
            for path, value in (entry.get("values") or {}).items():
                if path.split(".")[0] == "sameAs" and value.startswith("http"):
                    if value not in same_as:
                        same_as.append(value)

    if not claims:
        return probe.result(False, "none"), "no canonical claim was promoted, so nothing could be asked"

    if names and time.monotonic() < deadline:
        _wikipedia(run, probe, claims, names[0], domain, deadline, now)
    if same_as and time.monotonic() < deadline:
        _same_as(run, probe, claims, same_as, deadline, now)
    if time.monotonic() < deadline:
        _wayback(run, probe, claims, site.get("resolved_origin") or site["input"], deadline, now)
    if time.monotonic() >= deadline:
        probe.truncated = True
    return probe.result(True, "keyless"), None
