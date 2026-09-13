"""freshness-and-corroboration: the two rules in ../references/rules.md, as code.

Reads evidence/evidence.json and nothing else, and writes one findings file
holding ``findings``, ``not_assessed`` and ``checks_passed``. An unchecked claim
is never reported as supported or unsupported: without a comparable external
record the corroboration rule is not assessed.

Each function implements the rule block of the same id; the block holds the
reasons. ``severity`` and ``suggested_action.priority`` are never set; the
orchestrator derives them.

Standard library only. No imports from any other skill.
"""

import argparse
import json
import os

SKILL = "freshness-and-corroboration"
SUPPORTED_SCHEMA_MAJOR = "1"

ARTICLE_CONFIDENCE = 0.8
STRUCTURED_RECORD = "wikidata.org"


def is_2xx(status):
    return isinstance(status, int) and 200 <= status <= 299


def plural(n, word, many=None):
    return "%d %s" % (n, word if n == 1 else (many or word + "s"))


def dates_readable(page):
    """The collector reads month names in English only, so a date written in
    another language is invisible to it. Absence is judged only where it can
    be observed: pages declaring English, or declaring no language."""
    return page["lang"] is None or page["lang"].strip().lower().split("-")[0] in ("en", "")


def is_undated(page):
    dates = page["dates"]
    return not dates["schema_date_published"] and not dates["schema_date_modified"] and not dates["visible_dates"]


def frc_001(evidence, out):
    classified = [p for p in evidence["pages"]
                  if is_2xx(p["status"]) and p["page_type"] == "article"
                  and (p["page_type_confidence"] or 0) >= ARTICLE_CONFIDENCE]
    articles = [p for p in classified if dates_readable(p)]
    if len(articles) < 2:
        other = len(classified) - len(articles)
        out["not_assessed"].append({"rule_id": "FRC-001", "reason":
                                    "article pages classified with confidence >= 0.8 sampled: %d; 2 are needed%s"
                                    % (len(articles), " (%s declaring a language other than English, whose written "
                                       "dates the audit cannot read, set aside)" % plural(other, "further page")
                                       if other else ""),
                                    "enable_hint": "applies to sites publishing articles; for articles in other "
                                                   "languages, check by hand that each shows a date and carries "
                                                   "datePublished"})
        return
    undated = [p for p in articles if is_undated(p)]
    if len(undated) < 2 or len(undated) * 2 < len(articles):
        out["passed"].append({"rule_id": "FRC-001", "summary":
                              "Articles state a date: %d of %s carry no visible or structured date, below the "
                              "template threshold" % (len(undated), plural(len(articles), "article page"))})
        return
    out["findings"].append({
        "id": "F-001",
        "title": "Articles state no date a machine can read",
        "evidence": "%d of %s show no visible date and carry neither datePublished nor dateModified in JSON-LD: %s."
                    % (len(undated), plural(len(articles), "sampled article page"),
                       ", ".join(p["url"] for p in undated[:5])),
        "suggested_action": {
            "summary": "Show a labelled publication or update date on articles and emit datePublished and dateModified.",
            "what": "Show a labelled publication or update date on the article template and emit it as datePublished "
                    "and dateModified.",
            "where": "The article template behind the URLs cited.",
            "why": "A machine can only judge recency from a date it can read.",
            "how": "Render Published and Updated dates near the headline, and emit an Article or BlogPosting JSON-LD "
                   "node carrying datePublished and dateModified in ISO 8601, generated from the same fields.",
            "mechanism": "Recency can be read rather than guessed.",
            "success_criteria": "Every cited URL shows a visible date and carries datePublished or dateModified in its "
                                "server response JSON-LD.",
            "effort": "low",
        },
        "skill": SKILL, "rule_id": "FRC-001", "status": "found", "category": "discoverability",
        "symptom": ["misrepresented"], "confidence": "medium",
        "impact": {"blocking": False, "breadth": "section", "content_importance": "secondary"},
        "scope": {"pages_affected": len(undated), "pages_examined": len(articles), "page_types": ["article"]},
        "evidence_refs": [{"url": p["url"], "observation": "no visible date, no datePublished, no dateModified",
                           "layer": p["provenance"]["layer"], "method": p["provenance"]["method"],
                           "retrieved_at": p["fetched_at"]} for p in undated],
        "false_positive_controls_applied": ["2xx pages only", "article classifier confidence >= 0.8",
                                            "only pages in English or with no declared language, whose dates the "
                                            "audit can read",
                                            "any visible date counts, including boilerplate dates",
                                            "HTTP Last-Modified not accepted as an article date"],
        "exceptions_checked": ["evergreen undated reference pages: undetectable, confidence medium and a 2-page floor"],
    })


