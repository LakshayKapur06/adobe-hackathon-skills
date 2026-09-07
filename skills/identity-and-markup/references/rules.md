# Identity and Markup — rule set

Every rule below is written in the canonical block defined in
`docs/RULE_FORMAT.md`. One engineering vocabulary across all six diagnostics,
not six voices. CI validates that each block has all fourteen fields present and
non-empty, that every field path named under **Evidence read** exists in
`schemas/evidence.schema.json`, and that the rule count declared below matches
the number of blocks in this file.

## Mechanism owned

Is the brand a well-formed, unambiguous, credible entity to a machine? When
several things share a name, a retrieval system mixes them up unless something
distinguishes one from the others. The rules here cover JSON-LD presence,
validity and completeness, markup that contradicts visible text, `Organization`
identity anchoring via an `@id` and `sameAs`, name-collision risk, and trust and
provenance affordances. This skill also owns the promotion of claim candidates
to canonical claims.

## Not owned by this skill

Whether the outside world agrees with the brand's claims
(`freshness-and-corroboration`). Whether the text is present at all
(`render-and-extraction`). Whether prose is quotable (`answerability`).

## Evidence this skill may read

This skill reads `evidence/evidence.json` and nothing else. It never touches the
network. Every field path a rule consumes must appear in this list, and every
path in this list must exist in the evidence schema — CI enforces both
directions, which is what makes fabricated evidence impossible.

- `pages[].url`
- `pages[].jsonld`
- `pages[].jsonld[].type`
- `pages[].jsonld[].valid`
- `pages[].jsonld[].errors`
- `pages[].jsonld[].fields_present`
- `pages[].jsonld[].values`
- `pages[].jsonld[].contradicts_visible_text`
- `pages[].microdata_or_rdfa`
- `pages[].raw.headings`
- `pages[].raw.links`
- `pages[].text.visible_excerpt`
- `pages[].page_type`
- `claim_candidates`
- `claim_candidates[].kind`
- `claim_candidates[].value_normalized`
- `claim_candidates[].observed_count`
- `claim_candidates[].extraction_method`
- `canonical_claims`
- `canonical_claims[].entity_ambiguity`
- `canonical_claims[].first_party_confidence`
- `site.registrable_domain`
- `site.detected_locales`

## Rule budget

Rules defined: 0 of a maximum 12.

The cap is deliberate. A thirteenth rule means something must be cut or merged.
Rule-count inflation reads as padding under this rubric, and a false positive
costs more than a miss.

## Rules
