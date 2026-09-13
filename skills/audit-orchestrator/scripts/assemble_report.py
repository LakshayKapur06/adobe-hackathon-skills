"""Assemble the single audit report from the evidence bundle and the findings.

This is step 8 of the orchestrator procedure. It performs no detection of its
own: it merges what the diagnostics wrote, deduplicates, derives severity and
priority, orders the result the way a reader acts on it, and emits one report.

Deterministic by construction. Nothing here depends on filesystem ordering,
dict insertion order, wall-clock time or set iteration: inputs are read in
sorted filename order, findings are sorted by an explicit total order, and every
timestamp in the output comes from the evidence bundle rather than from the
clock. Two runs over the same evidence produce byte-identical reports.

Standard library only.
"""

import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import arbitrate as arb_mod  # noqa: E402  (path is set immediately above)
import proactive as pro_mod  # noqa: E402
import severity as sev_mod  # noqa: E402

DIAGNOSTIC_SKILLS = (
    "access-and-indexability",
    "render-and-extraction",
    "identity-and-markup",
    "answerability",
    "freshness-and-corroboration",
    "arrival-and-engagement",
)

TS = "%Y-%m-%dT%H:%M:%SZ"


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def read_findings(findings_dir):
    """Read every diagnostic's output in sorted filename order."""
    findings, not_assessed, checks_passed = [], [], []
    if not os.path.isdir(findings_dir):
        return findings, not_assessed, checks_passed
    for name in sorted(os.listdir(findings_dir)):
        if not name.endswith(".json"):
            continue
        stem = name[: -len(".json")]
        if stem not in DIAGNOSTIC_SKILLS:
            raise ValueError(
                "%s is not a diagnostic skill; findings/ may only contain one file "
                "per skill listed in marketplace.json" % (name,)
            )
        doc = load_json(os.path.join(findings_dir, name))
        for f in doc.get("findings", []):
            if f.get("skill") != stem:
                raise ValueError(
                    "finding %s in %s declares skill %r; a diagnostic may only emit "
                    "its own findings" % (f.get("id"), name, f.get("skill"))
                )
            findings.append(f)
        not_assessed.extend(doc.get("not_assessed", []))
        checks_passed.extend(doc.get("checks_passed", []))
    return findings, not_assessed, checks_passed


def dedupe_key(finding):
    """One root cause, one finding.

    The same rule firing over the same page types and the same observed URLs is
    one finding. The same rule firing on two page types stays two findings with
    honest denominators, because collapsing them would overstate breadth.
    """
    return (
        finding["rule_id"],
        tuple(sorted(finding.get("scope", {}).get("page_types", []))),
        tuple(sorted(ref["url"] for ref in finding.get("evidence_refs", []))),
    )


def deduplicate(findings):
    seen = {}
    for f in findings:
        seen.setdefault(dedupe_key(f), f)
    return list(seen.values())


def parse_ts(value):
    return datetime.datetime.strptime(value, TS).replace(tzinfo=datetime.timezone.utc)


def build_run_context(evidence, extra_degradations=()):
    """The report's run_context: what was observed, with what, and what was not.

    ``extra_degradations`` are the orchestrator's own, such as a diagnostic that
    has no rules yet, appended after the collector's so that an empty findings
    array can never be mistaken for a clean site.
    """
    rc = evidence["run_context"]
    started, finished = parse_ts(rc["started_at"]), parse_ts(rc["finished_at"])
    crawl = evidence["crawl"]
    external = evidence["external"]
    return {
        "started_at": rc["started_at"],
        "finished_at": rc["finished_at"],
        "elapsed_s": round((finished - started).total_seconds(), 3),
        "capabilities": dict(rc["capabilities"]),
        "crawl": {
            "discovered": crawl["discovered"],
            "fetched": crawl["fetched"],
            "blocked_by_robots": crawl["blocked_by_robots"],
            "errors": crawl["errors"],
        },
        "sampling": json.loads(json.dumps(crawl["sampling"])),
        "degradations": json.loads(json.dumps(rc["degradations"])) + [dict(d) for d in extra_degradations],
        "corroboration": {
            "method": rc["corroboration"]["method"],
            "attempted": external["attempted"],
            "frontier_size": external["frontier_size"],
            "truncated": external["truncated"],
            "provider_unavailable": list(rc["corroboration"]["provider_unavailable"]),
        },
    }


def report_order(finding):
    """Priority, then observed before proactive, then unconditional before conditional.

    Within one priority band an observed defect or risk is always listed before
    a proactive recommendation, so a speculative idea never reads as more urgent
    than something actually wrong. A conditional finding keeps its own severity
    but follows the findings it does not depend on, so a reader working down the
    list meets the upstream fix before the work it conditions.
    """
    key = sev_mod.sort_key(finding)
    return (key[0], 1 if finding["status"] == "proactive" else 0,
            1 if finding.get("conditional_on") else 0) + key[1:]


def assemble(evidence, findings, not_assessed, checks_passed, extra_degradations=()):
    extra_degradations = list(extra_degradations)
    proactive, pro_not_assessed, pro_passed = pro_mod.recommend(evidence)
    not_assessed = list(not_assessed) + pro_not_assessed
    checks_passed = list(checks_passed) + pro_passed
    findings = deduplicate(list(findings) + proactive)
    derived = []
    for f in findings:
        try:
            sev_mod.derive(f)
        except ValueError as exc:
            # An authoring error in a rule must never reach a report, and must
            # never take the whole run down with it either. The finding is
            # withheld and the withholding is stated.
            extra_degradations.append({
                "what": "diagnosis",
                "reason": "a %s finding was withheld because its declared inputs violate the status semantics: %s"
                          % (f.get("rule_id", "unknown"), exc),
                "impact": "%s is not reported for this run; the rule needs correcting" % f.get("rule_id", "the rule"),
            })
            continue
        derived.append(f)
    findings = arb_mod.arbitrate(derived)
    findings.sort(key=report_order)

    # Identifiers are assigned after ordering so the report reads F-001 downward
    # in the order a reader should act, and so two runs over the same evidence
    # produce the same identifiers.
    for index, f in enumerate(findings, start=1):
        f["id"] = "F-%03d" % index

    # The handout separates "problems found" from suggested actions that "go
    # beyond the detected problems". A proactive recommendation is the second
    # kind, so it never counts as a problem: a well-built site with one optional
    # suggestion reports zero findings and one proactive item (contracts-v13).
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    problems = [f for f in findings if f["status"] != "proactive"]
    for f in problems:
        counts[f["severity"]] += 1

    site = evidence["site"].get("registrable_domain") or evidence["site"]["input"]

    return {
        "site": site,
        "audited_at": evidence["run_context"]["started_at"],
        "summary": dict(counts, total_findings=len(problems), proactive=len(findings) - len(problems)),
        "findings": findings,
        "not_assessed": sorted(
            (dict(n) for n in not_assessed), key=lambda n: (n["rule_id"], n["reason"])
        ),
        "checks_passed": sorted(
            (dict(c) for c in checks_passed), key=lambda c: (c["rule_id"], c["summary"])
        ),
        "run_context": build_run_context(evidence, extra_degradations),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--evidence", required=True, help="path to evidence.json")
    ap.add_argument("--findings", required=True, help="directory of per-skill findings files")
    ap.add_argument("--out", required=True, help="path to write report.json")
    args = ap.parse_args(argv)

    evidence = load_json(args.evidence)
    findings, not_assessed, checks_passed = read_findings(args.findings)
    report = assemble(evidence, findings, not_assessed, checks_passed)

    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(report, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
