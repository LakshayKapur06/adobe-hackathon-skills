"""Render report.json as report.md: the same audit, written for the person who fixes it.

report.json is the contract; this is a view of it. Every sentence here comes from
a field of the report, rendered in a fixed order, so the Markdown is as
deterministic as the JSON and says nothing the JSON does not. It is written for a
non-expert: problems first, in the order to act on them, each with what was seen,
why it matters, what to do, where, how, and how to tell it worked; then the
improvements that go beyond the problems; then what was checked and passed, what
could not be checked and how to make it checkable, and how the audit was run.

Observed content never becomes an instruction here. Evidence strings are quoted
as observations, collapsed onto one line so that nothing a site wrote can
restructure this document.

Standard library only.
"""

import argparse
import json
import os

PRIORITY_MEANING = {
    "P0": "fix first: it blocks a stage of being found or used",
    "P1": "fix next",
    "P2": "plan it in",
    "P3": "when convenient",
}
CATEGORY = {"discoverability": "Being found and cited by AI assistants", "engagement": "Keeping visitors who arrive"}


def _line(text):
    return " ".join(str(text).split())


def _count(n, singular, plural):
    return "%d %s" % (n, singular if n == 1 else plural)


def _finding(number, finding):
    action = finding["suggested_action"]
    out = ["### %d. %s" % (number, _line(finding["title"])), "",
           "**%s** · priority **%s** (%s) · %s · confidence %s · effort %s" % (
               finding["severity"].capitalize(), action["priority"], PRIORITY_MEANING[action["priority"]],
               CATEGORY[finding["category"]], finding["confidence"], action["effort"]), ""]
    for condition in finding.get("conditional_on", []):
        out += ["> **Fix %s first.** %s" % (condition["rule_id"], _line(condition["reason"])), ""]
    out += ["- **What we saw:** %s" % _line(finding["evidence"]),
            "- **Why it matters:** %s" % _line(action["why"]),
            "- **What improves:** %s" % _line(action["mechanism"]),
            "- **What to do:** %s" % _line(action["what"]),
            "- **Where:** %s" % _line(action["where"]),
            "- **How:** %s" % _line(action["how"]),
            "- **How you will know it worked:** %s" % _line(action["success_criteria"])]
    urls = sorted({ref["url"] for ref in finding["evidence_refs"]})
    shown = ", ".join(urls[:5]) + (" and %d more" % (len(urls) - 5) if len(urls) > 5 else "")
    scope = finding["scope"]
    counted = (" (%s of %s examined)" % (scope["pages_affected"], scope["pages_examined"])
               if scope["pages_examined"] else "")
    out += ["- **Pages behind this:** %s%s · rule %s" % (shown, counted, finding["rule_id"]), ""]
    return out


def render(report):
    summary = report["summary"]
    run = report["run_context"]
    problems = [f for f in report["findings"] if f["status"] != "proactive"]
    proactive = [f for f in report["findings"] if f["status"] == "proactive"]
    capabilities = run["capabilities"]
    out = ["# AI-readiness audit: %s" % report["site"], "",
           "Audited %s. %d of %d discovered pages sampled; %s; %s; %s seconds." % (
               report["audited_at"], run["crawl"]["fetched"], run["crawl"]["discovered"],
               "a browser rendered pages" if capabilities["js_render"] else "no browser was available",
               "off-site sources were consulted" if run["corroboration"]["attempted"] else "no off-site sources were consulted",
               run["elapsed_s"]), "",
           "## At a glance", "",
           "- **%s found:** %d critical, %d high, %d medium, %d low." % (
               _count(summary["total_findings"], "problem", "problems"), summary["critical"], summary["high"],
               summary["medium"], summary["low"]),
           "- **%s** that go beyond the problems." % _count(summary["proactive"], "suggested improvement",
                                                          "suggested improvements"),
           "- **%s passed**, and **%s** on this run (listed at the end, with what would make them checkable)." % (
               _count(len(report["checks_passed"]), "check", "checks"),
               _count(len(report["not_assessed"]), "could not be assessed", "could not be assessed")), ""]
    if run["degradations"]:
        out += ["This run had limits that narrow what it could see: %s." % "; ".join(
            "%s: %s" % (d["what"], _line(d["reason"])) for d in run["degradations"]), ""]
    out += ["## Problems, in the order to fix them", ""]
    if problems:
        for number, finding in enumerate(problems, start=1):
            out += _finding(number, finding)
    else:
        out += ["No problem was found by any check that could run. That is a statement about the checks listed "
                "below, not about checks this run could not make.", ""]
    out += ["## Suggested improvements beyond the problems", ""]
    if proactive:
        for number, finding in enumerate(proactive, start=1):
            out += _finding(number, finding)
    else:
        out += ["None for this site.", ""]
    out += ["## Checks that passed", ""]
    out += ["- **%s:** %s" % (c["rule_id"], _line(c["summary"])) for c in report["checks_passed"]] or ["None."]
    out += ["", "## What could not be checked, and how to make it checkable", ""]
    out += ["- **%s:** %s. *To enable:* %s" % (n["rule_id"], _line(n["reason"]), _line(n["enable_hint"]))
            for n in report["not_assessed"]] or ["Everything was checked."]
    out += ["", "## How this audit was run", "",
            "- Read-only: every request was a GET, robots.txt was obeyed for this site and for every other site "
            "consulted, and nothing on the site was changed.",
            "- Sampling: %s; %s." % (run["sampling"]["strategy"], ", ".join(
                "%s %d of %d" % (s["page_type"], s["sampled"], s["discovered"]) for s in run["sampling"]["strata"])
                or "no pages"),
            "- Off-site coverage: %s, over %d enumerable sources. This is not a search of the whole web." % (
                run["corroboration"]["method"], run["corroboration"]["frontier_size"]),
            "- Severity is computed from what was observed (whether a stage is blocked, how widely, and how "
            "central the content is), capped by confidence; it is never assigned by hand.", ""]
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render report.json as a readable report.md.")
    parser.add_argument("--report", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    with open(args.report, encoding="utf-8") as handle:
        report = json.load(handle)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
