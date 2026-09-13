"""access-and-indexability: the nine rules in ../references/rules.md, as code.

Reads evidence/evidence.json and nothing else, and writes one findings file
holding ``findings``, ``not_assessed`` and ``checks_passed``. Every rule ends in
exactly one of three outcomes: it fires, it passes, or it could not be assessed.
An unmade observation is never reported as a pass.

Each function below implements the rule block of the same id. The block is the
specification: its thresholds, controls and impact derivations are written
there with their reasons, and are repeated here only as code. ``severity`` and
``suggested_action.priority`` are never set; the orchestrator derives them.

Standard library only. No imports from any other skill.
"""

import argparse
import json
import os
import re
from urllib.parse import urlsplit

SKILL = "access-and-indexability"
SUPPORTED_SCHEMA_MAJOR = "1"

RETRIEVAL_AGENTS = ("OAI-SearchBot", "PerplexityBot", "Claude-SearchBot", "Googlebot")
TRAINING_AGENTS = ("GPTBot", "ClaudeBot", "CCBot", "Google-Extended")
SERVES = {"OAI-SearchBot": "ChatGPT search", "PerplexityBot": "Perplexity",
          "Claude-SearchBot": "Claude's search results", "Googlebot": "Google Search, including AI Overviews"}
PRIMARY_TYPES = ("home", "product", "article", "doc", "about")

# X-Robots-Tag scopes that count, per rule (lower-cased product tokens).
INDEX_SCOPES = ("googlebot", "oai-searchbot", "perplexitybot", "claude-searchbot")
SNIPPET_SCOPES = ("googlebot",)
NOINDEX_TOKENS = ("noindex", "none")
NOSNIPPET_TOKENS = ("nosnippet", "max-snippet:0")
# Robots directives that legitimately contain a colon, so that "max-snippet:0"
# is never mistaken for a user-agent scope named "max-snippet".
COLON_DIRECTIVES = ("max-snippet", "max-image-preview", "max-video-preview", "unavailable_after")

UA_PROBED_AGENTS = ("GPTBot", "ClaudeBot", "PerplexityBot", "OAI-SearchBot", "CCBot")
UA_REFUSALS = (401, 403, 404, 406, 410, 451)
CLIENT_REFUSALS = (401, 403, 429)
ROOT_ALIASES = ("/", "/index.html", "/index.php", "/home", "/default.aspx")


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------

def is_2xx(status):
    return isinstance(status, int) and 200 <= status <= 299


def is_error(status):
    return status in (404, 410) or (isinstance(status, int) and 500 <= status <= 599)


def path_of(url):
    parts = urlsplit(url or "")
    return (parts.path or "/") + ("?" + parts.query if parts.query else "")


def host_of(url):
    return (urlsplit(url or "").hostname or "").lower()


def product_token(value):
    match = re.match(r"\s*([A-Za-z0-9_-]+)", value or "")
    return match.group(1).lower() if match else ""


def pct(part, whole):
    return "%d%%" % round(100.0 * part / whole) if whole else "0%"


def plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


class Context:
    """The bundle plus the small derived views several rules share."""

    def __init__(self, evidence):
        self.e = evidence
        self.robots = evidence["robots"]
        self.origin = evidence["site"]["resolved_origin"] or evidence["site"]["input"]
        self.started_at = evidence["run_context"]["started_at"]
        self.pages = evidence["pages"]
        self.ok_pages = [p for p in self.pages if is_2xx(p["status"])]
        self.robots_url = self.robots["url"] or self.origin.rstrip("/") + "/robots.txt"

    def page_ref(self, page, observation):
        return {"url": page["url"], "observation": observation,
                "layer": page["provenance"]["layer"], "method": page["provenance"]["method"],
                "retrieved_at": page["fetched_at"]}

    def fetch_ref(self, url, observation, retrieved_at=None):
        return {"url": url, "observation": observation, "layer": "first_party",
                "method": "fetch", "retrieved_at": retrieved_at or self.started_at}

    def fetched_at_for(self, url):
        for page in self.pages:
            if url in (page["url"], page["final_url"]):
                return page["fetched_at"]
        return self.started_at


def finding(rule_id, title, evidence, action, *, status, confidence, impact, scope, refs,
            controls, exceptions, symptom=("invisible",)):
    return {
        "id": "F-001",
        "title": title,
        "evidence": evidence,
        "suggested_action": action,
        "skill": SKILL,
        "rule_id": rule_id,
        "status": status,
        "category": "discoverability",
        "symptom": list(symptom),
        "confidence": confidence,
        "impact": impact,
        "scope": scope,
        "evidence_refs": refs,
        "false_positive_controls_applied": list(controls),
        "exceptions_checked": list(exceptions),
    }


def action(summary, what, where, why, how, mechanism, success, effort):
    return {"summary": summary, "what": what, "where": where, "why": why, "how": how,
            "mechanism": mechanism, "success_criteria": success, "effort": effort}


