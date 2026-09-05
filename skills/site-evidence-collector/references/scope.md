# Collector scope — what is observed, and what is deliberately not

The collector records what is there. It does not decide what that means. The
line is simple: if a statement needs a threshold, a comparison against a norm,
or the word "should", it belongs in a diagnostic.

## Observed, and written to the bundle

| Group | What is recorded |
|---|---|
| Origin | Input, resolved origin after redirects, registrable domain, detected locales |
| robots.txt | Fetch status, every group verbatim, per-AI-crawler verdict, declared sitemaps |
| Sitemaps | Status, URL count, `lastmod` presence ratio, parse success |
| Crawl | Discovered, fetched, blocked by robots, errors, sampling strategy and strata |
| Per page | Status, redirect chain, content type, headers, meta robots, canonical, lang, hreflang, page type and its confidence |
| Raw extraction | Byte size, text length and hash, headings, links, images with alt, table/iframe/form counts |
| Rendered | Availability, text length and hash, headings, raw-vs-rendered delta ratio |
| Structured data | JSON-LD blocks with type, validity, errors, fields present, and whether they contradict visible text |
| Text shape | Visible excerpt, word count, boilerplate ratio, longest block, heading density |
| Dates | Visible dates, schema published/modified, HTTP `Last-Modified` |
| Obstructions | Cookie walls, modals, paywalls, age gates |
| Timing | TTFB, fetch time, render time |
| Claims | Candidate strings with kind, normalised value, source URL, locator, method, observed count |
| Off-site | Frontier size, truncation, origins with independence metadata, per-claim hits |

## Not observed, on purpose

| Not collected | Why |
|---|---|
| Search-engine result pages | Major engines disallow their own result endpoints in their robots.txt. Scraping them would violate the exact guardrail this marketplace audits for, in the one category cheapest to score against us. Also fragile and non-reproducible. |
| Live AI-assistant responses | Non-deterministic, key-dependent, slow and unreproducible. Monitoring an assistant panel is a *recommendation* the report makes, not an observation the audit takes. |
| Anything behind a login or a form | Out of scope by the read-only guardrail, without exception. |
| Context-adaptation probes | Diffing a response fetched with a synthetic query parameter has high false-positive potential — parameter echo, cache variance, CDN behaviour. It may feed a proactive recommendation only, never a finding. |
| Core Web Vitals as a discoverability signal | The causal link to AI citation specifically is weak. A light latency measurement is recorded and used on the engagement side only. |

## Determinism

Two runs against the same fixture produce byte-identical evidence except
timestamps. That means: fixed traversal order, sorted collections, no
wall-clock-seeded sampling, no randomised concurrency-order effects in the
output, no dependence on which worker finished first. Concurrency is a
performance device; results are re-ordered deterministically before writing.

Parsing is standard library only — `html.parser`, `urllib`, `json`, `re`,
`concurrent.futures`. A third-party parser may only ever be an optional
performance path whose extraction output is byte-identical, proven by a
conformance test. A dependency must never change extraction semantics, because
then the same site would produce different evidence on two machines.

## Two-pass ordering

Pass 1 crawls and extracts claim candidates. `identity-and-markup` promotes them
to canonical claims. Pass 2 probes off-site, seeded by those claims. The split
exists because promotion is a judgement, and the collector does not judge; see
`skills/audit-orchestrator/references/composition.md`.

## Politeness

Read-only GET requests. Sequential per host with bounded concurrency across
hosts, honouring `crawl-delay` where declared. An honest User-Agent that
identifies the audit. No retries beyond one on a transient network error. No
form submission, no login traversal, no clicking, ever. robots.txt is respected
for the audited domain and for every third-party domain fetched during the
off-site probe — a corroboration source is somebody's website too.
