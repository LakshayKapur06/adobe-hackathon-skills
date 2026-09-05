---
name: arrival-and-engagement
description: >-
  Diagnoses whether a visitor who arrives mid-journey from an assistant can
  orient and complete their task: applicability-gated task completability, deep
  linkability and anchor targets, content-obstructing interstitials such as
  cookie walls and modals, above-the-fold answer completeness, internal
  reachability and orphaned pages, and a light latency check. Use as part of a
  website AI-readiness audit when visitors arrive but do not stay. Reads a
  shared evidence bundle; never fetches, clicks or submits anything.
license: Apache-2.0
allowed-tools: Read, Write
---

# Arrival and Engagement

**Mechanism owned:** does a visitor arriving mid-journey orient and complete
their task? An assistant sends people to a deep URL, not to the homepage, and
without the navigational context a search result would have carried. The page
has to answer on arrival, or the visit ends.

## When to use

Use when auditing the second half of the problem: the brand is found, the
visitor arrives, and the visit fails anyway.

Do not use it to judge anything aesthetic. Visual design, brand tone and layout
taste are out of scope entirely — this skill only measures whether the arriving
visitor can reach and complete a task the site itself claims to offer.

## Inputs

`evidence/evidence.json`, produced by `site-evidence-collector`. Nothing else,
and never the network.

Principally: `pages[].obstructions`, `pages[].raw.headings`,
`pages[].raw.links`, `pages[].text.visible_excerpt`,
`pages[].text.word_count`, `pages[].timing.ttfb_ms`, `pages[].timing.fetch_ms`,
`link_graph.orphans`, `link_graph.max_depth_from_home`, `link_graph.edges`,
`pages[].jsonld[].fields_present`, `pages[].page_type`.

## Procedure

1. Load `evidence/evidence.json` and confirm `schema_version` is compatible.
2. **Gate every task on applicability.** A task activates only when the evidence
   says the site offers it: the price task requires an observed `Offer` or price
   pattern, the location task requires a claimed physical presence. Score only
   applicable tasks and always report the denominator. Without this gate the
   check invents obligations the site never took on.
3. For each rule in `references/rules.md`, check minimum evidence, then apply
   false-positive controls and legitimate-exception checks before firing.
4. Treat latency as an engagement signal only. It is deliberately not used as a
   discoverability signal, because the causal link between page speed and AI
   citation specifically is weak and we will not assert it.
5. Emit findings with observed impact inputs, confidence, status, effort, scope
   denominators and `evidence_refs`. Never assign `severity`.
6. Emit `checks_passed` for rules that ran and did not fire.

## Output

`findings/arrival-and-engagement.json`: `findings`, `not_assessed` and
`checks_passed` arrays, each finding conforming to
`../../schemas/finding.schema.json` minus the orchestrator-derived fields.


The rule set, the ownership boundary, the evidence this skill is permitted to
read and the rule budget are all in `references/rules.md`.
