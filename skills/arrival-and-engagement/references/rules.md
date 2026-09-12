# Arrival and Engagement — rule set

Every rule below is written in the canonical block defined in
`docs/RULE_FORMAT.md`. One engineering vocabulary across all six diagnostics,
not six voices. CI validates that each block has all fourteen fields present and
non-empty, that every field path named under **Evidence read** exists in
`schemas/evidence.schema.json`, and that the rule count declared below matches
the number of blocks in this file.

## Mechanism owned

Does a visitor arriving mid-journey orient and complete their task? An
assistant sends people to a deep URL without the navigational context a search
result would have carried, so the page has to answer on arrival. The rules here
cover applicability-gated task completability, deep-linkability and anchor
targets, content-obstructing interstitials, above-the-fold answer completeness,
internal reachability and orphans, and a light latency check.

## Not owned by this skill

Anything aesthetic: visual design, brand tone and layout taste are out of scope
entirely. Discoverability of any kind — latency is used here as an engagement
signal only, never as a discoverability signal, because the causal link between
page speed and AI citation specifically is weak and we will not assert it.

## Evidence this skill may read

This skill reads `evidence/evidence.json` and nothing else. It never touches the
network. Every field path a rule consumes must appear in this list, and every
path in this list must exist in the evidence schema — CI enforces both
directions, which is what makes fabricated evidence impossible.

- `pages[].status`
- `pages[].url`
- `pages[].obstructions`
- `pages[].obstructions[].kind`
- `pages[].raw.headings`
- `pages[].raw.anchors`
- `pages[].raw.anchors[].id`
- `pages[].raw.anchors[].heading_text`
- `pages[].raw.links`
- `pages[].raw.links[].href`
- `pages[].raw.links[].internal`
- `pages[].raw.links[].anchor`
- `pages[].raw.forms`
- `pages[].text.visible_excerpt`
- `pages[].text.word_count`
- `pages[].timing.ttfb_ms`
- `pages[].timing.fetch_ms`
- `pages[].jsonld[].fields_present`
- `pages[].jsonld[].type`
- `pages[].page_type`
- `link_graph.orphans`
- `link_graph.max_depth_from_home`
- `link_graph.edges`
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
