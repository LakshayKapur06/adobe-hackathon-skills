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
import re
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
PROMOTER = os.path.join(ROOT, "skills", "identity-and-markup", "scripts", "promote.py")
GLOBAL_DEADLINE_S = 300
DIAGNOSIS_RESERVE_S = 25       # the diagnosis-and-synthesis stage budget, CONTRACTS section 4


def rule_ids(skill):
    """The rule ids a diagnostic defines, read from its own rules.md."""
    path = os.path.join(ROOT, "skills", skill, "references", "rules.md")
    with open(path, encoding="utf-8") as handle:
        return re.findall(r"^### ([A-Z]{3}-\d{3}) ", handle.read(), re.M)


def _registry():
    registry = {}
    for name in ("evidence.schema.json", "finding.schema.json", "report.schema.json"):
        with open(os.path.join(SCHEMAS, name), encoding="utf-8") as handle:
            registry[name] = json.load(handle)
    return registry


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
    # -- pass 2 -----------------------------------------------------------------
    # D9's split, sequenced here because it is the only place that may compose
    # skills: the collector observed candidate strings, identity decides which
    # of them the site is actually asserting, and only then is there anything
    # worth asking the world about. The collector stays the single writer of
    # evidence.json; identity hands it a sidecar.
    claims_path = os.path.join(workdir, "evidence", "canonical_claims.json")
    remaining = GLOBAL_DEADLINE_S - DIAGNOSIS_RESERVE_S - (time.monotonic() - started)
    if remaining > 5:
        try:
            subprocess.run([sys.executable, PROMOTER, "--evidence", evidence_path,
                            "--out", claims_path], timeout=remaining, check=True)
            subprocess.run([sys.executable, COLLECTOR, "--corroborate", "--workdir", workdir]
                           + (["--no-egress"] if no_egress else []),
                           timeout=max(5, remaining), check=True)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
            # Pass 2 is corroboration, not observation. Losing it costs breadth
            # and must never cost the run: pass 1 already stands on its own.
            sys.stderr.write("audit-orchestrator: pass 2 did not complete (%s)\n" % exc)
        with open(evidence_path, encoding="utf-8") as handle:
            evidence = json.load(handle)
        problems = _validate(evidence, "evidence.schema.json", registry)
        if problems:
            return _fail("the evidence bundle is not schema-valid after pass 2", problems)

    if collect_only:
        return 0

    findings_dir = os.path.join(workdir, "findings")
    os.makedirs(findings_dir, exist_ok=True)
    unruled, failed = [], []
    for skill in assemble_report.DIAGNOSTIC_SKILLS:
        script = os.path.join(ROOT, "skills", skill, "scripts", "diagnose.py")
        out_path = os.path.join(findings_dir, skill + ".json")
        if not os.path.isfile(script):
            unruled.append(skill)
            continue
        remaining = GLOBAL_DEADLINE_S - (time.monotonic() - started)
        try:
            subprocess.run([sys.executable, script, "--evidence", evidence_path, "--out", out_path],
                           timeout=max(5, remaining), check=True)
            with open(out_path, encoding="utf-8") as handle:
                json.load(handle)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError, ValueError) as exc:
            # One diagnostic failing must not cost the other five their report
            # (CONTRACTS section 4: never fail the whole run). Its rules are
            # reported as not assessed, by id, so nothing reads as a pass.
            failed.append((skill, exc))
            if os.path.exists(out_path):
                os.remove(out_path)

    extra, failed_not_assessed = [], []
    for skill, exc in failed:
        reason = "budget_exhausted" if isinstance(exc, subprocess.TimeoutExpired) else             "the %s diagnostic did not complete (%s)" % (skill, type(exc).__name__)
        extra.append({"what": "diagnosis", "reason": "%s: %s" % (skill, reason),
                      "impact": "every %s rule is reported as not assessed" % skill})
        for rule_id in rule_ids(skill):
            failed_not_assessed.append({"rule_id": rule_id, "reason": reason,
                                        "enable_hint": "re-run the audit; if it recurs, run skills/%s/scripts/"
                                                       "diagnose.py directly to see the error" % skill})
    if unruled:
        extra.append({
            "what": "diagnosis",
            "reason": "no detection rules are defined yet for: %s" % ", ".join(unruled),
            "impact": "findings, not_assessed and checks_passed are empty for those skills because "
                      "nothing was evaluated, not because the site passed",
        })
    findings, not_assessed, checks_passed = assemble_report.read_findings(findings_dir)
    report = assemble_report.assemble(evidence, findings, not_assessed + failed_not_assessed, checks_passed, extra)
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
