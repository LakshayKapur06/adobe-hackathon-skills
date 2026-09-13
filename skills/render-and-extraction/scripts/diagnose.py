"""render-and-extraction: the three rules in ../references/rules.md, as code.

Reads evidence/evidence.json and the extracted-text sidecars it names, and
writes one findings file holding ``findings``, ``not_assessed`` and
``checks_passed``. Every rule ends in exactly one of those outcomes, and a rule
that needed a rendered comparison it did not get says so rather than passing.

Each function implements the rule block of the same id; the block holds the
reasons for every number used here. ``severity`` and
``suggested_action.priority`` are never set; the orchestrator derives them.

Standard library only. No imports from any other skill.
"""

import argparse
import json
import os
import re
import urllib.parse

SKILL = "render-and-extraction"
SUPPORTED_SCHEMA_MAJOR = "1"

PRIMARY_TYPES = ("home", "product", "article", "doc", "about")
JS_DELTA = 0.8
JS_MIN_GAIN = 200
EMPTY_TEXT = 200
PRICE_SHARE = 0.6
PRICE_MIN_PAGES = 5
PRICE_HIGH_PAGES = 8
PRICE_TOKEN = re.compile(r"(?:₹|\$|€|£|¥|\bRs\.?|\bINR\b|\bUSD\b|\bEUR\b|\bGBP\b|\bJPY\b)\s?\d[\d,]*(?:\.\d+)?")
# A price written with the currency after the amount, as much of Europe writes it
# ("1.499,00 €", "29,95 EUR"). It counts only as evidence that the server
# response already carries a price, so it can silence the rule, never fire it.
PRICE_AFTER = re.compile(r"\d[\d.,]*\s?(?:€|£|₹|\$|\bEUR\b|\bUSD\b|\bGBP\b|\bINR\b|\bCHF\b|\bkr\b|zł)")
PRICE_FIELDS = ("offers.price", "offers.lowPrice")


def is_2xx(status):
    return isinstance(status, int) and 200 <= status <= 299


def is_html(page):
    return "html" in (page["content_type"] or "").lower()


def comparable(page):
    return is_2xx(page["status"]) and is_html(page) and page["rendered"]["available"]


def server_text(page):
    """Visible plus hidden server text: what a fetcher that ignores CSS extracts."""
    return page["raw"]["text_len"] + page["raw"]["hidden_text_len"]


def js_dependent(page):
    rendered = page["rendered"]
    rendered_len = rendered["text_len"] or 0
    return (rendered["delta_ratio"] is not None and rendered["delta_ratio"] >= JS_DELTA
            and rendered_len - page["raw"]["text_len"] >= JS_MIN_GAIN
            and server_text(page) <= (1 - JS_DELTA) * rendered_len)


def ref(page, observation):
    return {"url": page["url"], "observation": observation, "layer": page["provenance"]["layer"],
            "method": page["provenance"]["method"], "retrieved_at": page["fetched_at"]}


def plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def finding(rule_id, title, evidence, action, *, confidence, impact, scope, refs, controls, exceptions, symptom):
    return {"id": "F-001", "title": title, "evidence": evidence, "suggested_action": action, "skill": SKILL,
            "rule_id": rule_id, "status": "found", "category": "discoverability", "symptom": list(symptom),
            "confidence": confidence, "impact": impact, "scope": scope, "evidence_refs": refs,
            "false_positive_controls_applied": list(controls), "exceptions_checked": list(exceptions)}


def action(summary, what, where, why, how, mechanism, success, effort):
    return {"summary": summary, "what": what, "where": where, "why": why, "how": how,
            "mechanism": mechanism, "success_criteria": success, "effort": effort}


NO_BROWSER = {"reason": "no browser was available, so no page could be rendered and compared with its server response",
              "enable_hint": "install a Chromium-based browser (Chrome, Edge or Chromium) and re-run without --no-render"}


def shared_path(pages):
    """The deepest directory every URL sits under, such as "/cli/", or None.

    Page types are inferred from URLs, so one client-side application can be
    filed under several types; naming the path it shares says what the fix
    covers more precisely than the type does."""
    if len(pages) < 2:
        return None
    dirs = [[part for part in urllib.parse.urlsplit(page["url"]).path.split("/") if part][:-1] for page in pages]
    common = []
    for parts in zip(*dirs):
        if len(set(parts)) != 1:
            break
        common.append(parts[0])
    return "/" + "/".join(common) + "/" if common else None


