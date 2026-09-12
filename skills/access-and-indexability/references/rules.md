# Access and Indexability — rule set

Every rule below is written in the canonical block defined in
`docs/RULE_FORMAT.md`. One engineering vocabulary across all six diagnostics,
not six voices. CI validates that each block has all fourteen fields present and
non-empty, that every field path named under **Evidence read** exists in
`schemas/evidence.schema.json`, and that the rule count declared below matches
the number of blocks in this file.

## Mechanism owned

Can a machine legally and technically reach the content at a stable address?
This is the first of the three retrieval gates — be let in, be readable, be
quotable — and a failure here makes every downstream gate unreachable. The rules
in this file cover AI-crawler policy in robots.txt, user-agent-conditional
blocking, status and redirect chains, host and URL canonical fragmentation,
sitemap health, meta robots and `X-Robots-Tag` directives including `nosnippet`,
and locale fragmentation via hreflang.

## Not owned by this skill

Content quality once reached (`answerability`). Whether the response body
actually contains the substance (`render-and-extraction`). Entity identity and
markup validity (`identity-and-markup`). Rendering of any kind: this skill reads
what the collector observed and renders nothing itself.

## Evidence this skill may read

This skill reads `evidence/evidence.json` and nothing else. It never touches the
network. Every field path a rule consumes must appear in this list, and every
path in this list must exist in the evidence schema — CI enforces both
directions, which is what makes fabricated evidence impossible.

- `robots`
- `robots.ai_agents`
- `robots.groups`
- `robots.fetched`
- `robots.status`
- `robots.sitemaps`
- `sitemaps`
- `crawl`
- `crawl.blocked_by_robots`
- `crawl.discovered`
- `crawl.fetched`
- `pages[].url`
- `pages[].final_url`
- `pages[].status`
- `pages[].redirect_chain`
- `pages[].headers.x_robots_tag`
- `pages[].meta_robots`
- `pages[].canonical`
- `pages[].canonical_self`
- `pages[].lang`
- `pages[].hreflang`
- `ua_probe`
- `ua_probe[].url`
- `ua_probe[].user_agent`
- `ua_probe[].status`
- `ua_probe[].text_len`
- `ua_probe[].text_hash`
- `well_known`
- `well_known[].path`
- `well_known[].present`
- `well_known[].status`
- `pages[].page_type`
- `site.resolved_origin`
- `site.registrable_domain`
- `site.detected_locales`
- `schema_version`
- `pages[].fetched_at`
- `pages[].provenance.layer`
- `pages[].provenance.method`
- `robots.parse_ok`
- `robots.parse_reason`
- `discovery`
- `discovery.soft_404`
- `discovery.soft_404.detected`
- `discovery.soft_404.baseline_text_hash`
- `discovery.soft_404.probe_paths`
- `discovery.collapsed_duplicate_text`
- `discovery.collapsed_redirect_target`

## Rule budget

Rules defined: 0 of a maximum 12.

The cap is deliberate. A thirteenth rule means something must be cut or merged.
Rule-count inflation reads as padding under this rubric, and a false positive
costs more than a miss.

## Rules
