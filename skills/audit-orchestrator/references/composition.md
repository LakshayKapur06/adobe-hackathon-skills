# Composition — how the entrypoint assembles eight skills into one report

This file is the contract between skills. It is deliberately a *file* contract,
not a tool contract: any host that can run a script and read a directory can run
this marketplace, and no skill depends on a host-specific capability.

## The layers

```
audit-orchestrator            entrypoint: composition, arbitration, output
   |
   +-- site-evidence-collector    the only skill that touches the network
   |        writes  evidence/evidence.json
   |
   +-- six mechanism diagnostics  read that bundle, write findings/<id>.json
```

Observation is separated from judgement for one reason: two skills that each
fetch the same page can disagree about it, and an auditor that contradicts
itself is worse than one that misses something. There is exactly one writer of
observed facts.

## The file contract

| Path | Written by | Read by | Schema |
|---|---|---|---|
| `evidence/evidence.json` | `site-evidence-collector` | all six diagnostics | `schemas/evidence.schema.json` |
| `evidence/pages/<sha256>.txt` | `site-evidence-collector` | diagnostics needing page text | plain text; length and hash are in the bundle |
| `evidence/evidence.json` key `canonical_claims` | `identity-and-markup` | `freshness-and-corroboration`, collector pass 2 | same |
| `findings/<skill-id>.json` | each diagnostic | orchestrator | `schemas/finding.schema.json` per element |
| `report.json` | orchestrator | the caller | `schemas/report.schema.json` |

Nothing else crosses a skill boundary. No skill imports code from another skill.
Every skill folder stays independently valid if lifted out on its own.

## Ordering, and why it is a design output rather than a loop

1. `access-and-indexability` — the admission gate. If a machine cannot reach the
   content, every later finding is conditional on fixing this one first, and the
   report says so.
2. `render-and-extraction` — the readability gate. Whether the substance is in
   the response at all bounds what any content rule can legitimately claim.
3. `identity-and-markup` — establishes what the brand claims to be, and promotes
   claim candidates to canonical claims.
4. `answerability` — the quotability gate, over content now known to be present.
5. `freshness-and-corroboration` — tests the canonical claims from step 3
   against the off-site evidence. It runs after identity because an ambiguous
   brand name poisons external matching: a low-confidence identity caps the
   confidence of every corroboration finding derived from it.
6. `arrival-and-engagement` — the human half, independent of the first five.

Steps 1, 2, 4 and 6 could in principle run concurrently; the dependency that
actually matters is 3 before 5.

## Two-pass observation

The collector runs in two passes because claim promotion sits between them:

- **Pass 1** — robots gate, capability probe, first-party crawl, extraction, and
  deterministic emission of `claim_candidates` (strings with provenance, no
  interpretation).
- **Promotion** — `identity-and-markup` turns candidates into
  `canonical_claims`, with `first_party_confidence` and `entity_ambiguity`.
- **Pass 2** — the off-site probe, seeded by those canonical claims.

Without this split, either the collector would have to interpret (which is a
judgement, and judgement belongs to diagnostics) or corroboration would have to
fetch (which would break the single-observer rule).

## Arbitration

Diagnostics overlap by design at the *symptom* level and are disjoint at the
*mechanism* level. When two findings describe the same underlying cause:

1. **One root cause, one finding.** Keep the finding from the skill that owns
   the causal mechanism, upstream-most in the ordering above.
2. **The downstream observation becomes evidence, not a second finding.** If
   prices are missing from server HTML *and* the product pages are also
   `nosnippet`, the access finding is the finding; the extraction observation is
   recorded in its `evidence_refs`.
3. **Suppress conditional findings under a blocking upstream one.** If robots
   disallows every AI crawler at the origin, content-shape findings are still
   reported but explicitly marked as conditional on the access fix, because
   fixing them first would change nothing.
4. **Never merge severities.** Severity is recomputed from the surviving
   finding's own impact inputs. Two medium findings never become a high.
5. **Deduplicate by `(rule_id, scope.page_types, evidence_refs[].url)`.** The
   same rule firing on two page types is two findings with honest denominators,
   not one aggregate that overstates breadth.

## Derived fields

Diagnostics declare observations. The orchestrator derives judgements.

| Field | Declared by | Derived by |
|---|---|---|
| `impact.blocking`, `impact.breadth`, `impact.content_importance` | diagnostic | — |
| `confidence`, `status`, `suggested_action.effort` | diagnostic | — |
| `severity` | — | orchestrator, `scripts/severity.py` |
| `suggested_action.priority` | — | orchestrator, `scripts/severity.py` |

Keeping severity in one place is what makes the truth table testable and stops
six skills drifting into six severity dialects.

## Degradation

The audit is designed to be useful with no browser and no egress. Capability is
a matrix — JS rendering and third-party egress are independent — not a ladder.

| Missing | Effect |
|---|---|
| JS renderer | Render-delta rules become `not_assessed` with an enabling hint. Every other rule is unaffected. |
| Third-party egress | Corroboration rules become `not_assessed`. The whole on-site half still runs and still produces a complete report. |
| Both | The report covers access, extraction from server HTML, identity, answerability, on-site freshness and engagement. |

An unmade observation is never reported as a clean result. That is the
difference between an audit and a compliment.

## Budgets

The global deadline is 300 seconds, enforced here. On expiry, whatever completed
is reported and the remainder becomes `not_assessed` with reason
`budget_exhausted`. The run never fails as a whole. Per-stage budgets are in
`skills/site-evidence-collector/references/budgets.md`.

## Sandboxing

The orchestrator states that all skills run in one working directory. If a host
runs skills in isolated sandboxes with no shared filesystem, the orchestrator
executes the diagnostics' scripts itself within its own working directory; the
file contract above is unchanged either way.