# --------------------------------------------------------------------------
# robots.txt matching, RFC 9309, for counting the sampled pages a rule covers
# --------------------------------------------------------------------------

def named_groups(groups, agent):
    wanted = agent.lower()
    return [g for g in groups if product_token(g["user_agent"]) == wanted]


def governing_groups(groups, agent):
    named = named_groups(groups, agent)
    if named:
        return named
    return [g for g in groups if g["user_agent"].strip() == "*"]


def _pattern(rule):
    body = re.escape(rule).replace(r"\*", ".*")
    if body.endswith(r"\$"):
        body = body[:-2] + "$"
    return re.compile(body)


def path_allowed(groups, path):
    """Longest match wins; on a tie, allow wins (RFC 9309 2.2.2)."""
    best_len, allowed = -1, True
    for group in groups:
        for verdict, rules in ((True, group["allow"]), (False, group["disallow"])):
            for rule in rules:
                if not rule:
                    continue
                if _pattern(rule).match(path):
                    length = len(rule)
                    if length > best_len or (length == best_len and verdict):
                        best_len, allowed = length, verdict
    return allowed


def has_content_allows(groups):
    return any(rule not in ("", "/") for g in groups for rule in g["allow"])


def robots_not_ok(ctx, rule_id):
    """The shared outcome for rules that need a parsed robots.txt."""
    reason = ctx.robots["parse_reason"]
    if reason in ("absent_4xx", "not_plausibly_robots"):
        return "passed", {"rule_id": rule_id, "summary":
                          "robots.txt imposes no restrictions (parse_reason %s), so no crawler is "
                          "excluded by it" % reason}
    return "not_assessed", {"rule_id": rule_id, "reason":
                            "robots.txt was not obtained (parse_reason %s), so every agent is recorded "
                            "as disallowed without any rule having been read" % reason,
                            "enable_hint": "re-run once robots.txt answers 200 or 404; ACC-002 reports "
                                           "the error response itself"}


def exclusion_scope(ctx, agents):
    """The sampled pages whose path is disallowed to at least one of ``agents``."""
    groups = ctx.robots["groups"]
    covered = [p for p in ctx.pages
               if any(not path_allowed(governing_groups(groups, a), path_of(p["final_url"])) for a in agents)]
    return {"pages_affected": len(covered), "pages_examined": len(ctx.pages),
            "page_types": sorted({p["page_type"] for p in covered})}


def served(agents):
    return ", ".join(SERVES[a] for a in agents)


def quote_group(groups):
    lines = []
    for g in groups:
        rules = ["Disallow: %s" % r for r in g["disallow"]] + ["Allow: %s" % r for r in g["allow"]]
        shown = rules[:4] + (["(%d more)" % (len(rules) - 4)] if len(rules) > 4 else [])
        lines.append("User-agent: %s / %s" % (g["user_agent"], "; ".join(shown) or "no rules"))
    return " | ".join(lines)


# --------------------------------------------------------------------------
# the rules
# --------------------------------------------------------------------------

def acc_001(ctx, out):
    robots = ctx.robots
    if not (robots["parse_ok"] and robots["parse_reason"] == "ok"):
        kind, entry = robots_not_ok(ctx, "ACC-001")
        out[kind].append(entry)
        return
    groups = robots["groups"]
    verdicts = robots["ai_agents"]
    collateral = [a for a in RETRIEVAL_AGENTS
                  if verdicts[a] == "disallowed" and not named_groups(groups, a)]
    if not collateral:
        out["passed"].append({"rule_id": "ACC-001", "summary":
                              "No answer-time retrieval crawler (%s) is shut out by the * group in "
                              "robots.txt" % ", ".join(RETRIEVAL_AGENTS)})
        return
    star = [g for g in groups if g["user_agent"].strip() == "*"]
    swept_training = [a for a in TRAINING_AGENTS
                      if verdicts[a] == "disallowed" and not named_groups(groups, a)]
    scope = exclusion_scope(ctx, collateral)
    evidence = ("robots.txt disallows / to %s through the * group, and no group names %s, so %s cannot "
                "retrieve the site. %s of %s sampled pages are disallowed to them. The governing group reads: %s."
                % (", ".join(collateral), "them" if len(collateral) > 1 else "it", served(collateral),
                   scope["pages_affected"], scope["pages_examined"], quote_group(star)))
    if swept_training:
        evidence += " Training agents swept up by the same group: %s." % ", ".join(swept_training)
    out["findings"].append(finding(
        "ACC-001", "Answer-time retrieval crawler shut out by the * group in robots.txt", evidence,
        action("Add a robots.txt group naming each excluded search crawler so the * rule stops applying to it.",
               "Add a group naming %s that allows the content paths, placed so it overrides the * group."
               % ", ".join(collateral),
               "The robots.txt at %s." % ctx.robots_url,
               "Under RFC 9309 a group naming a crawler replaces the * group entirely for it, so the crawler "
               "is readmitted without loosening the rule for anything else.",
               "For each crawler, add `User-agent: %s` followed by `Allow: /` and the site's existing "
               "private-path Disallow lines. Training agents such as GPTBot can stay under whatever policy "
               "the owner chooses, since they do not serve answer-time retrieval." % collateral[0],
               "Admission to the retrieval index of each assistant named.",
               "Re-fetching robots.txt yields `allowed` for %s, with the owner's private paths still disallowed."
               % ", ".join(collateral), "low"),
        status="found", confidence="high",
        impact={"blocking": True, "breadth": "section" if has_content_allows(star) else "site",
                "content_importance": "primary"},
        scope=scope,
        refs=[ctx.fetch_ref(ctx.robots_url, "verdict disallowed at / for %s, governed by the * group"
                            % ", ".join(collateral))],
        controls=["parse_reason is ok, so the verdict comes from a parsed file and not from an outage",
                  "crawlers excluded by a group naming them are left to ACC-008",
                  "RFC 9309 group selection: a group naming a crawler always overrides *"],
        exceptions=["deliberate named-group exclusion: none of the reported crawlers is named in any group"]))


