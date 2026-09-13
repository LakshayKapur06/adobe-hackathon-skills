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
| Crawl | Discovered, fetched, blocked by robots, errors, sampling strategy and URL-pattern strata |
| Per page | Status, redirect chain, content type, headers, meta robots, canonical, lang, hreflang, page type and its confidence |
| Raw extraction | Byte size, visible text length and hash, the length of text hidden by markup, the extracted-text sidecar path, headings, in-page anchor targets, links, images with alt, table/iframe/form counts |
| Rendered | Availability, text length and hash, its own sidecar path, headings, raw-vs-rendered delta ratio |
| Structured data | JSON-LD blocks with type, validity, errors, fields present, a flat map of dotted path to asserted value, and whether they contradict visible text |
| Text shape | Visible excerpt, word count, boilerplate ratio, longest block, heading density |
| Dates | Visible dates, schema published/modified, HTTP `Last-Modified` |
| Obstructions | Cookie walls, modals, paywalls, age gates |
| Timing | Time to first byte, the connection setup inside it (DNS, TCP, TLS), fetch time, render time |
| Claims | Candidate strings with kind, normalised value, source URL, locator, method, observed count |
| Off-site | Frontier size, truncation, origins with independence metadata, per-claim hits |
| User-agent probe | Status and extracted-text length returned to each named AI crawler, on the home page and one deep page only |
| Agent-facing discovery files | Status, presence and content type of `/llms.txt`, `/agents.md` and `/.well-known/ucp` — never their contents |

## Extracted text lives beside the bundle, not inside it

`raw.text_path` and `rendered.text_path` point at
`evidence/pages/<sha256>.txt`, which holds the extracted text whose length and
hash the sibling fields report. Inlining full page text would make the bundle
unreadable and undiffable for no gain; naming the files by content hash means
two pages with identical extracted text share one file. Those sidecars are part
of the evidence bundle: the collector writes them and nothing else does, and a
diagnostic reading one is still reading observation, not fetching.

## The user-agent probe, and its deliberate bound

`ua_probe` is the one observation that varies the request identity, to detect a
site that serves different content or a different status to a named AI crawler
than to an ordinary client. It is bounded hard at two URLs — the home page and
one deep page — because repeating it across a sample would be indistinguishable
from probing the site, and because two URLs is enough to tell conditional
serving from a one-off. Every probe respects robots.txt: a URL we are disallowed
from is not requested under any user agent, and the probe never re-requests a
URL that already errored.

## Agent-facing discovery files, and why we look at all

No major assistant is documented to consume `/llms.txt`, `/agents.md` or
`/.well-known/ucp`. They are observed anyway, for one reason: so that anything
the report says about them rests on what is actually at the origin, and can be
pitched correctly — as a speculative, low-priority proactive item — rather than
flagged as a defect the way a naive audit would. Absence is recorded like any
other observation, never as an error.

Each path is requested once, within a 5s total budget, and only if robots.txt
permits it. Only the status, presence and content type are kept. The contents
are never recorded: these files exist to be read by agents, which makes them
the most direct way a site can put instructions in front of one, and the
evidence bundle is not a channel for that.

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

Pass 1 crawls and extracts claim candidates. The audit's identity diagnostic
promotes them to canonical claims. Pass 2 probes off-site, seeded by those
claims.

The split exists to resolve a circular dependency without breaking the
single-observer rule. Corroboration needs to know what the brand claims, and
deciding which of several candidate strings *is* the brand's claim is a
judgement — weighing how often a string occurs, by which extraction method, on
how prominent a page. If the collector made that judgement it would be
interpreting rather than observing; if the corroboration diagnostic fetched its
own sources it would become a second observer. Splitting observation into two
passes, with the judgement in between, avoids both.

## Politeness

Read-only GET requests. Sequential per host with bounded concurrency across
hosts, honouring `crawl-delay` where declared. An honest User-Agent that
identifies the audit. No retries beyond one on a transient network error. No
form submission, no login traversal, no clicking, ever. robots.txt is respected
for the audited domain and for every third-party domain fetched during the
off-site probe — a corroboration source is somebody's website too.