def rnd_001(evidence, workdir, out):
    pages = [p for p in evidence["pages"] if comparable(p)]
    if not evidence["run_context"]["capabilities"]["js_render"]:
        out["not_assessed"].append(dict(NO_BROWSER, rule_id="RND-001"))
        return
    if len(pages) < 2:
        out["not_assessed"].append({"rule_id": "RND-001", "reason":
                                    "only %s had both a server response and a rendered DOM to compare"
                                    % plural(len(pages), "page"),
                                    "enable_hint": "raise the render budget or sample size; pages outside the render "
                                                   "budget are fetch-only"})
        return
    dependent = [p for p in pages if js_dependent(p)]
    groups = []
    spans_site = (any(p["page_type"] == "home" for p in dependent)
                  or len({p["page_type"] for p in dependent}) >= 2)
    if len(dependent) >= 2 and len(dependent) * 2 >= len(pages) and spans_site:
        groups.append(("site", dependent, pages))
    else:
        for page_type in PRIMARY_TYPES:
            members = [p for p in pages if p["page_type"] == page_type]
            hit = [p for p in dependent if p["page_type"] == page_type]
            if not hit:
                continue
            if page_type == "home" or (len(hit) >= 2 and len(hit) * 2 >= len(members)):
                groups.append(("section", hit, members))
    if not groups:
        out["passed"].append({"rule_id": "RND-001", "summary":
                              "No template depends on JavaScript for its text: %d of %s compared are "
                              "JavaScript-dependent, below the template threshold"
                              % (len(dependent), plural(len(pages), "rendered page"))})
        return
    unrendered = sum(1 for p in evidence["pages"]
                     if is_2xx(p["status"]) and is_html(p) and not p["rendered"]["available"])
    for breadth, hit, members in groups:
        types = sorted({p["page_type"] for p in hit})
        empty_server = all(p["raw"]["text_len"] < EMPTY_TEXT for p in hit)
        primary = any(t in PRIMARY_TYPES for t in types)
        where = "across the site" if breadth == "site" else "on %s pages" % types[0]
        under = shared_path(hit) if breadth == "section" else None
        if under:
            where += " under %s" % under
        out["findings"].append(finding(
            "RND-001", "Page content exists only after JavaScript runs (%s)" % (
                "site-wide" if breadth == "site" else ("pages under %s" % under if under else types[0])),
            "%d of %s compared %s are JavaScript-dependent: at least 80%% of their rendered text is missing from the "
            "server response. Examples: %s. %s"
            % (len(hit), plural(len(members), "rendered page"), where,
               "; ".join("%s (server response %d characters, rendered page %d)"
                         % (p["url"], p["raw"]["text_len"], p["rendered"]["text_len"])
                         for p in hit[:5]),
               ("%s were not rendered within budget and are not counted." % plural(unrendered, "HTML page"))
               if unrendered else "Every sampled HTML page was rendered."),
            action("Server-render, statically generate or prerender these routes so their text is in the server "
                   "response.",
                   "Put the page's substance in the server response for the templates %s." % where,
                   ("The routes under %s and the rendering configuration of the application serving them."
                    % under) if under else "The routes cited and the rendering configuration of their templates.",
                   "Text assembled in the browser does not exist for a fetcher that does not run scripts.",
                   "Enable the framework's server rendering or static generation for these routes, or put a "
                   "prerendering step in front of them serving the rendered HTML to every client alike; then "
                   "confirm with a plain fetch that headings and body text are present.",
                   "Extraction of the page's text from the fetched response.",
                   "A plain fetch with no JavaScript of every cited URL returns the main headings and body text, so "
                   "that at least a fifth of what the rendered page shows is already in the server response.", "high"),
            confidence="high" if empty_server else "medium",
            impact={"blocking": True, "breadth": breadth,
                    "content_importance": "primary" if primary else "secondary"},
            scope={"pages_affected": len(hit), "pages_examined": len(members), "page_types": types},
            refs=[ref(p, "server text %d chars, rendered %d chars, delta_ratio %.3f"
                      % (p["raw"]["text_len"], p["rendered"]["text_len"], p["rendered"]["delta_ratio"])) for p in hit],
            controls=["only 2xx HTML pages with a rendered DOM compared",
                      "server text hidden with CSS counts as present in the server response",
                      "delta_ratio >= 0.8 and >= 200 characters gained, above the measured hydrated-widget band",
                      "pages outside the render budget excluded from numerator and denominator",
                      "rendered duplicates collapsed by the collector"],
            exceptions=["single dependent page on a server-rendered site: template share of 50% required",
                        "dynamic rendering for crawlers: undetectable, confidence medium unless the server text is empty"],
            symptom=("invisible", "misrepresented")))


