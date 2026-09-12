# Freshness and Corroboration — rule set

Every rule below is written in the canonical block defined in
`docs/RULE_FORMAT.md`. One engineering vocabulary across all six diagnostics,
not six voices. CI validates that each block has all fourteen fields present and
non-empty, that every field path named under **Evidence read** exists in
`schemas/evidence.schema.json`, and that the rule count declared below matches
the number of blocks in this file.

## Mechanism owned

Are the current facts datable, internally consistent and independently
supported? Machines treat a fact as more trustworthy when many independent
places say the same thing, and a claim contradicted between a brand's own pages
gives a retrieval system a reason to prefer somebody else's version. The rules
here cover declared versus actual freshness, undated substantive content,
intra-site contradictions, and external breadth, agreement rate and
contradiction inventory.

## Not owned by this skill

On-site structure and markup validity (`identity-and-markup`,
`answerability`). Deciding what the brand claims: this skill consumes the
canonical claims that `identity-and-markup` promoted.

## Evidence this skill may read

This skill reads `evidence/evidence.json` and nothing else. It never touches the
network. Every field path a rule consumes must appear in this list, and every
path in this list must exist in the evidence schema — CI enforces both
directions, which is what makes fabricated evidence impossible.

- `pages[].status`
- `pages[].page_type`
- `pages[].page_type_confidence`
- `canonical_claims[].id`
- `external.hits[].retrieved_at`
- `canonical_claims`
- `pages[].jsonld[].values`
- `canonical_claims[].value_normalized`
- `canonical_claims[].kind`
- `canonical_claims[].first_party_confidence`
- `canonical_claims[].entity_ambiguity`
- `claim_candidates`
- `external.attempted`
- `external.method`
- `external.frontier_size`
- `external.truncated`
- `external.origins`
- `external.origins[].registrable_domain`
- `external.origins[].source_type`
- `external.origins[].syndication_cluster`
- `external.origins[].brand_owned`
- `external.hits`
- `external.hits[].claim_id`
- `external.hits[].asserted_value`
- `external.hits[].matches_current`
- `external.hits[].origin`
- `pages[].dates`
- `pages[].dates.visible_dates`
- `pages[].dates.schema_date_modified`
- `pages[].dates.schema_date_published`
- `pages[].dates.http_last_modified`
- `pages[].headers.last_modified`
- `sitemaps[].lastmod_present_ratio`
- `run_context.capabilities.egress`
- `run_context.corroboration`
- `schema_version`
- `pages[].fetched_at`
- `pages[].provenance.layer`
- `pages[].provenance.method`
- `pages[].url`
- `sitemaps[].url`
- `external.hits[].url`
- `external.origins[].urls`

## Rule budget

Rules defined: 0 of a maximum 12.

The cap is deliberate. A thirteenth rule means something must be cut or merged.
Rule-count inflation reads as padding under this rubric, and a false positive
costs more than a miss.

## Rules