def acc_002(ctx, out):
    robots = ctx.robots
    reason = robots["parse_reason"]
    if not robots["fetched"] or robots["status"] is None:
        out["not_assessed"].append({"rule_id": "ACC-002", "reason":
                                    "robots.txt produced no HTTP response (parse_reason %s), which cannot "
                                    "separate a robots.txt defect from a host or network failure" % reason,
                                    "enable_hint": "re-run when the host answers; a timeout or DNS failure "
                                                   "is not evidence about robots.txt"})
        return
    if reason not in ("server_error", "rate_limited"):
        out["passed"].append({"rule_id": "ACC-002", "summary":
                              "robots.txt answered HTTP %d, which lets compliant crawlers proceed"
                              % robots["status"]})
        return
    status = robots["status"]
    out["findings"].append(finding(
        "ACC-002", "robots.txt answered with a %s, so compliant crawlers fetch nothing"
        % ("rate limit" if reason == "rate_limited" else "server error"),
        "robots.txt at %s answered HTTP %d once, as the first request of the audit. RFC 9309 tells a "
        "crawler that cannot obtain robots.txt because of a server error to assume complete disallow; "
        "Google pauses crawling for 12 hours and then works from its last good copy. One observation "
        "cannot show whether the error persists." % (ctx.robots_url, status),
        action("Make /robots.txt answer 200 with the intended policy, or 404 if there is none.",
               "Serve robots.txt with a 200, or a 404 if the site has no policy.",
               "The server, CDN or firewall rule serving /robots.txt at %s." % ctx.robots_url,
               "Only a 2xx or a 4xx other than 429 lets a crawler proceed; an error answer reads as "
               "'crawl nothing'.",
               "Serve robots.txt as a static file outside the application, exempt it from rate limiting "
               "and bot challenges, and check the server logs for the status crawlers have been receiving.",
               "Admission of every compliant crawler.",
               "Repeated fetches of robots.txt over at least a day return 200 or 404, never 5xx or 429.",
               "low"),
        status="risk", confidence="low",
        impact={"blocking": True, "breadth": "site", "content_importance": "primary"},
        scope={"pages_affected": len(ctx.pages), "pages_examined": len(ctx.pages),
               "page_types": sorted({p["page_type"] for p in ctx.pages})},
        refs=[ctx.fetch_ref(ctx.robots_url, "HTTP %d on robots.txt (parse_reason %s)" % (status, reason))],
        controls=["only an HTTP response counts, never a network failure",
                  "4xx other than 429 excluded: RFC 9309 treats it as no restrictions"],
        exceptions=["transient outage: not detectable from one request, so status is risk at low confidence",
                    "a rate limit caused by this audit: robots.txt is its first request"]))


def parse_x_robots(header):
    """[(scope or None, directive)] from an X-Robots-Tag value."""
    pairs, scope = [], None
    for segment in (header or "").split(","):
        segment = segment.strip()
        if not segment:
            continue
        head, sep, rest = segment.partition(":")
        if sep and head.strip().lower() not in COLON_DIRECTIVES and rest.strip():
            scope, segment = head.strip().lower(), rest.strip()
        pairs.append((scope, re.sub(r"\s*:\s*", ":", segment.lower())))
    return pairs


def directives(page, scopes):
    found = {t.strip().lower().replace(" ", "") for t in page["meta_robots"]}
    for scope, directive in parse_x_robots(page["headers"]["x_robots_tag"]):
        if scope is None or scope in scopes:
            found.add(directive)
    return found