def rnd_002(evidence, workdir, out):
    pages = evidence["pages"]
    if any(comparable(p) for p in pages):
        out["not_assessed"].append({"rule_id": "RND-002", "reason":
                                    "rendered pages were available, so RND-001 made the stronger raw-versus-rendered "
                                    "comparison instead",
                                    "enable_hint": "none needed: this rule covers only runs with no rendered page"})
        return
    html = [p for p in pages if is_2xx(p["status"]) and is_html(p)]
    if not any(p["page_type"] == "home" for p in html):
        out["not_assessed"].append({"rule_id": "RND-002", "reason":
                                    "no 2xx HTML home page was observed, so the server response of the site's front "
                                    "door is unknown",
                                    "enable_hint": "the home page must answer this client with 2xx"})
        return
    thin = [p for p in html if server_text(p) < EMPTY_TEXT]
    if len(thin) < len(html):
        out["passed"].append({"rule_id": "RND-002", "summary":
                              "%d of %s carry at least %d characters of text in the server response"
                              % (len(html) - len(thin), plural(len(html), "2xx HTML page"), EMPTY_TEXT)})
        return
    soft = evidence["discovery"]["soft_404"]
    shell = bool(soft["detected"] and soft["baseline_text_hash"]
                 and all(p["raw"]["text_hash"] == soft["baseline_text_hash"] for p in html))
    collapsed = evidence["discovery"]["collapsed_duplicate_text"]
    no_browser = not evidence["run_context"]["capabilities"]["js_render"]
    out["findings"].append(finding(
        "RND-002", "The server response carries no text on any sampled page",
        "%s returned fewer than %d characters of text in the server response (%s).%s%s No page was "
        "rendered%s, so what a browser would add is not measured here; what a fetcher that does not execute "
        "JavaScript receives is observed directly."
        % ("The only 2xx HTML page sampled" if len(html) == 1 else "All %d 2xx HTML pages sampled" % len(html),
           EMPTY_TEXT,
           ", ".join("%s: %d" % (p["url"], p["raw"]["text_len"]) for p in html[:5]),
           " The site answered two paths that cannot exist with the identical response, so every URL serves one "
           "empty application shell." if shell else "",
           (" %s with identical text were collapsed before sampling." % plural(collapsed, "further URL"))
           if collapsed else "",
           " because no browser was available" if no_browser else " because every render attempt failed"),
        action("Serve the site's content in the server response rather than only through client-side scripts.",
               "Serve content in the server response instead of only through client-side scripts.",
               "The application shell served at the URLs cited.",
               "The server response is all a non-rendering fetcher ever reads.",
               "Adopt server-side rendering or static generation for the site's routes, or place a prerendering "
               "step in front of them serving the same rendered HTML to every client; re-run this audit with a "
               "browser available to measure the gap per template.",
               "Any text at all reaching a fetcher that does not execute scripts.",
               "A plain fetch of the home page and each cited URL returns at least the page's main heading and body "
               "text in the server response.", "high"),
        confidence="high" if shell else "medium",
        impact={"blocking": True, "breadth": "site", "content_importance": "primary"},
        scope={"pages_affected": len(html), "pages_examined": len(html),
               "page_types": sorted({p["page_type"] for p in html})},
        refs=[ref(p, "server response text %d characters" % p["raw"]["text_len"]) for p in html],
        controls=["only 2xx HTML pages counted, so a refused home page cannot fire this",
                  "non-HTML resources excluded", "every page must be under the threshold, not a share",
                  "soft-404 baseline compared to establish a single shell"],
        exceptions=["a site that genuinely has no content yet: indistinguishable without rendering, confidence medium "
                    "unless a single shell answers every path"],
        symptom=("invisible",)))


def read_sidecar(workdir, path):
    if not path:
        return ""
    full = os.path.join(workdir, path)
    if not os.path.isfile(full):
        return None
    with open(full, encoding="utf-8") as handle:
        return handle.read()


