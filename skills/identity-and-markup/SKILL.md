---
name: identity-and-markup
description: >-
  Diagnoses whether a brand presents as a well-formed, unambiguous, credible
  entity to a machine: JSON-LD presence, validity and completeness, structured
  markup that contradicts visible text, Organization identity anchoring via id
  and sameAs, name-collision risk, and trust and provenance affordances. Also
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

Principally: `pages[].jsonld`, `pages[].microdata_or_rdfa`,
`pages[].raw.headings`, `pages[].text.visible_excerpt`, `claim_candidates`,
`site.registrable_domain`, `site.detected_locales`.

## Procedure

1. Load `evidence/evidence.json` and confirm `schema_version` is compatible.
2. **Promote claim candidates to canonical claims first.** Group candidates by
   kind and normalised value, weigh them by observed count, extraction method
   and source-page prominence, then assign `first_party_confidence` and
   `entity_ambiguity`. Write the promoted set back as `canonical_claims`. This
   runs before the off-site probe, because an ambiguous brand name poisons
   external matching and corroboration confidence is gated on it.
3. For each rule in `references/rules.md`, check minimum evidence, then apply
   false-positive controls and legitimate-exception checks before firing.
4. Emit findings with observed impact inputs, confidence, status, effort, scope
   denominators and `evidence_refs`. Never assign `severity`.
5. Emit `checks_passed` for rules that ran and did not fire.

## Output

`findings/identity-and-markup.json`: `findings`, `not_assessed` and
`checks_passed` arrays. Additionally writes `canonical_claims` back into the
evidence bundle — the only diagnostic permitted to write to the bundle, and
only for that one key.


The rule set, the ownership boundary, the evidence this skill is permitted to
read and the rule budget are all in `references/rules.md`.