def template_directive_rule(ctx, out, rule_id, tokens, scopes, eligible, confidence_for, emit):
    candidates = [p for p in ctx.ok_pages if p["page_type"] in PRIMARY_TYPES]
    if not candidates:
        out["not_assessed"].append({"rule_id": rule_id, "reason":
                                    "no 2xx page of a primary type (%s) was sampled" % ", ".join(PRIMARY_TYPES),
                                    "enable_hint": "re-run with a larger sample, or after the site serves "
                                                   "this client its content pages"})
        return
    fired = {}
    for page_type in PRIMARY_TYPES:
        members = [p for p in candidates if p["page_type"] == page_type and eligible(p)]
        affected = [p for p in members if directives(p, scopes) & set(tokens)]
        if not affected:
            continue
        if (page_type == "home") or (len(affected) >= 2 and len(affected) * 2 >= len(members)):
            fired[page_type] = (affected, members)
    if not fired:
        out["passed"].append({"rule_id": rule_id, "summary":
                              "No primary page template carries %s (%s examined)"
                              % (" or ".join(tokens), plural(len(candidates), "primary 2xx page"))})
        return
    total = sum(len(a) for a, _ in fired.values())
    if len(fired) >= 2 and total * 2 >= len(ctx.ok_pages):
        groups = [sorted(fired)]
    else:
        groups = [[t] for t in sorted(fired)]
    for types in groups:
        affected = [p for t in types for p in fired[t][0]]
        members = [p for t in types for p in fired[t][1]]
        breadth = "site" if len(types) >= 2 else "section"
        confidence = confidence_for(types, affected)
        emit(types, affected, members, breadth, confidence)


def acc_003(ctx, out):
    def eligible(page):
        return not (page["canonical"] is not None and not page["canonical_self"])

    def confidence_for(types, affected):
        return "high" if len(affected) >= 3 or types == ["home"] else "medium"

    def emit(types, affected, members, breadth, confidence):
        refs = [ctx.page_ref(p, "robots directives in effect: %s"
                             % ", ".join(sorted(directives(p, INDEX_SCOPES) & set(NOINDEX_TOKENS))))
                for p in affected]
        out["findings"].append(finding(
            "ACC-003", "Pages of type %s refuse indexing" % " and ".join(types),
            "%s of %s sampled 2xx %s pages carry noindex or none in their robots meta tag or X-Robots-Tag "
            "header (%s). A page excluded from the index cannot be retrieved into an answer."
            % (len(affected), len(members), "/".join(types), pct(len(affected), len(members))),
            action("Remove noindex from the %s template or the header rule that emits it." % "/".join(types),
                   "Remove noindex (or none) from the %s page template, or from the header rule adding it."
                   % "/".join(types),
                   "The robots meta tag in the %s template or the server/CDN rule setting X-Robots-Tag, on "
                   "the URLs cited." % "/".join(types),
                   "The directive is applied after fetching, so no amount of crawl access recovers the page.",
                   "Find the template or SEO-plugin setting that applies the directive to the whole type, "
                   "often a 'discourage indexing' toggle left on from staging, and scope it to the pages "
                   "actually meant to be excluded.",
                   "Index admission for the affected template.",
                   "A plain fetch of every cited URL returns no noindex or none in either the robots meta "
                   "tag or X-Robots-Tag.", "low"),
            status="found", confidence=confidence,
            impact={"blocking": True, "breadth": breadth, "content_importance": "primary"},
            scope={"pages_affected": len(affected), "pages_examined": len(members), "page_types": types},
            refs=refs,
            controls=["2xx pages only", "exact token match after lower-casing",
                      "X-Robots-Tag scopes other than the retrieval crawlers ignored",
                      "pages declaring another URL as canonical excluded",
                      "category, contact, policy and other pages never counted"],
            exceptions=["editorial noindex on single pages: at least 2 pages and 50% of the type required",
                        "syndicated copies pointing elsewhere by canonical: excluded"]))

    template_directive_rule(ctx, out, "ACC-003", NOINDEX_TOKENS, INDEX_SCOPES, eligible, confidence_for, emit)


def acc_004(ctx, out):
    def eligible(page):
        return not (directives(page, INDEX_SCOPES) & set(NOINDEX_TOKENS))

    def confidence_for(types, affected):
        return "medium" if len(affected) >= 3 or types == ["home"] else "low"

    def emit(types, affected, members, breadth, confidence):
        refs = [ctx.page_ref(p, "snippet directives in effect: %s"
                             % ", ".join(sorted(directives(p, SNIPPET_SCOPES) & set(NOSNIPPET_TOKENS))))
                for p in affected]
        out["findings"].append(finding(
            "ACC-004", "Pages of type %s forbid snippets" % " and ".join(types),
            "%s of %s sampled indexable 2xx %s pages carry nosnippet or max-snippet:0 (%s). Google documents "
            "that nosnippet applies to AI Overviews and AI Mode and prevents the content being used as a "
            "direct input to them; max-snippet:0 is equivalent."
            % (len(affected), len(members), "/".join(types), pct(len(affected), len(members))),
            action("Remove the page-wide snippet ban from the %s template; mark only restricted passages "
                   "with data-nosnippet." % "/".join(types),
                   "Remove nosnippet or max-snippet:0 from the %s template, or replace it with data-nosnippet "
                   "on only the passages that must not be reproduced." % "/".join(types),
                   "The robots meta tag or X-Robots-Tag rule for the %s pages cited." % "/".join(types),
                   "A page-wide snippet ban forbids quoting every passage, including the ones the owner wants "
                   "attributed.",
                   "Edit the template's robots meta output or the server rule, and put data-nosnippet on "
                   "genuinely restricted passages.",
                   "Quotability in answers that cite the page.",
                   "Every cited URL returns neither nosnippet nor max-snippet:0 in its robots meta tag or "
                   "X-Robots-Tag.", "low"),
            status="found", confidence=confidence,
            impact={"blocking": True, "breadth": breadth, "content_importance": "primary"},
            scope={"pages_affected": len(affected), "pages_examined": len(members), "page_types": types},
            refs=refs, symptom=("invisible", "misrepresented"),
            controls=["2xx pages only", "pages already carrying noindex left to ACC-003",
                      "exact token match: max-snippet:-1 and positive limits never match",
                      "header scopes other than googlebot ignored"],
            exceptions=["deliberate reproduction policy on licensed content: indistinguishable from markup, "
                        "so confidence is capped at medium"]))

    template_directive_rule(ctx, out, "ACC-004", NOSNIPPET_TOKENS, SNIPPET_SCOPES, eligible, confidence_for, emit)


