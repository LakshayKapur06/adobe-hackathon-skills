"""Collector pass 1: observe one site and write one schema-valid evidence bundle.

Stages, each under its own budget (../references/budgets.md): robots.txt and
origin resolution, capability probe, soft-404 probe, the agent-facing discovery
files, sitemaps, a stratified crawl, and rendering. The output is
``<workdir>/evidence/evidence.json`` plus the extracted-text sidecars under
``<workdir>/evidence/pages/``, and nothing else.

Observed content is data. Nothing fetched here changes what this module does,
beyond supplying which in-scope URL to request next.

Standard library only.
"""

import argparse
import datetime
import hashlib
import json
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import claims  # noqa: E402
import discover  # noqa: E402
import extract  # noqa: E402
import fetch  # noqa: E402
import render  # noqa: E402
import robots  # noqa: E402
import urls  # noqa: E402

SCHEMA_VERSION = "1.0.0"
BUDGETS = {"global_s": 300, "robots_s": 15, "well_known_s": 5, "crawl_s": 90,
           "render_s": 60, "ua_probe_s": 15, "external_s": 90}

# The identities the user-agent probe sends: (label, robots token, header).
#
# Google-Extended is deliberately absent. It is a robots control token, not a
# crawler: it has no HTTP user agent, so there is nothing to send and nothing
# to learn from sending it. It stays in robots.ai_agents, where it does mean
# something.
#
# The label is what the evidence records, so a rule compares "browser" against
# a named crawler rather than parsing header strings.
UA_PROBE_AGENTS = (
    # Labelled browser-ua, never "browser". It is a client presenting a
    # browser's user-agent string, which is not the same thing and must never
    # be read as one: see the limit recorded in _ua_probe.
    ("browser-ua", "browser-ua",
     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/131.0.0.0 Safari/537.36"),
    ("GPTBot", "GPTBot",
     "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.2; "
     "+https://openai.com/gptbot"),
    ("ClaudeBot", "ClaudeBot",
     "Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)"),
    ("PerplexityBot", "PerplexityBot",
     "Mozilla/5.0 (compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)"),
    ("OAI-SearchBot", "OAI-SearchBot",
     "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; OAI-SearchBot/1.0; "
     "+https://openai.com/searchbot"),
    ("CCBot", "CCBot", "CCBot/2.0 (https://commoncrawl.org/faq/)"),
    ("Googlebot", "Googlebot",
     "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; Googlebot/2.1; "
     "+http://www.google.com/bot.html"),
)
UA_PROBE_MAX = 16                 # the contract's hard bound on ua_probe entries
DEFAULT_MAX_PAGES = 30
EGRESS_PROBE = ("www.wikidata.org", 443)
WELL_KNOWN_PATHS = ("/llms.txt", "/agents.md", "/.well-known/ucp")
SOFT404_MIN_BYTES = 256
MAX_SITEMAP_FILES = 10
LINK_GRAPH_CAP = 5000
HTML_TYPES = ("text/html", "application/xhtml+xml")


def _utc(moment=None):
    moment = moment or datetime.datetime.now(datetime.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


class Run:
    """The mutable state of one collection run."""

    def __init__(self, fetcher):
        self.fetcher = fetcher
        self.errors = []
        self.degradations = []
        self.robots = {}

    def error(self, url, stage, message):
        self.errors.append({"url": url, "stage": stage, "message": message})

    def degrade(self, what, reason, impact):
        self.degradations.append({"what": what, "reason": reason, "impact": impact})

    def robots_for(self, scheme, netloc, deadline=None):
        """Fetch, interpret and cache the robots.txt governing one host."""
        if netloc in self.robots:
            return self.robots[netloc]
        url = "%s://%s/robots.txt" % (scheme, netloc)
        response = self.fetcher.get(url, deadline=deadline)
        mode, parsed, reason, parse_reason = robots.interpret(
            response.status, response.text, response.content_type)
        entry = {"url": url, "status": response.status, "fetched": response.status is not None,
                 "mode": mode, "robots": parsed, "reason": reason, "parse_reason": parse_reason}
        if mode == "unreachable" or parse_reason == "not_plausibly_robots":
            self.error(url, "robots", reason)
        self.robots[netloc] = entry
        if parsed is not None:
            self.fetcher.set_crawl_delay(netloc, parsed.crawl_delay((fetch.ROBOTS_TOKEN,)))
        return entry

    def allowed(self, url, deadline=None):
        normal = urls.normalise(url)
        if normal is None:
            return False
        entry = self.robots_for(normal.split(":", 1)[0], urls.netloc(normal), deadline)
        if entry["mode"] == "unreachable":
            return False
        if entry["robots"] is None:
            return True
        return entry["robots"].allowed(urls.path_and_query(normal), (fetch.ROBOTS_TOKEN,))


def _is_html(response):
    kind = (response.content_type or "").split(";")[0].strip().lower()
    return kind in HTML_TYPES or (not kind and response.text.lstrip()[:1] == "<")


def _parse(response, base):
    """Extract a document, but only from a response that carries page content.

    A non-2xx body is an error document, not the page: an edge block page, a
    not-found notice, a gateway error. Extracting it would record its text as
    the page's own content, and no rule reading text_len, links, headings or
    jsonld could then tell a page we were refused from a page that is thin.
    The status is recorded either way, and it is the observation that matters.
    """
    if not response.ok or not _is_html(response):
        return extract.parse_document("", base)
    return extract.parse_document(response.text, base)


def _probe_egress(disabled):
    if disabled:
        return False, "third-party egress disabled (--no-egress)"
    try:
        socket.create_connection(EGRESS_PROBE, timeout=3).close()
        return True, None
    except OSError as exc:
        return False, "no third-party egress (%s:%d unreachable: %s)" % (EGRESS_PROBE[0], EGRESS_PROBE[1], exc)


def _write_sidecar(pages_dir, text):
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    path = os.path.join(pages_dir, digest + ".txt")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    return "evidence/pages/%s.txt" % digest


def _same_site(run, origin, deadline):
    return lambda u: urls.origin(urls.normalise(u) or u) == origin and run.allowed(u, deadline)


def probe_paths(host):
    """Two paths that cannot exist, derived from the host.

    Derived rather than random because they are recorded in the bundle, and two
    runs over the same site must produce the same bundle (CLAUDE.md rule 10).
    Sixteen hex digits of a hash name no real resource on any site.
    """
    return ["/" + hashlib.sha256(("agent-readiness-audit soft-404 probe %d %s" % (i, host))
                                 .encode("utf-8")).hexdigest()[:16] for i in (1, 2)]


def _soft404_probe(run, origin, deadline):
    """Request the two probe paths. Returns the discovery.soft_404 record.

    ``detected`` means both paths answered 2xx with a substantive body, so the
    site does not return real 404s. ``baseline_text_hash`` is set only when the
    two bodies are also identical: a site that echoes the requested path into
    its not-found page is detected but has no single baseline to dedupe against.
    """
    record = {"detected": False, "baseline_text_hash": None, "probe_paths": []}
    responses = []
    for path in probe_paths(urls.host(origin)):
        url = origin + path
        if not run.allowed(url, deadline):
            continue
        record["probe_paths"].append(path)
        responses.append(run.fetcher.get(url, may_follow=_same_site(run, origin, deadline), deadline=deadline))
    if len(responses) < 2 or not all(r.ok and len(r.body) >= SOFT404_MIN_BYTES for r in responses):
        return record
    record["detected"] = True
    hashes = [extract.parse_document(r.text, r.final_url)["text_hash"] for r in responses]
    if hashes[0] != hashes[1]:
        run.error(origin + "/", "discovery",
                  "soft-404: two paths that cannot exist both returned 2xx with substantive bodies, "
                  "but the bodies differ (the page echoes the requested path), so no single "
                  "baseline exists and URL-level deduplication is not possible")
        return record
    record["baseline_text_hash"] = hashes[0]
    run.error(origin + "/", "discovery",
              "soft-404 baseline %s: two paths that cannot exist both returned status %d "
              "with this identical body" % (hashes[0], responses[0].status))
    return record


def _ua_probe(run, governing, targets, deadline):
    """The same URL under different identities, which is the only way to see it.

    A site that serves an ordinary browser and refuses a named AI crawler looks
    perfectly healthy from any single request. Detecting that requires varying
    the request identity, which is why this is bounded to two URLs: repeated
    across a sample it would stop being a measurement and start being probing.

    **A disclosed limit, and the reason a rule may not overclaim from this.**
    Varying the user-agent header varies one signal. An edge network that
    fingerprints TLS, header set and header order sees the same client whatever
    string it sends, and one real site refused all seven identities including
    browser-ua while serving an actual browser from the same address seconds
    earlier. So this probe can show that a site treats two *named agents*
    differently, which is a finding. It cannot show that a site serves browsers
    and refuses crawlers, because we never present as a browser -- only as a
    client claiming to be one. Any rule reading these entries states the
    comparison it actually made.

    robots.txt is obeyed twice over. The URL must be allowed to *us*, because we
    are the client making the request whatever header we send; and it must be
    allowed to the agent we name, because a group written for GPTBot governs
    anything calling itself GPTBot. An agent disallowed here is not probed, and
    writes no entry -- absent means unprobed, never "served nothing".
    """
    entries = []
    parsed = governing.get("robots")
    for url in targets:
        if not run.allowed(url, deadline):
            continue
        path = urls.path_and_query(url)
        for label, token, header in UA_PROBE_AGENTS:
            if len(entries) >= UA_PROBE_MAX or time.monotonic() >= deadline:
                return entries
            if parsed is not None and not parsed.allowed(path, (token,)):
                continue
            response = run.fetcher.get(url, deadline=deadline, user_agent=header)
            doc = _parse(response, url)
            entries.append({"url": url, "user_agent": label, "status": response.status,
                            "text_len": doc["text_len"], "text_hash": doc["text_hash"]})
    return entries


def _probe_targets(kept, home_key):
    """The home page and one deep page, chosen deterministically.

    The deep page is the longest-text page of the sample: a probe against an
    empty template would compare two nothings and conclude serving is uniform.
    Ties break on URL so two runs over one site choose the same page.
    """
    deep = [(doc["text_len"], key) for key, response, doc in kept
            if key != home_key and response.ok]
    targets = [home_key]
    if deep:
        targets.append(max(deep, key=lambda item: (item[0], item[1]))[1])
    return targets


def _well_known(run, origin, deadline, baseline):
    """The agent-facing discovery files, present or not.

    ``present`` requires a 2xx, a non-empty body, and text that is not the
    soft-404 baseline. A site that serves one shell at every path answers
    /llms.txt with 200 and that shell; without the third condition, a file that
    does not exist would be recorded as present.
    """
    entries = []
    for path in WELL_KNOWN_PATHS:
        url = origin + path
        if not run.allowed(url, deadline):
            continue                      # not probed: no entry, by contract
        response = run.fetcher.get(url, may_follow=_same_site(run, origin, deadline), deadline=deadline)
        if response.status in (401, 403):
            # Probed, and refused. No answer was obtained, which is what the
            # contract's missing entry means; a 404 is a real absence and keeps
            # its entry. Recording present: false here would assert that a file
            # we were never allowed to look at does not exist.
            continue
        present = bool(response.ok and response.body.strip())
        if present and baseline and \
                extract.parse_document(response.text, response.final_url)["text_hash"] == baseline:
            present = False
        entries.append({"path": path, "status": response.status, "present": present,
                        "content_type": response.content_type})
    return entries


def _sitemaps(run, origin, governing, frontier, deadline):
    queue = list(governing["robots"].sitemaps) if governing["robots"] is not None else []
    if not queue:
        queue = [origin + "/sitemap.xml"]
    records, seen = [], set()
    while queue and len(seen) < MAX_SITEMAP_FILES and time.monotonic() < deadline:
        url = queue.pop(0)
        if url in seen or not run.allowed(url, deadline):
            continue
        seen.add(url)
        response = run.fetcher.get(url, deadline=deadline)
        kind, locations, ratio, ok = None, [], None, False
        if response.ok:
            kind, locations, ratio, ok = discover.parse_sitemap(response.body, response.content_type, url)
        records.append({"url": url, "status": response.status,
                        "url_count": len(locations) if ok else None,
                        "lastmod_present_ratio": ratio, "parse_ok": ok})
        if kind == "index":
            queue.extend(locations)
        elif kind == "urlset":
            for location in locations:
                frontier.add(location, "sitemap")
    return records


def _alias_of(key, response, doc, kept):
    """An earlier kept page that this one merely repeats, or None.

    Used only when rendering is unavailable, and only when two conditions hold
    together: identical extracted text, and a canonical link between the two
    URLs. With rendering available, raw identity is never grounds for skipping
    a page, because a client-rendered site's shell is identical at every route
    and often carries one fixed canonical; the rendered-text comparison decides
    instead.
    """
    if not response.ok:
        return None
    mine = {key, doc["canonical"]} - {None}
    for other_key, other_response, other_doc in kept:
        if not other_response.ok or other_doc["text_hash"] != doc["text_hash"]:
            continue
        theirs = {other_key, other_doc["canonical"]} - {None}
        if doc["canonical"] in theirs or other_doc["canonical"] in mine:
            return other_key
    return None


def collect(url, workdir, max_pages=DEFAULT_MAX_PAGES, no_render=False, no_egress=False,
            renderer=None, fetcher=None, budgets=None):
    """Observe ``url`` and write the evidence bundle under ``workdir``. Returns it."""
    budgets = dict(BUDGETS, **(budgets or {}))
    run = Run(fetcher or fetch.Fetcher())
    started = datetime.datetime.now(datetime.timezone.utc)
    evidence_dir = os.path.join(workdir, "evidence")
    pages_dir = os.path.join(evidence_dir, "pages")
    os.makedirs(pages_dir, exist_ok=True)
    for stale in os.listdir(pages_dir):
        if stale.endswith(".txt"):
            os.remove(os.path.join(pages_dir, stale))

    start_url = urls.normalise(url if "://" in url else "https://" + url)
    if start_url is None:
        raise ValueError("not an http(s) URL: %r" % url)
    scheme, input_netloc = start_url.split(":", 1)[0], urls.netloc(start_url)
    robots_deadline = time.monotonic() + budgets["robots_s"]

    # -- 1. robots.txt first, then the origin ----------------------------------
    resolved_origin, home, governing, stop = None, None, None, None
    refused_home = None
    stop_impact = "no first-party pages were fetched; every page-level rule is not assessed"
    entry = run.robots_for(scheme, input_netloc, robots_deadline)
    home_url = urls.origin(start_url) + "/"
    if entry["mode"] == "unreachable":
        governing, stop = entry, entry["reason"]
    elif not run.allowed(home_url):
        governing, stop = entry, "robots.txt disallows the site root for this audit's user agent"
    else:
        home = run.fetcher.get(home_url, may_follow=lambda u: run.allowed(u))
        if home.status is None:
            governing, stop = entry, "home page unreachable: %s" % home.error
            run.error(home_url, "fetch", home.error or "no response")
            home = None
        else:
            final = urls.normalise(home.final_url) or home_url
            resolved_origin = urls.origin(final)
            governing = run.robots_for(final.split(":", 1)[0], urls.netloc(final))
            if governing["mode"] == "unreachable":
                stop, home = governing["reason"], None
            elif home.status in fetch.REDIRECT_STATUSES:
                stop, home = "the home page redirects to a URL robots.txt disallows", None
            elif not home.ok:
                # A refusal at the front door. The crawl cannot proceed, and
                # the error document must not be mistaken for the site: an
                # edge block page extracted as content reads exactly like a
                # thin, link-less, markup-free home page.
                stop = "the home page returned HTTP %d, so no page content was observed" % home.status
                stop_impact = ("the home page is recorded with its status and an empty body; no page "
                               "content was observed, and every content-level rule is not assessed")
                run.error(home_url, "fetch", "the home page returned HTTP %d" % home.status)
                refused_home, home = home, None
    if stop:
        run.degrade("crawl", stop, stop_impact)

    # -- 2. capabilities ---------------------------------------------------------
    if no_render:
        renderer, render_note = None, "rendering disabled (--no-render)"
    elif renderer is None:
        binary, note = render.find_browser()
        renderer = render.Renderer(binary, fetch.USER_AGENT) if binary else None
        render_note = note
        if renderer is not None and not renderer.probe():
            render_note, renderer = renderer.unavailable_reason, None
    else:
        render_note = getattr(renderer, "unavailable_reason", None)
        if not getattr(renderer, "available", False):
            renderer = None
    js_render = renderer is not None
    egress, egress_note = _probe_egress(no_egress)
    if not js_render:
        run.degrade("render", render_note or "no browser available",
                    "raw-versus-rendered comparisons are not assessed")
    run.degrade("external",
                egress_note or "off-site corroboration is collector pass 2, not yet built",
                "corroboration rules are not assessed")
    # Stages not yet built leave their arrays empty. Say so, so that an empty
    # array can never be read as a measurement that found nothing.
    frontier = discover.Frontier(urls.netloc(resolved_origin) if resolved_origin else input_netloc)
    kept, collapsed_shell, aliases, redirected, crawl_errors = [], 0, [], [], 0
    well_known, sitemap_records, render_results, ua_probe = [], [], {}, []
    soft404 = {"detected": False, "baseline_text_hash": None, "probe_paths": []}
    baseline = None

    if home is not None:
        origin = resolved_origin
        home_key = frontier.add(home.final_url, "nav") or urls.normalise(home.final_url)
        # -- 3. soft-404, agent-facing files, sitemaps -------------------------------
        soft404 = _soft404_probe(run, origin, robots_deadline + budgets["well_known_s"])
        baseline = soft404["baseline_text_hash"]
        well_known = _well_known(run, origin, time.monotonic() + budgets["well_known_s"], baseline)
        sitemap_records = _sitemaps(run, origin, governing, frontier, robots_deadline)
        home_doc = _parse(home, home.final_url)
        for link in home_doc["resolved_links"]:
            frontier.add(link, "nav")
        if js_render:
            # The shell of a client-rendered site carries few links; the
            # rendered home page is where its navigation actually is.
            render_results[home_key] = renderer.render(home.final_url)
            if render_results[home_key][0]:
                for link in extract.parse_document(render_results[home_key][0], home.final_url)["resolved_links"]:
                    frontier.add(link, "nav")

        # -- 4. stratified crawl -------------------------------------------------------
        # Pages are keyed on their final URL after redirects. A URL that is
        # itself the final form of a page already held is never fetched, and a
        # redirect hop onto one is never followed.
        held = {home_key}
        sampler = discover.Sampler(frontier)
        sampler.mark(home_key)
        kept.append((home_key, home, home_doc))
        crawl_deadline = time.monotonic() + budgets["crawl_s"]
        in_scope = (frontier.origin, frontier.twin)

        def follow(hop):
            normal = urls.normalise(hop)
            return (normal is not None and urls.netloc(normal) in in_scope and normal not in held
                    and run.allowed(hop, crawl_deadline))

        while len(kept) < max_pages and time.monotonic() < crawl_deadline:
            target = sampler.next()
            if target is None:
                break
            if target in held:
                redirected.append((target, target))
                continue
            if not run.allowed(target, crawl_deadline):
                continue
            response = run.fetcher.get(target, deadline=crawl_deadline, may_follow=follow)
            if response.status is None:
                if "budget" not in (response.error or ""):
                    crawl_errors += 1
                    run.error(target, "fetch", response.error or "no response")
                continue
            final = urls.normalise(response.final_url) or target
            if final in held:
                redirected.append((target, final))
                continue
            if not response.ok and response.status not in fetch.REDIRECT_STATUSES:
                # Every refusal counts, not only a 5xx. A run that is answered
                # 403 at every door must never report a clean crawl.
                crawl_errors += 1
                run.error(target, "fetch", "returned HTTP %d" % response.status)
            doc = _parse(response, response.final_url)
            if not js_render and baseline and response.ok and doc["text_hash"] == baseline:
                # Rendering is unavailable, so this copy of the shell adds no
                # distinct content: it is not a page and not a stratum member.
                collapsed_shell += 1
                continue
            alias = None if js_render else _alias_of(target, response, doc, kept)
            if alias:
                aliases.append((target, alias))
                continue
            for link in doc["resolved_links"]:
                frontier.add(link, "linkgraph")
            kept.append((target, response, doc))
            held.add(final)
        if time.monotonic() >= crawl_deadline and len(kept) < max_pages and sampler.next() is not None:
            run.degrade("crawl", "the %ss crawl budget ran out after %d pages" % (budgets["crawl_s"], len(kept)),
                        "fewer pages were sampled than requested; every finding states its denominator")
        if collapsed_shell:
            run.error(origin + "/", "discovery",
                      "collapsed %d of %d fetched URLs whose server response matched the soft-404 "
                      "baseline %s; with rendering unavailable they contribute no distinct content "
                      "and are not counted in crawl.fetched or any stratum"
                      % (collapsed_shell, collapsed_shell + len(kept), baseline))
        if aliases:
            run.error(origin + "/", "discovery",
                      "collapsed %d URLs that are the same document as an earlier page (identical "
                      "extracted text and a canonical link between the two): %s"
                      % (len(aliases), "; ".join("%s = %s" % pair for pair in aliases[:5])))
        if redirected:
            run.error(origin + "/", "discovery",
                      "collapsed %d URLs whose final URL after redirects was already held: %s"
                      % (len(redirected), "; ".join("%s -> %s" % pair for pair in redirected[:5])))

        # -- 5. rendering ----------------------------------------------------------
        if js_render:
            # One page of every type first, then the rest. The budget cannot
            # cover every page of a large sample, so what it does cover is
            # chosen rather than whatever the crawl happened to reach first:
            # a raw-versus-rendered baseline is worth most when every template
            # has one, and worth least when nine pages of one template have it.
            pending = [(key, doc) for key, response, doc in kept
                       if key not in render_results and response.ok and _is_html(response)]
            first_of_type, rest, seen = [], [], set()
            for key, _ in pending:
                bucket = first_of_type if frontier.kind.get(key) not in seen else rest
                seen.add(frontier.kind.get(key))
                bucket.append(key)
            render_results.update(render.render_many(renderer, first_of_type + rest,
                                                    budgets["render_s"]))


    if refused_home is not None:
        # Recorded, not crawled. The refusal is a fact about the site, and
        # pages[] with a status and an empty body is where a rule can read it
        # as a typed field instead of parsing a degradation message. It enters
        # the frontier too: we did discover this URL, and a bundle reporting
        # more pages fetched than discovered describes no possible crawl.
        key = frontier.add(refused_home.final_url, "nav") or urls.normalise(refused_home.final_url) or home_url
        kept.append((key, refused_home, _parse(refused_home, refused_home.final_url)))
        crawl_errors += 1      # one URL fetched, one refusal: never a clean crawl

    # -- 5b. user-agent-conditional serving ----------------------------------------
    # Outside the crawl block on purpose. A home page that refused us is the
    # single most informative case this probe has: "they served a browser and
    # refused us" is a finding, and it is unreachable from a crawl that stopped.
    if governing is not None and governing["mode"] != "unreachable" and kept:
        ua_probe = _ua_probe(run, governing, _probe_targets(kept, kept[0][0]),
                             time.monotonic() + budgets["ua_probe_s"])
    if not ua_probe:
        run.degrade("ua-probe", "no URL could be probed under any user agent",
                    "ua_probe is empty because nothing was probed, not because serving is uniform")

    # -- 6. assemble pages -------------------------------------------------------
    pages, first_with_text, claim_notes = [], {}, []
    render_failed = render_skipped = 0
    render_duplicates = []
    for key, response, doc in kept:
        rendered = {"available": False, "text_len": None, "text_hash": None, "text_path": None,
                    "headings": [], "delta_ratio": None}
        render_ms, rendered_text = None, None
        if js_render and response.ok and _is_html(response):
            # Neither a non-2xx page nor a non-HTML resource is rendered. The
            # browser would assemble the error document, or its own viewer for
            # the XML — a sitemap rendered this way yielded 762,313 characters
            # of tree view against an empty raw body, a delta_ratio of 1.0, and
            # "all of this content is JavaScript-only" is both the strongest
            # claim the render mechanism can make and entirely an artifact.
            html, failure, render_ms = render_results.get(key, (None, "not reached within the render budget", None))
            if html:
                rdoc = extract.parse_document(html, response.final_url)
                rendered_text = rdoc["text"]
                if rdoc["text_hash"] in first_with_text:
                    render_duplicates.append((key, first_with_text[rdoc["text_hash"]]))
                    continue
                first_with_text[rdoc["text_hash"]] = key
                delta = None
                if rdoc["text_len"]:
                    delta = round(max(0.0, (rdoc["text_len"] - doc["text_len"]) / rdoc["text_len"]), 3)
                rendered = {"available": True, "text_len": rdoc["text_len"], "text_hash": rdoc["text_hash"],
                            "text_path": _write_sidecar(pages_dir, rdoc["text"]),
                            "headings": rdoc["headings"], "delta_ratio": delta}
            elif failure and "budget" in failure:
                render_skipped += 1
                run.error(key, "render", failure)
            else:
                render_failed += 1
                run.error(key, "render", failure or "the browser returned no DOM")
        pages.append(_page_evidence(key, response, doc, rendered, render_ms, pages_dir, run))
        page = pages[-1]
        if page["status"] and 200 <= page["status"] <= 299:
            # Candidates come from the page as recorded: the rendered text when
            # there is any, because a client-rendered site states its claims
            # only after rendering, and the raw text otherwise.
            claims.from_jsonld(page["jsonld"], page["url"], claim_notes)
            claims.from_headings(doc["headings"], page["page_type"], page["url"], claim_notes)
            claims.from_text(rendered_text or doc["text"], page["url"], claim_notes)

    if render_duplicates:
        run.error((resolved_origin or "") + "/", "discovery",
                  "collapsed %d fetched pages whose rendered text duplicated an earlier page: %s"
                  % (len(render_duplicates), "; ".join("%s = %s" % pair for pair in render_duplicates[:5])))
    if render_failed:
        run.degrade("render", "%d of %d pages failed to render (browser error or timeout)" % (render_failed, len(kept)),
                    "those pages are fetch-only and their raw-versus-rendered comparison is not assessed")
    if render_skipped:
        run.degrade("render", "%d pages were not reached within the %ss render budget" % (render_skipped, budgets["render_s"]),
                    "those pages are fetch-only and their raw-versus-rendered comparison is not assessed")
    html_pages = [p for p in pages if p["status"] and 200 <= p["status"] <= 299]
    shells = [p for p in html_pages if p["raw"]["text_hash"] == baseline] if baseline else []
    if shells and len(shells) == len(html_pages) and not js_render:
        # Every page we hold is the document a path that cannot exist returns,
        # and there is no browser to look past it. The count of collapsed
        # copies is not what makes this true: a shell carrying no links
        # discovers nothing to collapse, so the degenerate case arrives as one
        # page rather than many, and it is the worst case, not the mildest.
        #
        # Only without a browser is this a degradation. With one, raw text of
        # zero against rendered text of thousands is not something we failed to
        # assess -- it is the observation itself, and a rule reads it.
        total = collapsed_shell + len(html_pages)
        run.degrade("page-content",
                    "every one of %d sampled URL%s returned the same server response as a path that "
                    "cannot exist, and rendering is unavailable"
                    % (total, "" if total == 1 else "s"),
                    "no page-level content exists in the server response at all: nothing on this site "
                    "is readable without executing JavaScript, and no page-level rule can be assessed")

    claim_candidates, dropped = claims.aggregate(claim_notes)
    if dropped:
        run.error((resolved_origin or "") + "/", "extract",
                  "claim_candidates truncated to %d of %d distinct candidates"
                  % (len(claim_candidates), len(claim_candidates) + dropped))
    if not claim_candidates:
        run.degrade("claims", "no claim candidate was extracted from any sampled page",
                    "claim_candidates is empty because nothing matched, not because the site "
                    "makes no claims; identity and corroboration rules are not assessed")

    evidence = {
        "schema_version": SCHEMA_VERSION,
        "site": {
            "input": url,
            "resolved_origin": resolved_origin,
            "registrable_domain": urls.registrable_domain(urls.host(resolved_origin or start_url)),
            "detected_locales": list(dict.fromkeys(p["lang"] for p in pages if p["lang"])),
        },
        "run_context": {
            "started_at": _utc(started),
            "finished_at": _utc(),
            "capabilities": {"js_render": js_render, "egress": egress,
                             "renderer": renderer.label if js_render else None},
            "budgets": {k: budgets[k] for k in ("global_s", "crawl_s", "render_s", "external_s")},
            "degradations": run.degradations,
            "corroboration": {"method": "none", "provider_unavailable": []},
        },
        "robots": robots.evidence_block(governing["url"], governing["status"], governing["fetched"],
                                        governing["mode"], governing["robots"], governing["parse_reason"]),
        "sitemaps": sitemap_records,
        "crawl": {
            "discovered": len(frontier),
            "fetched": len(pages),
            "blocked_by_robots": sum(1 for u in frontier.order if not run.allowed(u)),
            "errors": crawl_errors,
            "sampling": {
                "strategy": "stratified:" + ("+".join(s for s in ("sitemap", "nav", "linkgraph")
                                                      if s in frontier.sources) or "none"),
                "strata": _strata(frontier, pages),
            },
        },
        "discovery": {
            "soft_404": soft404,
            "collapsed_duplicate_text": collapsed_shell + len(aliases) + len(render_duplicates),
            "collapsed_redirect_target": len(redirected),
        },
        "pages": pages,
        "link_graph": _link_graph(frontier, kept, pages, run),
        "claim_candidates": claim_candidates,
        "canonical_claims": [],
        "external": {"attempted": False, "method": "none", "frontier_size": 0, "truncated": False,
                     "origins": [], "hits": []},
        "ua_probe": ua_probe,
        "well_known": well_known,
        "errors": run.errors,
    }
    with open(os.path.join(evidence_dir, "evidence.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(evidence, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return evidence


def _page_evidence(key, response, doc, rendered, render_ms, pages_dir, run):
    entries, truncation = extract.jsonld_entries(doc["jsonld_scripts"], doc["text"])
    for field, kept, total in doc["truncations"] + ([truncation] if truncation else []):
        run.error(key, "extract", "%s truncated to %d of %d on this page" % (field, kept, total))
    url_type, url_confidence = discover.classify_url(key)
    page_type, confidence = discover.refine(url_type, url_confidence, [e["type"] for e in entries])
    modified, published = extract.schema_dates(entries)
    obstructions = list(doc["obstructions"])
    if any(e["values"].get("isAccessibleForFree", "").lower() == "false" for e in entries) and \
            not any(o["kind"] == "paywall" for o in obstructions):
        obstructions.append({"kind": "paywall", "evidence": "JSON-LD isAccessibleForFree is false"})
    final = urls.normalise(response.final_url) or key
    headers = response.headers
    return {
        "url": key,
        "final_url": final,
        "status": response.status,
        "redirect_chain": response.redirect_chain,
        "content_type": response.content_type,
        "fetched_at": response.fetched_at,
        "headers": {"x_robots_tag": headers.get("x-robots-tag"),
                    "last_modified": headers.get("last-modified"),
                    "cache_control": headers.get("cache-control")},
        "meta_robots": doc["meta_robots"],
        "canonical": doc["canonical"],
        "canonical_self": doc["canonical"] is not None and doc["canonical"] == final,
        "lang": doc["lang"],
        "hreflang": doc["hreflang"],
        "page_type": page_type,
        "page_type_confidence": confidence,
        "raw": {"bytes": len(response.body), "text_len": doc["text_len"], "text_hash": doc["text_hash"],
                "text_path": _write_sidecar(pages_dir, doc["text"]), "headings": doc["headings"],
                "anchors": doc["anchors"], "links": doc["links"], "images": doc["images"],
                "tables": doc["tables"], "iframes": doc["iframes"], "forms": doc["forms"]},
        "rendered": rendered,
        "jsonld": entries,
        "microdata_or_rdfa": doc["microdata_or_rdfa"],
        "text": {"visible_excerpt": extract.excerpt(doc["text"]), "word_count": doc["word_count"],
                 "boilerplate_ratio": doc["boilerplate_ratio"],
                 "longest_block_words": doc["longest_block_words"],
                 "heading_density_per_1k": doc["heading_density_per_1k"]},
        "dates": {"visible_dates": extract.visible_dates(doc["text"]),
                  "schema_date_modified": modified, "schema_date_published": published,
                  "http_last_modified": headers.get("last-modified")},
        "obstructions": obstructions,
        "timing": {"ttfb_ms": response.ttfb_ms, "fetch_ms": response.fetch_ms, "render_ms": render_ms},
        "provenance": {"layer": "first_party", "method": "render" if rendered["available"] else "fetch"},
    }


def _strata(frontier, pages):
    discovered, sampled = {}, {}
    for url in frontier.order:
        discovered[frontier.kind[url]] = discovered.get(frontier.kind[url], 0) + 1
    for page in pages:
        kind = frontier.kind.get(page["url"], discover.classify_url(page["url"])[0])
        sampled[kind] = sampled.get(kind, 0) + 1
    return [{"page_type": t, "discovered": discovered.get(t, 0), "sampled": sampled.get(t, 0)}
            for t in discover.PAGE_TYPES if discovered.get(t) or sampled.get(t)]


def _link_graph(frontier, kept, pages, run):
    page_urls = [p["url"] for p in pages]
    docs = {key: doc for key, _, doc in kept}
    edges, seen, total = [], set(), 0
    for source in page_urls:
        for link in docs[source]["resolved_links"]:
            target = frontier.add(link, "linkgraph")
            if target is None or target == source or (source, target) in seen:
                continue
            seen.add((source, target))
            total += 1
            if len(edges) < LINK_GRAPH_CAP:
                edges.append([source, target])
    if total > LINK_GRAPH_CAP:
        run.error(page_urls[0], "extract", "link_graph.edges truncated to %d of %d" % (LINK_GRAPH_CAP, total))
    inbound = {t for _, t in edges}
    orphans = [u for u in page_urls[1:] if u not in inbound]
    depth = None
    if page_urls:
        adjacency = {}
        for s, t in edges:
            adjacency.setdefault(s, []).append(t)
        reached, layer, level = {page_urls[0]: 0}, {page_urls[0]}, 0
        members = set(page_urls)
        while layer:
            level += 1
            nxt = {t for node in layer for t in adjacency.get(node, []) if t in members and t not in reached}
            for t in nxt:
                reached[t] = level
            layer = nxt
        depth = max(reached.values())
    return {"edges": edges, "orphans": orphans, "max_depth_from_home": depth}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Collect a website's evidence bundle (read-only).")
    parser.add_argument("--url", required=True)
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--no-render", action="store_true")
    parser.add_argument("--no-egress", action="store_true")
    args = parser.parse_args(argv)
    collect(args.url, args.workdir, max_pages=args.max_pages,
            no_render=args.no_render, no_egress=args.no_egress)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
