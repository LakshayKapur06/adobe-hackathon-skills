"""arrival-and-engagement: the rule in ../references/rules.md, as code.

Reads evidence/evidence.json and nothing else, and writes one findings file
holding ``findings``, ``not_assessed`` and ``checks_passed``. The rule block
holds the reasons for the threshold, and ``references/rules.md`` records the
arrival checks that were measured and cut. ``severity`` and
``suggested_action.priority`` are never set; the orchestrator derives them.

Latency is an engagement signal here and never a discoverability one.

Standard library only. No imports from any other skill.
"""

import argparse
import json
import os
import statistics

SKILL = "arrival-and-engagement"
SUPPORTED_SCHEMA_MAJOR = "1"

POOR_TTFB_MS = 1800
MIN_PAGES = 5


def is_2xx(status):
    return isinstance(status, int) and 200 <= status <= 299


def server_ms(page):
    """Time to first byte minus the request's own connection setup."""
    timing = page["timing"]
    return timing["ttfb_ms"] - (timing["connect_ms"] or 0)


def arr_001(evidence, out):
    timed = [p for p in evidence["pages"] if is_2xx(p["status"]) and p["timing"]["ttfb_ms"] is not None]
    if len(timed) < MIN_PAGES:
        out["not_assessed"].append({"rule_id": "ARR-001", "reason":
                                    "2xx pages with a recorded time to first byte: %d; %d are needed for a median"
                                    % (len(timed), MIN_PAGES),
                                    "enable_hint": "needs at least 5 sampled pages that answer this client"})
        return
    ordered = sorted(timed, key=lambda p: (server_ms(p), p["url"]))
    median = statistics.median(server_ms(p) for p in timed)
    fastest, slowest = ordered[0], ordered[-1]
    if median <= POOR_TTFB_MS:
        out["passed"].append({"rule_id": "ARR-001", "summary":
                              "Median server response time (time to first byte minus connection setup) is %d ms "
                              "across %d pages, within web.dev's 1,800 ms poor boundary" % (round(median), len(timed))})
        return
    slow = [p for p in ordered if server_ms(p) > POOR_TTFB_MS]
    out["findings"].append({
        "id": "F-001",
        "title": "The server is slow to send the first byte",
        "evidence": "Median server response time (time to first byte minus DNS, TCP and TLS setup) across %d "
                    "sampled 2xx pages is %d ms, above web.dev's 1,800 ms poor boundary; %d of them exceed it. "
                    "Slowest %s at %d ms, fastest %s at %d ms. Measured from one auditing client."
                    % (len(timed), round(median), len(slow), slowest["url"], round(server_ms(slowest)),
                       fastest["url"], round(server_ms(fastest))),
        "suggested_action": {
            "summary": "Confirm with field TTFB data, then cache HTML at the edge and speed up the slowest templates.",
            "what": "Confirm the delay with field data, then reduce server response time on the slowest templates.",
            "where": "The origin server and CDN configuration for the URLs cited, starting with %s." % slowest["url"],
            "why": "Every visible milestone waits on the first byte.",
            "how": "Check real-user TTFB in the site's analytics or the Chrome UX Report; if it is also poor, cache "
                   "rendered HTML at a CDN edge, profile the slowest templates' server work, and serve static routes "
                   "statically.",
            "mechanism": "Time until an arriving visitor sees anything.",
            "success_criteria": "The 75th-percentile field TTFB is at or below 800 ms, or a re-run of this audit "
                                "records a median below 1,800 ms.",
            "effort": "medium",
        },
        "skill": SKILL, "rule_id": "ARR-001", "status": "risk", "category": "engagement",
        "symptom": ["bounce"], "confidence": "low",
        "impact": {"blocking": False, "breadth": "site", "content_importance": "secondary"},
        "scope": {"pages_affected": len(slow), "pages_examined": len(timed),
                  "page_types": sorted({p["page_type"] for p in slow})},
        "evidence_refs": [{"url": p["url"], "observation": "time to first byte %d ms, of which connection setup %s ms"
                           % (round(p["timing"]["ttfb_ms"]), p["timing"]["connect_ms"]),
                           "layer": p["provenance"]["layer"], "method": p["provenance"]["method"],
                           "retrieved_at": p["fetched_at"]} for p in slow[-10:]],
        "false_positive_controls_applied": ["2xx pages only", "median, not mean or maximum",
                                            "timer starts after any crawl-delay wait",
                                            "connection setup subtracted, so client network stalls do not count"],
        "exceptions_checked": ["client distance and per-request connection setup: undetectable, hence risk at low "
                               "confidence against the poor boundary"],
    })


RULES = (arr_001,)


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
    parser = argparse.ArgumentParser(description="Run the arrival-and-engagement rules over an evidence bundle.")
    parser.add_argument("--evidence", required=True, help="path to evidence/evidence.json")
    parser.add_argument("--out", required=True, help="path to write findings/arrival-and-engagement.json")
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
