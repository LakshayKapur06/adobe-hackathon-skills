"""Run one audit from the command line.

    python scripts/run_audit.py --url https://example.com --out runs/example/

A thin wrapper. It runs the entrypoint's own pipeline
(skills/audit-orchestrator/scripts/run.py) and then reformats the evidence for a
human reader. It orchestrates nothing the orchestrator does not already do, and
it derives nothing: every number printed is read straight from the bundle.

Standard library only.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE = os.path.join(ROOT, "skills", "audit-orchestrator", "scripts", "run.py")


def _cell(value):
    return "-" if value is None else str(value)


def _table(rows, headers):
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(headers)]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    out = [line, "  ".join("-" * w for w in widths)]
    out += ["  ".join(c.ljust(w) for c, w in zip(row, widths)) for row in rows]
    return "\n".join(out)


def summary_table(evidence):
    """One row per page: the bundle's own values, reformatted, nothing derived."""
    rows = []
    for page in evidence["pages"]:
        parts = urllib.parse.urlsplit(page["url"])
        types = list(dict.fromkeys(e["type"] for e in page["jsonld"] if e["type"]))
        rows.append([
            (parts.path or "/") + ("?" + parts.query if parts.query else ""),
            page["page_type"],
            _cell(page["raw"]["text_len"]),
            _cell(page["rendered"]["text_len"]),
            _cell(page["rendered"]["delta_ratio"]),
            ", ".join(types) or "-",
            str(len(page["raw"]["anchors"])),
        ])
    return _table(rows, ["url", "page_type", "raw.text_len", "rendered.text_len",
                         "delta_ratio", "jsonld types", "anchors"])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run one read-only website audit.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--out", required=True, help="run directory, for example runs/<slug>/")
    parser.add_argument("--collect-only", action="store_true", help="stop after the evidence bundle")
    parser.add_argument("--no-render", action="store_true", help="never use a browser")
    parser.add_argument("--no-egress", action="store_true", help="never contact third-party hosts")
    parser.add_argument("--max-pages", type=int, default=30, metavar="N")
    parser.add_argument("--summary", action="store_true", help="also print a per-page table")
    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    command = [sys.executable, PIPELINE, "--url", args.url, "--workdir", args.out,
               "--max-pages", str(args.max_pages)]
    for flag, on in (("--collect-only", args.collect_only), ("--no-render", args.no_render),
                     ("--no-egress", args.no_egress)):
        if on:
            command.append(flag)
    started = time.monotonic()
    status = subprocess.run(command).returncode
    elapsed = time.monotonic() - started
    if status != 0:
        print("audit failed (exit status %d) after %.1fs" % (status, elapsed))
        return status

    with open(os.path.join(args.out, "evidence", "evidence.json"), encoding="utf-8") as handle:
        evidence = json.load(handle)
    caps = evidence["run_context"]["capabilities"]
    degradations = evidence["run_context"]["degradations"]
    report_path = os.path.join(args.out, "report.json")
    if os.path.isfile(report_path):
        with open(report_path, encoding="utf-8") as handle:
            degradations = json.load(handle)["run_context"]["degradations"]
    print("%d/%d pages fetched/discovered | js_render=%s egress=%s | %.1fs | %d degradations | %s" % (
        evidence["crawl"]["fetched"], evidence["crawl"]["discovered"],
        "yes (%s)" % caps["renderer"] if caps["js_render"] else "no",
        "yes" if caps["egress"] else "no", elapsed, len(degradations),
        report_path if os.path.isfile(report_path) else os.path.join(args.out, "evidence")))
    if args.summary:
        print()
        print("origin: %s" % (evidence["site"]["resolved_origin"] or evidence["site"]["input"]))
        print(summary_table(evidence))
        if degradations:
            print()
            print("degradations:")
            for d in degradations:
                print("  [%s] %s -> %s" % (d["what"], d["reason"], d["impact"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