def acc_005(ctx, out):
    domain = (ctx.e["site"]["registrable_domain"] or host_of(ctx.origin)).lower()

    def in_domain(host):
        return host == domain or host.endswith("." + domain)

    def is_root(url):
        parts = urlsplit(url)
        return (parts.path or "/") in ROOT_ALIASES

    non_root = [p for p in ctx.ok_pages if not is_root(p["final_url"])]
    declaring = [p for p in non_root if p["canonical"] is not None]
    if len(declaring) < 2:
        out["not_assessed"].append({"rule_id": "ACC-005", "reason":
                                    "fewer than 2 non-root 2xx pages declare a canonical (%d found)" % len(declaring),
                                    "enable_hint": "re-run with a larger sample; a site declaring no canonicals "
                                                   "has nothing for this rule to check"})
        return
    affected = [p for p in declaring
                if not p["canonical_self"] and in_domain(host_of(p["canonical"]))
                and (urlsplit(p["canonical"]).path or "/") == "/"]
    distinct = {urlsplit(p["final_url"]).path for p in affected}
    if len(distinct) < 2 or len(affected) * 2 < len(declaring):
        out["passed"].append({"rule_id": "ACC-005", "summary":
                              "Distinct pages do not declare the home page as canonical (%d of %d non-root pages "
                              "with a canonical do)" % (len(affected), len(declaring))})
        return
    target = sorted({p["canonical"] for p in affected})
    types = sorted({p["page_type"] for p in affected})
    out["findings"].append(finding(
        "ACC-005", "Distinct pages declare the home page as their canonical URL",
        "%s of %s non-root 2xx pages that declare a canonical name %s, the site root, as their canonical URL. "
        "Each tells an indexer it is a duplicate of the home page."
        % (len(affected), len(declaring), " and ".join(target)),
        action("Emit a per-page canonical equal to each page's own URL.",
               "Make each page's rel=canonical name its own URL.",
               "The shared layout, head component or application shell that emits rel=canonical on the URLs cited.",
               "A canonical is per-page by definition, so a fixed value in a shared layout declares every page "
               "a duplicate of one.",
               "Generate the href from the request path, or from the router's resolved route in a client-rendered "
               "application, and make sure the server response carries the per-page value.",
               "Deep pages indexed as themselves.",
               "Every cited URL returns a canonical equal to its own final URL in the server response.", "medium"),
        status="found", confidence="high" if len(affected) >= 3 else "medium",
        impact={"blocking": False,
                "breadth": "site" if len(affected) * 2 >= len(ctx.ok_pages) else "section",
                "content_importance": "primary" if any(t in PRIMARY_TYPES for t in types) else "secondary"},
        scope={"pages_affected": len(affected), "pages_examined": len(declaring), "page_types": types},
        refs=[ctx.page_ref(p, "canonical %s on %s" % (p["canonical"], p["final_url"])) for p in affected],
        controls=["2xx pages only", "root aliases (/index.html, /home and query-only root variants) not counted",
                  "canonicals on a different registrable domain out of scope",
                  "URLs whose text duplicates a kept page were collapsed by the collector before this rule"],
        exceptions=["single retired page consolidated into home: at least 2 distinct paths required",
                    "one-page site whose routes repeat the home page: collapsed as duplicates upstream"]))


