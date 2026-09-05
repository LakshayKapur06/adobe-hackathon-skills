---
name: freshness-and-corroboration
description: >-
  Diagnoses whether a brand's current facts are datable, internally consistent
  and independently supported: declared versus actual freshness, undated
  substantive content, contradictions between pages of the same site, and the
  breadth, agreement rate and contradiction inventory of independent off-site
  sources. Use as part of a website AI-readiness audit when a brand is
  represented with stale or wrong facts. Reads a shared evidence bundle; never
  fetches anything and always reports its own coverage bound.
license: Apache-2.0
allowed-tools: Read, Write
---

# Freshness and Corroboration

**Mechanism owned:** are the current facts datable, internally consistent and
independently supported? Machines treat a fact as more trustworthy when many
independent places say the same thing. A claim that lives in exactly one place
is fragile; a claim contradicted between the brand's own pages, or between the
brand and the sources it points to, is worse — it gives a retrieval system a
reason to prefer somebody else's version.

## When to use

Use when a brand is described with stale or incorrect facts, when a fact cannot
be dated, or when an assistant repeats an outdated tagline, price, address or
founding year.

Do not use it to judge on-site structure or markup validity — that is
`identity-and-markup` and `answerability`. This skill consumes the canonical
claims that `identity-and-markup` promoted; it does not decide what the brand
claims.

## Inputs

`evidence/evidence.json`, produced by `site-evidence-collector`. Nothing else,
and never the network.

Principally: `canonical_claims`, `claim_candidates`, `external.attempted`,
`external.method`, `external.frontier_size`, `external.truncated`,
`external.origins`, `external.hits`, `pages[].dates`,
`pages[].headers.last_modified`, `sitemaps[].lastmod_present_ratio`,
`run_context.capabilities.egress`, `run_context.corroboration`.

## Procedure

1. Load `evidence/evidence.json` and confirm `schema_version` is compatible.
2. **Check egress before anything corroboration-shaped.** If
   `run_context.capabilities.egress` is false or `external.attempted` is false,
   every corroboration rule is `not_assessed` with its reason. An unsupported
   claim and an unchecked claim are different states and must never be merged.
3. **State the coverage bound in every corroboration finding.** Breadth is
   measured over an enumerable frontier — encyclopedic entries, profiles the
   brand itself points to, press it links, its own archived history — and
   `external.frontier_size` is the denominator. We do not have open-web recall,
   and no finding may be worded as though we do.
4. Count independence honestly: collapse syndication clusters and exclude
   brand-owned origins before computing breadth, or a single press release
   republished twelve times reads as twelve independent sources.
5. For each rule in `references/rules.md`, check minimum evidence, then apply
   false-positive controls and legitimate-exception checks before firing.
6. Emit findings with observed impact inputs, confidence, status, effort, scope
   denominators and `evidence_refs`. Never assign `severity`.
7. Emit `checks_passed` for rules that ran and did not fire.

## Output

`findings/freshness-and-corroboration.json`: `findings`, `not_assessed` and
`checks_passed` arrays, each finding conforming to
`../../schemas/finding.schema.json` minus the orchestrator-derived fields.


The rule set, the ownership boundary, the evidence this skill is permitted to
read and the rule budget are all in `references/rules.md`.
