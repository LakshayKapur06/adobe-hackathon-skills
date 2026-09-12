"""answerability: the rule in ../references/rules.md, as code.

Reads evidence/evidence.json and nothing else, and writes one findings file
holding ``findings``, ``not_assessed`` and ``checks_passed``. The rule block
holds the reasons for every number used here, and ``references/rules.md`` also
records the text metrics that were measured and rejected as evidence.
``severity`` and ``suggested_action.priority`` are never set; the orchestrator
derives them.

Standard library only. No imports from any other skill.
"""

import argparse
import json
import os

SKILL = "answerability"
SUPPORTED_SCHEMA_MAJOR = "1"

LONG_FORM_TYPES = ("article", "doc")
LONG_WORDS = 1500
FEW_HEADINGS = 3
NEWS_TYPES = ("NewsArticle", "ReportageNewsArticle", "LiveBlogPosting")


def is_2xx(status):
    return isinstance(status, int) and 200 <= status <= 299


def plural(n, word, many=None):
    return "%d %s" % (n, word if n == 1 else (many or word + "s"))


def ans_001(evidence, out):
    long_pages = [p for p in evidence["pages"]
                  if is_2xx(p["status"]) and p["page_type"] in LONG_FORM_TYPES
                  and p["text"]["word_count"] >= LONG_WORDS
                  and not any(n["type"] in NEWS_TYPES for n in p["jsonld"])]
    if len(long_pages) < 2:
        out["not_assessed"].append({"rule_id": "ANS-001", "reason":
                                    "long-form article or doc pages of at least %d words sampled, news reporting "
                                    "excluded: %d; the recommendation needs 2" % (LONG_WORDS, len(long_pages)),
                                    "enable_hint": "applies only to sites publishing long articles or documentation"})
        return
    fired = []
    for page_type in LONG_FORM_TYPES:
        members = [p for p in long_pages if p["page_type"] == page_type]
        hit = [p for p in members if len(p["raw"]["headings"]) < FEW_HEADINGS]
        if len(hit) >= 2 and len(hit) * 2 >= len(members):
            fired.append((page_type, hit, members))
    if not fired:
        out["passed"].append({"rule_id": "ANS-001", "summary":
                              "Long articles and documentation are sectioned: no long-form page type has most of its "
                              "long pages under %d headings (%s examined)"
                              % (FEW_HEADINGS, plural(len(long_pages), "long page"))})
        return
    for page_type, hit, members in fired:
        out["findings"].append({
            "id": "F-001",
            "title": "Long %s pages carry almost no section headings" % page_type,
            "evidence": "%d of %s of at least %d words have fewer than %d headings: %s."
                        % (len(hit), plural(len(members), "sampled %s page" % page_type), LONG_WORDS, FEW_HEADINGS,
                           "; ".join("%s (%d words, %s)" % (p["url"], p["text"]["word_count"],
                                                            plural(len(p["raw"]["headings"]), "heading"))
                                     for p in hit[:5])),
            "suggested_action": {
                "summary": "Divide long %s pages into sections under headings that name what each answers." % page_type,
                "what": "Divide the long %s pages into sections, each under a heading naming what the section "
                        "answers." % page_type,
                "where": "The %s template and the authoring guidelines behind the URLs cited." % page_type,
                "why": "Each heading becomes the label and the boundary of a retrievable passage.",
                "how": "Add h2 headings every few hundred words at real topic changes, phrased as the question or "
                       "claim the section addresses rather than a generic label, and give each an id so it can be "
                       "linked to directly.",
                "mechanism": "Passages that can be isolated and identified.",
                "success_criteria": "On each cited URL the headings divide the text so no section exceeds roughly "
                                    "500 words.",
                "effort": "medium",
            },
            "skill": SKILL,
            "rule_id": "ANS-001",
            "status": "proactive",
            "category": "discoverability",
            "symptom": ["invisible"],
            "confidence": "medium",
            "impact": {"blocking": False, "breadth": "section", "content_importance": "secondary"},
            "scope": {"pages_affected": len(hit), "pages_examined": len(members), "page_types": [page_type]},
            "evidence_refs": [{"url": p["url"], "observation": "%d words under %s"
                               % (p["text"]["word_count"], plural(len(p["raw"]["headings"]), "heading")),
                               "layer": p["provenance"]["layer"], "method": p["provenance"]["method"],
                               "retrieved_at": p["fetched_at"]} for p in hit],
            "false_positive_controls_applied": ["2xx pages only", "article and doc types only",
                                                "NewsArticle, ReportageNewsArticle and LiveBlogPosting excluded",
                                                "all headings counted, so boilerplate only lowers firing"],
            "exceptions_checked": ["news reporting house style: excluded by JSON-LD type",
                                   "deliberate continuous prose: undetectable, hence proactive"],
        })


RULES = (ans_001,)


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
    parser = argparse.ArgumentParser(description="Run the answerability rules over an evidence bundle.")
    parser.add_argument("--evidence", required=True, help="path to evidence/evidence.json")
    parser.add_argument("--out", required=True, help="path to write findings/answerability.json")
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
