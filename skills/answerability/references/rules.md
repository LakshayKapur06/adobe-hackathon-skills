# Answerability — rule set

Every rule below is written in the canonical block defined in
`docs/RULE_FORMAT.md`. One engineering vocabulary across all six diagnostics,
not six voices. CI validates that each block has all fourteen fields present and
non-empty, that every field path named under **Evidence read** exists in
`schemas/evidence.schema.json`, and that the rule count declared below matches
the number of blocks in this file.

## Mechanism owned

Is the content shaped so a retrieval system can locate and quote an answer?
Assistants build answers from passages they can isolate; substance diluted
across boilerplate or buried in one undifferentiated block gives a retriever
nothing to lift. The rules here cover passage and chunk hostility, boilerplate
dominance, heading architecture, summarisation survivability, and
evidence-gated query-intent coverage.

## Not owned by this skill

Crawler admission (`access-and-indexability`). Whether the text is present in
the response at all (`render-and-extraction`). Whether a fact is current or
corroborated (`freshness-and-corroboration`).

## Evidence this skill may read

This skill reads `evidence/evidence.json` and nothing else. It never touches the
network. Every field path a rule consumes must appear in this list, and every
path in this list must exist in the evidence schema — CI enforces both
directions, which is what makes fabricated evidence impossible.

- `pages[].url`
- `pages[].text.word_count`
- `pages[].text.boilerplate_ratio`
- `pages[].text.longest_block_words`
- `pages[].text.heading_density_per_1k`
- `pages[].text.visible_excerpt`
- `pages[].raw.headings`
- `pages[].raw.text_path`
- `pages[].raw.anchors`
- `pages[].raw.headings[].level`
- `pages[].raw.headings[].text`
- `pages[].page_type`
- `pages[].page_type_confidence`
- `pages[].jsonld[].fields_present`
- `pages[].jsonld[].type`
- `crawl.sampling`
- `crawl.sampling.strata`
- `schema_version`
- `pages[].fetched_at`
- `pages[].provenance.layer`
- `pages[].provenance.method`

## Rule budget

Rules defined: 0 of a maximum 12.

The cap is deliberate. A thirteenth rule means something must be cut or merged.
Rule-count inflation reads as padding under this rubric, and a false positive
costs more than a miss.

## Rules