def acc_006(ctx, out):
    probe = ctx.e["ua_probe"]
    by_url = {}
    for entry in probe:
        by_url.setdefault(entry["url"], {})[entry["user_agent"]] = entry["status"]
    comparable = sorted(u for u, agents in by_url.items()
                        if is_2xx(agents.get("browser-ua")) and any(a in agents for a in UA_PROBED_AGENTS))
    if not comparable:
        browser = [agents["browser-ua"] for agents in by_url.values() if "browser-ua" in agents]
        if not probe:
            reason = "no URL was probed under user-agent identities"
        elif browser and not any(is_2xx(s) for s in browser):
            reason = ("browser-ua was refused too (%s), so the site refused this client and nothing about "
                      "how it treats real crawlers can be inferred" % ", ".join(str(s) for s in browser))
        else:
            reason = "no probed URL has both a 2xx browser-ua response and a named-agent response to compare"
        out["not_assessed"].append({"rule_id": "ACC-006", "reason": reason,
                                    "enable_hint": "the probe needs the home page to answer this client with 2xx"})
        return
    refused = {}
    for agent in UA_PROBED_AGENTS:
        urls = [u for u in comparable if agent in by_url[u]]
        if urls and all(by_url[u][agent] in UA_REFUSALS for u in urls):
            refused[agent] = urls
    refused_urls = sorted({u for us in refused.values() for u in us})
    if refused and all(by_url[u].get("Googlebot") in UA_REFUSALS for u in refused_urls):
        # The edge refused the Googlebot string on the same URLs. No site means to
        # shut out Google Search, so this is an edge refusing declared crawlers it
        # cannot verify by address, which admits the real ones from their
        # published ranges. The AI-crawler refusals are that same defence.
        out["not_assessed"].append({"rule_id": "ACC-006", "reason":
                                    "the Googlebot identity was refused on the same URLs as %s (%s), the pattern of "
                                    "an edge that refuses declared crawlers it cannot verify by address; how requests "
                                    "from the crawlers' own addresses are answered cannot be observed from here"
                                    % (", ".join(sorted(refused)),
                                       ", ".join("%s on %s" % (by_url[u]["Googlebot"], u) for u in refused_urls)),
                                    "enable_hint": "check the server or CDN logs for requests from the crawlers' "
                                                   "published address ranges and the status they received"})
        return
    if not refused:
        out["passed"].append({"rule_id": "ACC-006", "summary":
                              "No named AI crawler identity was refused where browser-ua received 2xx (%s compared)"
                              % plural(len(comparable), "URL")})
        return
    urls = sorted({u for us in refused.values() for u in us})
    home = ctx.origin.rstrip("/") + "/"
    detail = "; ".join("%s: %s" % (a, ", ".join("%s on %s" % (by_url[u][a], u) for u in us))
                       for a, us in sorted(refused.items()))
    out["findings"].append(finding(
        "ACC-006", "A named AI crawler identity is refused where robots.txt admits it",
        "The same client sent the same request with different user-agent strings: browser-ua received 2xx, "
        "while %s received a refusal (%s). robots.txt admits these agents. This compares two header strings, "
        "not a browser against a crawler, and cannot show how requests from the operators' own addresses are "
        "treated." % (", ".join(sorted(refused)), detail),
        action("Check the server logs for how verified requests from the named crawlers are answered.",
               "Establish whether requests from the named crawler's published address ranges receive 2xx, and if "
               "not, remove the user-agent match refusing them.",
               "Server access logs first, then web server, CDN bot-management or firewall rules matching on "
               "User-Agent.",
               "robots.txt admits these crawlers, so a refusal at the server contradicts the site's own policy.",
               "Filter logs for the crawler's user-agent string, compare source addresses against the operator's "
               "published ranges, and check the status verified requests received; if refused, verify identity "
               "by address instead of refusing by string.",
               "Admission of the crawler where the policy already grants it.",
               "Server logs show 2xx responses to requests from the crawler's published address ranges on the "
               "cited URLs.", "low"),
        status="risk", confidence="low",
        impact={"blocking": True, "breadth": "site" if home in urls else "section", "content_importance": "primary"},
        scope={"pages_affected": len(urls), "pages_examined": len(comparable),
               "page_types": sorted({p["page_type"] for p in ctx.pages if p["url"] in urls or p["final_url"] in urls})},
        refs=[ctx.fetch_ref(u, "browser-ua %s; %s" % (by_url[u]["browser-ua"], ", ".join(
            "%s %s" % (a, by_url[u][a]) for a in sorted(refused) if a in by_url[u])), ctx.fetched_at_for(u))
              for u in urls],
        controls=["429 and 5xx excluded", "Googlebot excluded: refusing unverified Googlebot is documented defence",
                  "not fired when Googlebot was refused on the same URLs, the pattern of verification by address",
                  "refusal required on every URL where browser-ua received 2xx",
                  "agents robots.txt disallows are never probed"],
        exceptions=["edge verification of claimed identity by published address ranges: indistinguishable here, "
                    "so status is risk at low confidence"]))


