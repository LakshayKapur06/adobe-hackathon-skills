# PLAN.md — six-day build plan

**Governing rule: a valid end-to-end report by end of Day 2, then depth.** Never
leave the pipeline broken overnight. Every day ends with a green test suite and
a commit.

The binding constraint on this build is **verification throughput, not authoring
throughput.** An agent will happily produce sixty rules with plausible
thresholds; some fraction will be subtly wrong, and false positives are named in
two rubric rows. Code nobody verified is worse than code nobody wrote.

| Day | Agent builds | Human must personally do | Gate to pass before moving on |
|---|---|---|---|
| 1 | Repo skeleton, all 8 `SKILL.md` files, `marketplace.json`, `evidence.json` + finding JSON Schemas, severity/priority functions + truth-table tests, CI harness (skill validation, manifest shape, schema conformance, rule-block completeness, evidence-field existence, TODO grep, determinism) | **Read and freeze `CONTRACTS.md`.** Everything downstream depends on it | CI green on an empty build; `skills-ref validate` passes on all 8 folders |
| 2 | Collector pass 1: robots gate, politeness, stratified sampling, stdlib parsing, capability probe. One detector wired. Orchestrator emits a schema-valid report | **Run it against 3 real sites.** Open the same pages in a browser and confirm the evidence bundle matches what you actually see | Vertical slice works: point at a site, get a valid report |
| 3 | `access-and-indexability`, `render-and-extraction` (+ browser path), `identity-and-markup`. Claim-candidate extraction and promotion | **Review every threshold and every false-positive control** in the three `references/rules.md` files | Each skill has >= 1 true-positive and >= 1 false-positive fixture |
| 4 | `answerability`, `freshness-and-corroboration` (provider tiering, two-pass collector), `arrival-and-engagement` | Same review. Check corroboration output is honest about its coverage bound and never implies open-web recall | Zero-egress run produces a valid report covering the whole on-site half |
| 5 | Orchestrator depth: dedup, contradiction resolution, priority ordering, proactive recommendations, `checks_passed`, `run_context`, `not_assessed`. Adversarial fixtures. Runtime tuning. Sample report from the local fixture | **The adjudication pass. See `docs/HUMAN_PLAYBOOK.md`.** Pick 8-10 real sites and judge every finding true or false positive | FP rate < 10% overall and **zero FPs at critical or high**. Runtime < 5 min |
| 6 | Fixes from Day 5, README, rubric mapping, `OPTIONAL_ENHANCEMENTS.md`, packaging and size check | **Adversarial read-through as a skeptical judge.** Read only the `SKILL.md` and `references/` files, as a judge would | Zip builds clean, < 50 MB, tests green, buffer intact |

**Day 5 decides the score, and it cannot be delegated.** Only a human can look at
a finding and say "that is wrong, this site is fine." Protect that day.

## Cut lines, in the order they get cut

1. The optional env-key search provider (Day 5 rule: untested -> delete).
2. Common Crawl index provider (best-effort, lowest value of the keyless set).
3. `answerability`'s query-intent coverage rule (softest rule we have).
4. Merge `access-and-indexability` + `render-and-extraction` into one skill.
   Available until end of Day 3 only. After that the merge costs more than it saves.

Never cut: the fixture set, the false-positive controls, the README, or Day 6.

## Adversarial fixture set (Day 5, non-negotiable)

Small local static sites plus recorded responses:

- 5-page brochure site (tests: does it flag a small site for being small?)
- SPA with an empty server-side shell
- E-commerce with 300 products, faceted URLs, pagination
- Documentation site (tests: boilerplate ratio and heading-density rules must not misfire)
- Publisher with dated articles
- Multilingual site with hreflang
- A site whose robots.txt disallows us
- A site returning 5xx on a subset of pages
- A deliberately minimal, well-built site (**the most important one: it should
  produce almost no findings.** If it produces many, our rules are wrong)
- A site with contradictory first-party and third-party facts
