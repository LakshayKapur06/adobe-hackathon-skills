"""The audit pipeline: observe, validate, diagnose, assemble, validate, write.

This is the entrypoint's Procedure (../SKILL.md, steps 2 to 8) as code. It is
the only thing that composes the other skills, and it composes them through
files: the collector writes evidence/, each diagnostic writes one file in
findings/, and this script turns those into report.json.

An invalid evidence bundle stops the run before any diagnostic reads it, and an
invalid report is never written. A diagnostic that has no rules yet is recorded
as a degradation, so an empty findings array can never be read as a clean site.

Standard library only.
"""

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)

import assemble_report  # noqa: E402
from jsonschema_lite import Validator  # noqa: E402

SCHEMAS = os.path.join(ROOT, "schemas")
COLLECTOR = os.path.join(ROOT, "skills", "site-evidence-collector", "scripts", "collect.py")
GLOBAL_DEADLINE_S = 300
DIAGNOSIS_RESERVE_S = 40       # the diagnosis-and-synthesis stage budget


def _registry():
    return {name: json.load(open(os.path.join(SCHEMAS, name), encoding="utf-8"))
            for name in ("evidence.schema.json", "finding.schema.json", "report.schema.json")}


def _validate(instance, schema_name, registry):
    return Validator(registry[schema_name], registry).errors(instance)


def _fail(message, details=()):
    sys.stderr.write("audit-orchestrator: %s\n" % message)
    for line in list(details)[:20]:
        sys.stderr.write("  %s\n" % line)
    return 1


def run(url, workdir, collect_only=False, no_render=False, no_egress=False, max_pages=30):
    started = time.monotonic()
    registry = _registry()
    os.makedirs(workdir, exist_ok=True)

    command = [sys.executable, COLLECTOR, "--url", url, "--workdir", workdir, "--max-pages", str(max_pages)]
    if no_render:
        command.append("--no-render")
    if no_egress:
        command.append("--no-egress")
    try:
        collected = subprocess.run(command, timeout=GLOBAL_DEADLINE_S - DIAGNOSIS_RESERVE_S)
    except subprocess.TimeoutExpired:
        return _fail("the collector exceeded the %ss global deadline" % (GLOBAL_DEADLINE_S - DIAGNOSIS_RESERVE_S))
    if collected.returncode != 0:
        return _fail("the collector failed with exit status %d" % collected.returncode)

    evidence_path = os.path.join(workdir, "evidence", "evidence.json")
    with open(evidence_path, encoding="utf-8") as handle:
        evidence = json.load(handle)
    problems = _validate(evidence, "evidence.schema.json", registry)
    if problems:
        return _fail("the evidence bundle is not schema-valid; no diagnostic will read it", problems)
    if collect_only:
        return 0

    findings_dir = os.path.join(workdir, "findings")
    os.makedirs(findings_dir, exist_ok=True)
    unruled = []
    for skill in assemble_report.DIAGNOSTIC_SKILLS:
        script = os.path.join(ROOT, "skills", skill, "scripts", "diagnose.py")
        if not os.path.isfile(script):
            unruled.append(skill)
            continue
        remaining = GLOBAL_DEADLINE_S - (time.monotonic() - started)
        subprocess.run([sys.executable, script, "--evidence", evidence_path,
                        "--out", os.path.join(findings_dir, skill + ".json")],
                       timeout=max(5, remaining), check=True)

    extra = []
    if unruled:
        extra.append({
            "what": "diagnosis",
            "reason": "no detection rules are defined yet for: %s" % ", ".join(unruled),
            "impact": "findings, not_assessed and checks_passed are empty for those skills because "
                      "nothing was evaluated, not because the site passed",
        })
    findings, not_assessed, checks_passed = assemble_report.read_findings(findings_dir)
    report = assemble_report.assemble(evidence, findings, not_assessed, checks_passed, extra)
    problems = _validate(report, "report.schema.json", registry)
    if problems:
        return _fail("the assembled report is not schema-valid; nothing was written", problems)
    with open(os.path.join(workdir, "report.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run one read-only website audit end to end.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--no-render", action="store_true")
    parser.add_argument("--no-egress", action="store_true")
    parser.add_argument("--max-pages", type=int, default=30)
    args = parser.parse_args(argv)
    return run(args.url, args.workdir, collect_only=args.collect_only, no_render=args.no_render,
               no_egress=args.no_egress, max_pages=args.max_pages)


if __name__ == "__main__":
    raise SystemExit(main())