def frc_002(evidence, out):
    external = evidence["external"]
    if not evidence["run_context"]["capabilities"]["egress"] or not external["attempted"]:
        out["not_assessed"].append({"rule_id": "FRC-002", "reason":
                                    "the off-site probe did not run (egress %s, attempted %s), so no claim was checked"
                                    % (evidence["run_context"]["capabilities"]["egress"], external["attempted"]),
                                    "enable_hint": "run with network access to public records and without --no-egress"})
        return
    claims = [c for c in evidence["canonical_claims"]
              if c["kind"] == "founded_year" and c["first_party_confidence"] in ("high", "medium")
              and c["entity_ambiguity"] != "high"]
    by_claim = {c["id"]: c for c in claims}
    hits = [h for h in external["hits"] if h["claim_id"] in by_claim and h["origin"] == STRUCTURED_RECORD]
    if not hits:
        out["not_assessed"].append({"rule_id": "FRC-002", "reason":
                                    "no founding-year claim with medium or high first-party confidence and an "
                                    "unambiguous name was matched to a Wikidata record (frontier: %s)"
                                    % plural(external["frontier_size"], "source"),
                                    "enable_hint": "applies when the site states a founding year and its organization "
                                                   "has a Wikidata item naming the site as official website"})
        return
    disagreements = [h for h in hits if not h["matches_current"]]
    if not disagreements:
        out["passed"].append({"rule_id": "FRC-002", "summary":
                              "The site's founding year agrees with its Wikidata record (%s)"
                              % "; ".join("%s: %s" % (by_claim[h["claim_id"]]["value_normalized"], h["asserted_value"])
                                          for h in hits)})
        return
    hit = disagreements[0]
    claim = by_claim[hit["claim_id"]]
    out["findings"].append({
        "id": "F-001",
        "title": "The site's founding year disagrees with its Wikidata record",
        "evidence": "The site states %s as its founding year (claim %s, first-party confidence %s); the Wikidata item "
                    "%s, matched to this site by its official-website statement, records %s. Of the %s the off-site "
                    "probe could enumerate, this is the structured record; it is not a survey of the open web."
                    % (claim["value_normalized"], claim["id"], claim["first_party_confidence"], hit["url"],
                       hit["asserted_value"], plural(external["frontier_size"], "source")),
        "suggested_action": {
            "summary": "Establish which founding year is right for which event, then align the site and its Wikidata "
                       "record or label the site's year.",
            "what": "Establish which year is correct for which event, then make the site and the public record agree, "
                    "or say explicitly what each year refers to.",
            "where": "The site's about page and organization markup, and the Wikidata item %s." % hit["url"],
            "why": "A structured public record is where a founding year is most likely to be taken from.",
            "how": "If the site is wrong, correct its pages and foundingDate; if Wikidata is wrong, propose a correction "
                   "on the item with a reference to a primary source through Wikidata's own editing process; if both "
                   "describe different events, label the site's year, for example 'first published in'.",
            "mechanism": "One consistent founding fact across the sources machines read.",
            "success_criteria": "The founding year on the site and the inception year on the cited Wikidata item agree, "
                                "or the site labels which event its year refers to.",
            "effort": "low",
        },
        "skill": SKILL, "rule_id": "FRC-002", "status": "risk", "category": "discoverability",
        "symptom": ["misrepresented"],
        "confidence": "medium" if claim["first_party_confidence"] == "high" else "low",
        "impact": {"blocking": False, "breadth": "site", "content_importance": "secondary"},
        "scope": {"pages_affected": 0, "pages_examined": 0, "page_types": []},
        "evidence_refs": [{"url": hit["url"], "observation": "Wikidata records %s; the site states %s"
                           % (hit["asserted_value"], claim["value_normalized"]),
                           "layer": "third_party", "method": "fetch", "retrieved_at": hit["retrieved_at"]}],
        "false_positive_controls_applied": ["only wikidata.org structured hits compared",
                                            "Wayback, Wikipedia prose and sameAs hits never read as contradictions",
                                            "low-confidence claims and ambiguous names excluded (D8)",
                                            "identity settled by Wikidata's official-website statement"],
        "exceptions_checked": ["the two years may describe different events: undetectable, hence risk"],
    })


RULES = (frc_001, frc_002)


def diagnose(evidence):
    version = str(evidence.get("schema_version", ""))
    if version.split(".")[0] != SUPPORTED_SCHEMA_MAJOR:
        raise ValueError("unsupported evidence schema_version %r; this skill reads %s.x"
                         % (version, SUPPORTED_SCHEMA_MAJOR))
    out = {"findings": [], "not_assessed": [], "passed": []}
    for rule in RULES:
        rule(evidence, out)
    for index, item in enumerate(out["findings"], start=1):
        item["id"] = "F-%03d" % index
    return {"findings": out["findings"], "not_assessed": out["not_assessed"], "checks_passed": out["passed"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the freshness-and-corroboration rules over an evidence bundle.")
    parser.add_argument("--evidence", required=True, help="path to evidence/evidence.json")
    parser.add_argument("--out", required=True, help="path to write findings/freshness-and-corroboration.json")
    args = parser.parse_args(argv)
    with open(args.evidence, encoding="utf-8") as handle:
        result = diagnose(json.load(handle))
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