def acc_007(ctx, out):
    pages = ctx.pages
    home_ok = any(is_2xx(p["status"]) and (p["page_type"] == "home" or (
        host_of(p["final_url"]) == host_of(ctx.origin) and (urlsplit(p["final_url"]).path or "/") in ROOT_ALIASES))
        for p in pages)
    if len(pages) < 5 or not home_ok:
        out["not_assessed"].append({"rule_id": "ACC-007", "reason":
                                    "the sample holds %s, fewer than 5" % plural(len(pages), "URL") if home_ok else
                                    "no home page answered 2xx, so the crawl behind it is not a sample of the site",
                                    "enable_hint": "needs at least 5 sampled URLs behind a home page that "
                                                   "answers this client"})
        return
    errors = [p for p in pages if is_error(p["status"])]
    if len(errors) < 2 or len(errors) * 10 < len(pages):
        out["passed"].append({"rule_id": "ACC-007", "summary":
                              "%s of %s sampled URLs returned 404, 410 or 5xx, below the 2-URL and 10%% threshold"
                              % (len(errors), len(pages))})
        return
    share = len(errors) / float(len(pages))
    any_5xx = any(p["status"] >= 500 for p in errors)
    out["findings"].append(finding(
        "ACC-007", "URLs the site links to or lists return not-found or server errors",
        "%s of %s sampled URLs (%s), all discovered from the site's own sitemap, navigation or links, returned "
        "an error: %s." % (len(errors), len(pages), pct(len(errors), len(pages)),
                           ", ".join("%s %s" % (p["status"], p["url"]) for p in errors[:10])),
        action("Stop advertising URLs that do not resolve; restore or redirect the ones that should.",
               "Restore, redirect, or stop linking the cited URLs.",
               "The sitemap generator and the navigation or link templates that produced the cited URLs.",
               "Each reference sends crawlers to an error and spends crawl they would otherwise use on real pages.",
               "For each cited URL restore the page, add a 301 to its current equivalent, or remove it from the "
               "sitemap and linking template; for 5xx, check application logs for the failing route.",
               "Every advertised address yields content.",
               "A plain fetch of every cited URL returns 2xx, a redirect to a 2xx, or the URL no longer appears "
               "in the sitemap or on linking pages.", "medium"),
        status="found", confidence="medium" if any_5xx else "high",
        impact={"blocking": True,
                "breadth": "site" if share >= 0.5 else "section" if share >= 0.25 else "page",
                "content_importance": "secondary"},
        scope={"pages_affected": len(errors), "pages_examined": len(pages), "page_types": []},
        refs=[ctx.page_ref(p, "HTTP %s at %s" % (p["status"], p["final_url"])) for p in errors],
        controls=["401, 403 and 429 excluded as refusals to this client",
                  "status judged at the final URL after redirects", "5xx lowers confidence"],
        exceptions=["retired content served 410 behind a stale link: counted, the reference is the defect",
                    "momentary outage: handled by confidence"]))


def acc_008(ctx, out):
    robots = ctx.robots
    if not (robots["parse_ok"] and robots["parse_reason"] == "ok"):
        kind, entry = robots_not_ok(ctx, "ACC-008")
        out[kind].append(entry)
        return
    groups, verdicts = robots["groups"], robots["ai_agents"]
    named = [a for a in RETRIEVAL_AGENTS if verdicts[a] == "disallowed" and named_groups(groups, a)]
    training = [a for a in TRAINING_AGENTS if verdicts[a] == "disallowed" and named_groups(groups, a)]
    if not named:
        summary = "No answer-time retrieval crawler is excluded by name in robots.txt"
        if training:
            summary += "; training agents excluded by name, which removes no page from any answer index: %s" \
                       % ", ".join(training)
        out["passed"].append({"rule_id": "ACC-008", "summary": summary})
        return
    naming = [g for a in named for g in named_groups(groups, a)]
    scope = exclusion_scope(ctx, named)
    evidence = ("robots.txt names %s in %s and disallows /: %s. This is the site's stated policy, reported for "
                "its consequence: %s cannot retrieve, quote or cite the site. %s of %s sampled pages are covered."
                % (", ".join(named), "its own group" if len(named) == 1 else "their own groups",
                   quote_group(naming), served(named), scope["pages_affected"],
                   scope["pages_examined"]))
    if training:
        evidence += " Training agents also excluded by name: %s." % ", ".join(training)
    out["findings"].append(finding(
        "ACC-008", "Answer-time retrieval crawler excluded by name in robots.txt", evidence,
        action("Decide per assistant whether appearing in its answers is wanted; readmit only those search "
               "crawlers and keep training crawlers excluded.",
               "For each of %s, decide whether visibility in that assistant is wanted, and where it is, readmit "
               "that search crawler alone." % ", ".join(named),
               "The groups naming %s in the robots.txt at %s." % (", ".join(named), ctx.robots_url),
               "Search and training crawlers are separate products that their operators govern independently, "
               "so refusing training never required refusing citation.",
               "Keep `User-agent: GPTBot` with `Disallow: /` if training is refused, and change the `User-agent: "
               "%s` group from `Disallow: /` to `Allow: /` with the site's private-path Disallow lines." % named[0],
               "Citation eligibility in the assistants readmitted.",
               "Re-fetching robots.txt yields `allowed` for each retrieval crawler the owner chose to readmit, "
               "while training agents keep the verdict chosen for them.", "low"),
        status="proactive", confidence="high",
        impact={"blocking": True, "breadth": "section" if has_content_allows(naming) else "site",
                "content_importance": "primary"},
        scope=scope,
        refs=[ctx.fetch_ref(ctx.robots_url, "named group disallows / for %s" % ", ".join(named))],
        controls=["training agents never fire this rule", "a named group that allows the crawler does not fire",
                  "the evidence quotes the site's own group"],
        exceptions=["intended exclusion, such as pending licensing: the expected case, hence proactive"]))


