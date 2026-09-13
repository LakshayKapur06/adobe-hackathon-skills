# Where each rubric criterion is met

The handout grades the marketplace itself, not any one report. This page maps
each of its six criteria to the files that answer it, so every claim below can
be checked in the repository rather than taken on trust.

## Detection accuracy

*Correctly identifies the real problems (evidence-backed) across both
discoverability and engagement, with few misses and few false positives.*

| What answers it | Where |
|---|---|
| 20 rules across six mechanisms, each in one 14-field block: mechanism, signal, evidence read, justified threshold, minimum evidence, false-positive controls, legitimate exceptions, confidence, impact, status, remediation, success criteria | `skills/*/references/rules.md` |
| Every rule names only evidence fields that exist in the schema and that its skill may read; the build gate fails otherwise, and a recorder proves the code reads nothing else | `scripts/check.py` (evidence-fields), `tests/test_archetypes.py` (`TestScriptsReadOnlyTheirAllowList`) |
| Every page-content rule requires a 2xx response, so an error page is never judged as content | each `rules.md`, **Signal** |
| A check that could not run is reported as not assessed with what would enable it, never as a pass | `schemas/report.schema.json` (`not_assessed`), `tests/test_runner.py` |
| Findings a site might legitimately intend are reported as consequences, not defects: a named AI crawler opt-out in robots.txt is `proactive`, and a user-agent refusal that cannot be told apart from a CDN verifying crawlers by address is a low-confidence `risk` | `skills/access-and-indexability/references/rules.md` (ACC-006, ACC-008) |
| Checks that were measured on real sites, produced false positives on healthy pages, and were cut, with the measurement | each `rules.md`, sections on what was cut |
| The collector's observations compared page by page with pages a person saved from a browser | `tests/g2-evidence-check.md` |
| Every claim a rule makes about how an operator's crawler behaves, checked against that operator's documentation | `tests/rule-review.md` |
| False positives found on live sites turned into tests that keep them fixed: a free app's zero price read as a contradicted price, a client network stall read as a slow server | `tests/test_identity_rules.py`, `tests/test_arrival_rules.py`, `docs/DECISIONS.md` |

Engagement is deliberately narrow: one latency rule. Task completion,
interstitials, anchors, above-the-fold completeness and orphan pages were
measured and cut because the evidence a read-only audit can gather could not
separate defects from healthy designs (`skills/arrival-and-engagement/references/rules.md`).
Under this rubric a false positive costs more than a miss.

## Suggested-action quality

*Fixes are correctly targeted, mechanism-sound, and prioritized; beyond-problem
suggestions are relevant and non-obvious.*

| What answers it | Where |
|---|---|
| Every action states what to change, where (the template, header rule or file behind the cited URLs), why, how, the mechanism it improves, how to tell it worked, and the effort | `schemas/finding.schema.json` (`suggested_action`), `samples/*/report.md` |
| Priority P0 to P3 is derived, never hand-assigned, from whether a stage is blocked, how widely, how central the content is, capped by confidence, and checked by a 324-case truth table | `docs/CONTRACTS.md`, `tests/test_severity.py` |
| One root cause, one fix: a finding explained by an upstream one is marked `conditional_on` it and ordered after it | `skills/audit-orchestrator/references/composition.md`, `tests/test_orchestrator.py` |
| Four proactive recommendations, each triggered by something observed on this site and none restating a defect: identity links for organization markup that has none, structured dates for articles that only show them, a fixed prompt panel built from the site's own verified facts, and `/llms.txt` labelled as speculative | `skills/audit-orchestrator/references/proactive.md` |
| Advice that is common and wrong is not given: `llms.txt` is not called a defect, page speed is not claimed to affect AI citation, and FAQ markup is not recommended | `docs/DECISIONS.md` (D-table exclusions, D28), `skills/arrival-and-engagement/references/rules.md` |

## Output design

*A clear, structured, actionable report (evidence + severity + prioritized
actions) a non-expert could act on.*

| What answers it | Where |
|---|---|
| `report.md`: problems in the order to fix them, each with what was seen, why it matters, what to do, where, how and how to tell it worked; improvements beyond the problems; checks that passed; what could not be checked and how to make it checkable; how the audit was run | `skills/audit-orchestrator/scripts/render_report.py`, `samples/*/report.md` |
| `report.json`: the handout's required shape and more, validated against a schema before it is written | `schemas/report.schema.json` |
| The summary counts problems only; proactive recommendations are counted apart, so a healthy site does not appear to have problems | `docs/DECISIONS.md` (D27) |
| Every finding cites the URLs and the observation it was drawn from, and the evidence bundle ships with the report | `evidence_refs` in each finding, `samples/*/evidence/` |

## Skill-format and engineering hygiene

*Each skill folder is agentskills.io compliant; the manifest is well-formed with
exactly one entrypoint; deterministic; safe.*

| What answers it | Where |
|---|---|
| Eight skill folders, each with SKILL.md frontmatter (name, description, license, allowed-tools) and When to use, Inputs, Procedure and Output sections; exactly one entrypoint | `marketplace.json`, `scripts/check.py` (manifest, skills, references) |
| Deterministic: the same fixture twice gives identical output but for clocks | `scripts/check.py` (determinism) |
| Standard library only, no cross-skill imports, no unfinished-work markers | `scripts/check.py` (stdlib-only, isolation, no-placeholders) |
| Read-only GET requests, robots.txt obeyed for the audited site and for every third-party host, including Wikipedia and Wikidata | `skills/site-evidence-collector/references/providers.md`, `tests/test_robots.py`, `tests/test_corroboration.py` |
| Observed content is data: a Shopify robots.txt comment addressed to AI agents is fetched on every storefront audit and never reaches the report; files written for agents are probed for existence only | `CLAUDE.md`, `tests/test_archetypes.py` (`absent_text`), `tests/test_orchestrator.py` |
| The zip is built from committed files and the gate re-runs inside a clean extraction of it | `scripts/package.sh` |

## Marketplace composition

*Decomposition reflects genuine separation of concerns, with clean composition by
the entrypoint, not padding.*

| What answers it | Where |
|---|---|
| A skill exists only if it has a distinct mechanism, distinct evidence and a distinct remediation vocabulary; rule counts follow the evidence, capped at 12 per skill | `README.md` (Why eight skills), `docs/DECISIONS.md` (D1) |
| One skill observes and is the only one to touch the network; six diagnose from its evidence; the entrypoint validates, arbitrates, derives severity and writes the report | `skills/audit-orchestrator/SKILL.md`, `skills/audit-orchestrator/references/composition.md` |
| The contract between skills is files validated at every boundary, not a tool, so any host that can run a script can run it | `schemas/`, `docs/CONTRACTS.md` |
| A diagnostic that fails costs only its own rules, reported as not assessed | `tests/test_orchestrator.py` (`TestRunSurvivesADiagnosticFailure`) |

## Generalization

*Works on unseen sites.*

| What answers it | Where |
|---|---|
| Rules key on mechanisms and page types, never on the audited site's platform or domain; no diagnostic names a CMS or a site | each `rules.md` and `scripts/diagnose.py` |
| Five fictional archetype sites standing for classes of real website, each with legitimate patterns placed to tempt a false positive, asserted in both directions: every expected finding and no other | `tests/fixtures/archetypes/` |
| The audit degrades by capability, not by failure: without a browser or network it still runs and says what it could not check | `samples/spa-shell-no-browser/`, `README.md` (Running it) |
| Bounded by a global deadline with per-stage budgets; real sites finished in 14 to 156 seconds | `skills/site-evidence-collector/references/budgets.md` |