def rnd_003(evidence, workdir, out):
    if not evidence["run_context"]["capabilities"]["js_render"]:
        out["not_assessed"].append(dict(NO_BROWSER, rule_id="RND-003"))
        return
    eligible = [p for p in evidence["pages"]
                if comparable(p) and p["page_type"] == "product" and (p["page_type_confidence"] or 0) >= 0.6
                and not js_dependent(p)]
    texts = {}
    for p in eligible:
        raw, rendered = read_sidecar(workdir, p["raw"]["text_path"]), read_sidecar(workdir, p["rendered"]["text_path"])
        if raw is not None and rendered is not None:
            texts[p["url"]] = (raw, rendered)
    eligible = [p for p in eligible if p["url"] in texts]
    if len(eligible) < PRICE_MIN_PAGES:
        out["not_assessed"].append({"rule_id": "RND-003", "reason":
                                    "only %s met the bar (rendered, product with classifier confidence >= 0.6, not "
                                    "already JavaScript-dependent, text sidecars present); %d are needed"
                                    % (plural(len(eligible), "product page"), PRICE_MIN_PAGES),
                                    "enable_hint": "applies to sites with at least 5 sampled, rendered product pages"})
        return

    def structured_price(page):
        return any(f in PRICE_FIELDS for block in page["jsonld"] for f in block["fields_present"])

    hit = []
    for p in eligible:
        raw, rendered = texts[p["url"]]
        in_server = PRICE_TOKEN.search(raw) or PRICE_AFTER.search(raw)
        if not in_server and PRICE_TOKEN.search(rendered) and not structured_price(p):
            hit.append(p)
    if len(hit) < PRICE_SHARE * len(eligible):
        out["passed"].append({"rule_id": "RND-003", "summary":
                              "Prices are present in the server response on product pages: %d of %s show a price only "
                              "after rendering, below 60%%" % (len(hit), plural(len(eligible), "eligible product page"))})
        return
    out["findings"].append(finding(
        "RND-003", "Product prices appear only after rendering",
        "Rendered %s; a price appears in the rendered text of %d and in neither the server text nor server JSON-LD "
        "of those %d. Examples: %s."
        % (plural(len(eligible), "eligible product page"), len(hit), len(hit),
           "; ".join("%s (rendered shows %s)" % (p["url"], PRICE_TOKEN.search(texts[p["url"]][1]).group(0))
                     for p in hit[:5])),
        action("Server-render the product price, or emit Offer JSON-LD with offers.price in the server response.",
               "Include the price in the server response of the product template, as visible text or Offer JSON-LD.",
               "The product page template and its price component, on the URLs cited.",
               "The server response is what a fetcher extracts, and it holds a product without a price.",
               "Render the price component on the server, or emit Product with offers.price and "
               "offers.priceCurrency in JSON-LD generated server-side.",
               "The price becomes extractable and quotable.",
               "The price appears in the server response, as text or as offers.price JSON-LD, on every cited product "
               "URL, verifiable with a plain fetch and no JavaScript.", "medium"),
        confidence="high" if len(eligible) >= PRICE_HIGH_PAGES else "medium",
        impact={"blocking": True, "breadth": "section", "content_importance": "primary"},
        scope={"pages_affected": len(hit), "pages_examined": len(eligible), "page_types": ["product"]},
        refs=[ref(p, "no price token in server text or JSON-LD; rendered text contains %s"
                  % PRICE_TOKEN.search(texts[p["url"]][1]).group(0)) for p in hit],
        controls=["same currency-token pattern applied to both texts",
                  "pages with any price in the server text excluded",
                  "pages exposing offers.price or offers.lowPrice in server JSON-LD excluded",
                  "JavaScript-dependent pages left to RND-001", "page_type_confidence >= 0.6"],
        exceptions=["quote-on-request pricing: no price in rendered text either, so never matches",
                    "region-selected pricing: undetectable, confidence below high under 8 pages"],
        symptom=("invisible", "misrepresented")))


RULES = (rnd_001, rnd_002, rnd_003)


def diagnose(evidence, workdir):
    version = str(evidence.get("schema_version", ""))
    if version.split(".")[0] != SUPPORTED_SCHEMA_MAJOR:
        raise ValueError("unsupported evidence schema_version %r; this skill reads %s.x"
                         % (version, SUPPORTED_SCHEMA_MAJOR))
    out = {"findings": [], "not_assessed": [], "passed": []}
    for rule in RULES:
        rule(evidence, workdir, out)
    for index, item in enumerate(out["findings"], start=1):
        item["id"] = "F-%03d" % index
    return {"findings": out["findings"], "not_assessed": out["not_assessed"], "checks_passed": out["passed"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the render-and-extraction rules over an evidence bundle.")
    parser.add_argument("--evidence", required=True, help="path to evidence/evidence.json")
    parser.add_argument("--out", required=True, help="path to write findings/render-and-extraction.json")
    args = parser.parse_args(argv)
    evidence_path = os.path.abspath(args.evidence)
    workdir = os.path.dirname(os.path.dirname(evidence_path))
    with open(evidence_path, encoding="utf-8") as handle:
        result = diagnose(json.load(handle), workdir)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
