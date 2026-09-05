---
name: audit-orchestrator
description: >-
  Entrypoint for the agent-readiness marketplace. Given a website URL, runs the
  observation skill once, dispatches the six mechanism diagnostics against the
  shared evidence bundle, then merges, deduplicates, derives severity and
  priority, and emits a single audit report of findings plus prioritised
  suggested actions covering both AI discoverability and on-site engagement.
  Use when asked to audit, diagnose or score a website for why AI assistants
  miss, misstate or under-cite a brand, or why arriving visitors fail to
  complete their task. Recommend-only: never modifies the audited site.
license: Apache-2.0
allowed-tools: Read, Write, Bash
---

# Audit Orchestrator

The single entrypoint. It owns composition, arbitration and output design. It
owns no detection rules of its own.

## When to use

Use this skill when the request is "audit this website", "why is this brand
invisible to AI assistants", "why does this site lose visitors who arrive", or
any request for a readiness report on a site you have not seen before.

Do not use the diagnostic skills directly for a full audit: they read a shared
evidence bundle that only `site-evidence-collector` may produce, and a report
assembled without this skill will have unarbitrated duplicates and
hand-assigned severities.

## Inputs

| Input | Required | Notes |
|---|---|---|
| `site` | yes | A URL or bare domain. Scheme optional; the collector resolves it. |
| `workdir` | no | Working directory for all artefacts. Defaults to `./audit-run`. |
| `budget_s` | no | Global deadline in seconds. Defaults to 300. |

Nothing else is required. No API key, no account, no configuration.

## Procedure

1. **Establish the working directory.** Create `workdir` and treat it as the
   only place anything is written. Never write to, post to, or authenticate
   against the audited site. See `references/composition.md` for the exact file
   contract between skills.

2. **Observe once.** Invoke `site-evidence-collector` with `site` and `workdir`.
   It performs the robots gate, the first-party crawl, capability probing and
   the off-site probe, and writes `workdir/evidence/evidence.json`. No other
   skill is permitted to fetch anything. If the collector reports that robots
   disallows us at the origin, stop and emit a report whose only content is that
   fact — never fall back to fetching anyway.

3. **Diagnose in dependency order.** Run the six diagnostics against the same
   evidence bundle. Ordering is a design output, not an implementation detail
   (`references/composition.md` explains why): access and indexability, then
   render and extraction, then identity and markup, then answerability,
   freshness and corroboration, and arrival and engagement. Identity runs before
   corroboration because an ambiguous brand name poisons external matching and
   therefore gates corroboration confidence. Each diagnostic writes
   `workdir/findings/<skill-id>.json` and touches nothing else.

4. **Arbitrate.** Merge the finding sets and resolve overlap using the rules in
   `references/composition.md`: one root cause yields one finding, held by the
   skill that owns the mechanism, with the downstream symptom recorded as
   evidence rather than as a second finding.

5. **Derive severity and priority.** Diagnostics declare observed impact inputs
   (`blocking`, `breadth`, `content_importance`), `confidence`, `effort` and
   `status`. This skill computes `severity` and `priority` from them with
   `scripts/severity.py`. Severity is never hand-assigned by a diagnostic, and
   is a function of observables only — it never encodes a predicted change in
   AI citation rates, which we cannot observe.

6. **Account for what was not assessed.** Every rule that could not run —
   no browser, no egress, budget exhausted, minimum evidence unmet — is recorded
   in `not_assessed` with the reason and the one-line command that would enable
   it. Absence of observation is never reported as absence of a problem.

7. **Add proactive recommendations.** Emit strengthening actions that are
   warranted by the evidence even where no defect was found, marked
   `status: proactive`. These never exceed `medium` severity and are always
   `P2` or `P3`, so they cannot crowd out a real defect.

8. **Assemble and validate.** Build the report with
   `scripts/assemble_report.py` and validate it against
   `../../schemas/report.schema.json` before returning it. An invalid report is
   a failure, not a partial success.

## Output

One file, `workdir/report.json`, conforming to `../../schemas/report.schema.json`.
It contains `site`, `audited_at`, a counts-by-severity `summary`, the `findings`
array (each with `id`, `title`, `severity`, `evidence` and a
`suggested_action` carrying `summary` and `priority`), plus `not_assessed`,
`checks_passed` and a `run_context` block stating what was crawled against what
was discovered, the sampling strategy, the capabilities available and every
degradation. `not_assessed` and `checks_passed` are separate arrays so neither
inflates `total_findings`.

The `run_context` block is not decoration. It is what lets a reader check
whether a finding was drawn from three pages or thirty.

## Guardrails

Recommend-only, read-only, no authenticated or destructive actions, no form
submission, no clicking. robots.txt is respected for the audited domain and for
every third-party domain touched. All writes go to `workdir`.
