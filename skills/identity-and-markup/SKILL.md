---
name: identity-and-markup
description: >-
  Diagnoses whether a brand presents as a well-formed, unambiguous entity to a
  machine: organization identity markup on the home page, sameAs identity links
  that identify nothing, JSON-LD that fails to parse, and structured prices that
  contradict the visible page. Also
  promotes extracted claim candidates to canonical claims so corroboration has
  something stable to test. Use as part of a website AI-readiness audit when a
  brand may be confused with another entity or described inconsistently.
license: Apache-2.0
allowed-tools: Read, Write
---

# Identity and Markup

**Mechanism owned:** is the brand a well-formed, unambiguous, credible entity to
a machine? When several things share a name, a retrieval system mixes them up
unless something clearly distinguishes one from the others. Markup that
contradicts the visible text is worse than absent markup, because it makes the
machine confidently wrong.

## When to use

Use when auditing entity clarity and machine-readable identity: structured data
quality, identity anchoring, name ambiguity, provenance signals.

Do not use it to check whether outside sources agree with the brand's claims —
that is `freshness-and-corroboration`. This skill establishes what the brand
claims to be; that skill tests whether the world agrees.

## Inputs

`evidence/evidence.json`, produced by `site-evidence-collector`. Nothing else,
and never the network.

Principally: `pages[].status`, `pages[].page_type`, `pages[].jsonld`,
`pages[].microdata_or_rdfa`, and `claim_candidates` for promotion.

## Procedure

1. Load `evidence/evidence.json` and confirm `schema_version` is compatible.
2. **Promote claim candidates to canonical claims first**, with
   `scripts/promote.py`. Group candidates by kind and normalised value, weigh
   them by observed count and extraction method, then assign
   `first_party_confidence` and `entity_ambiguity`. Write the promoted set to
   `evidence/canonical_claims.json`; the collector merges it into the bundle in
   its second pass. This runs before the off-site probe, because an ambiguous
   brand name poisons external matching and corroboration confidence is gated
   on it. The rules in step 3 are implemented in `scripts/diagnose.py`:

       python scripts/diagnose.py --evidence evidence/evidence.json --out findings/identity-and-markup.json
3. For each rule in `references/rules.md`, check minimum evidence, then apply
   false-positive controls and legitimate-exception checks before firing.
4. Emit findings with observed impact inputs, confidence, status, effort, scope
   denominators and `evidence_refs`. Never assign `severity`.
5. Emit `checks_passed` for rules that ran and did not fire.

## Output

`findings/identity-and-markup.json`: `findings`, `not_assessed` and
`checks_passed` arrays. Promotion additionally writes
`evidence/canonical_claims.json`, a sidecar rather than an edit to
`evidence.json`, so that the collector stays the single writer of the bundle
(D2); the collector merges it in pass 2.


The rule set, the ownership boundary, the evidence this skill is permitted to
read and the rule budget are all in `references/rules.md`.
