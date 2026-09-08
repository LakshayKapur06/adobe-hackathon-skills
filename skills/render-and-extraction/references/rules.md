# Render and Extraction — rule set

Every rule below is written in the canonical block defined in
`docs/RULE_FORMAT.md`. One engineering vocabulary across all six diagnostics,
not six voices. CI validates that each block has all fourteen fields present and
non-empty, that every field path named under **Evidence read** exists in
`schemas/evidence.schema.json`, and that the rule count declared below matches
the number of blocks in this file.

## Mechanism owned

Once reached, is the substance present as machine-readable text? A fact that
exists only after client-side hydration cannot be extracted by a fetcher, so it
cannot be quoted even though a human sees it. The rules here cover the delta
between server HTML and the rendered DOM, facts locked inside images, PDFs,
canvas or iframes, and prices or availability that appear only after
interaction.

## Not owned by this skill

Markup semantics — whether the fact is expressed as valid `Product` or `Offer`
JSON-LD is `identity-and-markup`. Whether surrounding prose is quotable
(`answerability`). Crawler admission (`access-and-indexability`).

## Evidence this skill may read

This skill reads `evidence/evidence.json` and nothing else. It never touches the
network. Every field path a rule consumes must appear in this list, and every
path in this list must exist in the evidence schema — CI enforces both
directions, which is what makes fabricated evidence impossible.

- `pages[].url`
- `pages[].content_type`
- `pages[].status`
- `pages[].raw.text_len`
- `pages[].raw.text_hash`
- `pages[].raw.text_path`
- `pages[].raw.images`
- `pages[].raw.images[].alt`
- `pages[].raw.images[].text_likely`
- `pages[].raw.iframes`
- `pages[].raw.tables`
- `pages[].raw.headings`
- `pages[].rendered.available`
- `pages[].rendered.text_len`
- `pages[].rendered.text_hash`
- `pages[].rendered.text_path`
- `pages[].rendered.delta_ratio`
- `pages[].rendered.headings`
- `pages[].jsonld[].fields_present`
- `pages[].jsonld[].values`
- `pages[].jsonld[].type`
- `pages[].page_type`
- `pages[].page_type_confidence`
- `pages[].obstructions`
- `run_context.capabilities.js_render`
- `run_context.degradations`
- `crawl.sampling`
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