def acc_009(ctx, out):
    robots = ctx.robots
    declared = list(robots["sitemaps"]) if robots["parse_ok"] else []
    records = {s["url"]: s for s in ctx.e["sitemaps"]}
    assessable = [records[u] for u in declared
                  if u in records and records[u]["status"] is not None
                  and records[u]["status"] not in CLIENT_REFUSALS]
    if not assessable:
        reason = ("robots.txt was not parsed" if not robots["parse_ok"] else
                  "robots.txt declares no sitemap" if not declared else
                  "no declared sitemap produced an assessable response (not requested, no response, or refused "
                  "to this client)")
        out["not_assessed"].append({"rule_id": "ACC-009", "reason": reason,
                                    "enable_hint": "applies only to sitemaps declared in a parsed robots.txt that "
                                                   "answer this client"})
        return
    failing = [s for s in assessable if is_error(s["status"]) or (is_2xx(s["status"]) and not s["parse_ok"])]
    if not failing:
        out["passed"].append({"rule_id": "ACC-009", "summary":
                              "Every assessable sitemap declared in robots.txt returned a readable sitemap (%s)"
                              % plural(len(assessable), "file")})
        return

    def describe(s):
        return ("HTTP %s, not a sitemap document" % s["status"]) if is_2xx(s["status"]) else "HTTP %s" % s["status"]

    out["findings"].append(finding(
        "ACC-009", "A sitemap declared in robots.txt cannot be read",
        "%s of %s assessable sitemaps declared in robots.txt failed: %s."
        % (len(failing), len(assessable), "; ".join("%s (%s)" % (s["url"], describe(s)) for s in failing)),
        action("Make each declared sitemap URL return a valid sitemap, or remove declarations of retired files.",
               "Make each declared sitemap URL return a valid sitemap, or remove declarations pointing at retired "
               "files.",
               "The Sitemap: lines in robots.txt at %s and the generator behind each cited URL." % ctx.robots_url,
               "A crawler trusts the declaration and does not guess alternatives.",
               "Request each declared URL; fix the generator route or the path in robots.txt if it errors; if it "
               "returns an HTML page, typically an application shell answering every path, exempt the sitemap "
               "path from that routing.",
               "Complete URL discovery for every crawler that reads robots.txt.",
               "Every URL in the robots.txt Sitemap: lines returns 2xx and parses as a urlset or sitemapindex "
               "document.", "low"),
        status="found",
        confidence="medium" if any(isinstance(s["status"], int) and s["status"] >= 500 for s in failing) else "high",
        impact={"blocking": False, "breadth": "site" if len(failing) == len(assessable) else "section",
                "content_importance": "secondary"},
        scope={"pages_affected": len(failing), "pages_examined": len(assessable), "page_types": []},
        refs=[ctx.fetch_ref(s["url"], describe(s)) for s in failing],
        controls=["only sitemaps declared in robots.txt counted", "sitemaps reached through an index not counted",
                  "401, 403 and 429 excluded", "no-response entries excluded",
                  "gzip sitemaps decompressed by the collector"],
        exceptions=["declaration of a retired file: counted, the declaration is the defect",
                    "outage during the audit: handled by confidence"]))


RULES = (acc_001, acc_002, acc_003, acc_004, acc_005, acc_006, acc_007, acc_008, acc_009)


def diagnose(evidence):
    version = str(evidence.get("schema_version", ""))
    if version.split(".")[0] != SUPPORTED_SCHEMA_MAJOR:
        raise ValueError("unsupported evidence schema_version %r; this skill reads %s.x"
                         % (version, SUPPORTED_SCHEMA_MAJOR))
    ctx = Context(evidence)
    out = {"findings": [], "not_assessed": [], "passed": []}
    for rule in RULES:
        rule(ctx, out)
    for index, item in enumerate(out["findings"], start=1):
        item["id"] = "F-%03d" % index
    return {"findings": out["findings"], "not_assessed": out["not_assessed"], "checks_passed": out["passed"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the access-and-indexability rules over an evidence bundle.")
    parser.add_argument("--evidence", required=True, help="path to evidence/evidence.json")
    parser.add_argument("--out", required=True, help="path to write findings/access-and-indexability.json")
    args = parser.parse_args(argv)
    with open(args.evidence, encoding="utf-8") as handle:
        result = diagnose(json.load(handle))
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
