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
result would have carried, so the page has to answer on arrival. The one rule
here is the light latency check. Task completability, interstitials, anchors,
above-the-fold completeness and internal reachability were measured against the
evidence and cut; the section below records why.

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
- `pages[].timing.connect_ms`
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

Rules defined: 1 of a maximum 12.

The cap is deliberate. A thirteenth rule means something must be cut or merged.
Rule-count inflation reads as padding under this rubric, and a false positive
costs more than a miss.

## What the arrival evidence can and cannot support

This skill was designed around a task-completability probe, content-obstructing
interstitials, deep-link anchors, internal reachability and light latency.
Measuring the evidence on the G2 sites cut all but the last:

- `obstructions` is a marker match on `id`/`class` names and dialog attributes
  in the server HTML. On a news publisher it matched `paywall` on nine articles
  whose full 2,000-word text was served; on a small storefront it matched an
  `aria-modal` dialog on 29 of 30 pages, the shape of a cart drawer that stays
  hidden until opened. A marker says a component exists, not that it covers the
  content on arrival, and the collector never renders the page as a visitor
  would see it after load.
- `link_graph.orphans` and `link_graph.max_depth_from_home` are computed within
  the sampled pages only. A page linked from any unsampled page reads as an
  orphan, so both describe the sample, not the site's navigation.
- Deep-link anchors: every current major browser supports text fragments
  (`#:~:text=`), which let a link address a passage without any `id` on the
  page, so an absent `id` does not stop a visitor being sent to the passage.
- Task completability: the collector never clicks and never submits, by design
  and by the handout, so whether a task can be completed is unobservable. Form
  counts cannot stand in for it, because modern purchase buttons are often not
  inside a form at all.

What survives is the latency check the decision register assigns to this side
of the audit: whether the server answers slowly enough that a visitor waits
before anything can appear.

**How a finding cites its evidence.** The rule is page-level: each
`evidence_ref` cites `pages[].url`, `pages[].provenance.layer`,
`pages[].provenance.method` and `pages[].fetched_at`. It is implemented in
`scripts/diagnose.py`.

## Rules

### ARR-001 — The server is slow to send the first byte

- **Mechanism:** nothing on a page can appear before its first byte arrives, so
  time to first byte is a floor under every visible milestone. web.dev describes
  it as preceding First Contentful Paint and Largest Contentful Paint, and rates
  values over 1.8 seconds as poor. A visitor sent to a deep page from an answer
  arrives with no prior commitment to the site, and a page that shows nothing
  for seconds is the one they leave.
- **Signal:** the median server response time across sampled 2xx pages exceeds
  1,800 ms, where server response time is `timing.ttfb_ms` minus
  `timing.connect_ms` (or `ttfb_ms` alone when `connect_ms` is null).
- **Evidence read:** `pages[].url`, `pages[].status`, `pages[].page_type`,
  `pages[].timing.ttfb_ms`, `pages[].timing.connect_ms`, `pages[].timing.fetch_ms`.
- **Threshold:** median above 1,800 ms. Justification: 1,800 ms is web.dev's
  boundary for a poor TTFB. Applying it to server response time alone, which
  excludes connection setup that web.dev's TTFB includes, errs towards not
  firing: a site is only flagged when the server's own share already exceeds the
  boundary for the whole. The median rather than the mean or the maximum is
  used because a single slow page, such as one uncached search result, pulls a
  mean up and says nothing about the site; the median moves only when most of
  the sample is slow.
- **Minimum evidence:** at least 5 sampled 2xx pages with a recorded
  `ttfb_ms`. Fewer is `not_assessed`: a median of three requests is one slow
  moment.
- **False-positive controls:** only 2xx pages, so a refusal answered instantly
  or an error page timing out cannot shift the median; the collector starts the
  timer after any crawl-delay wait, so politeness never counts as latency;
  connection setup (DNS, TCP, TLS) is subtracted, so a stall on the auditing
  client's network never reads as a slow server, which one live G2 run showed
  it otherwise would (a uniform ten-second stall on every page); the
  finding states the median, the slowest and the fastest page, so a reader can
  see whether slowness is uniform.
- **Legitimate exceptions:** distance between the auditing client and the
  site's servers, and a fresh DNS and TLS connection on every request, which a
  returning browser does not pay, both inflate the measurement. Neither is
  detectable from the bundle. That is why the rule is `risk` at `low` confidence,
  why it compares a median against the poor boundary rather than the good one,
  and why the remediation begins with field measurement.
- **Confidence:** low, always, for the reasons under legitimate exceptions.
- **Impact inputs:** `blocking = false` (the page arrives, late). `breadth =
  "site"` (a median across the sample). `content_importance = "secondary"`.
- **Status:** risk
- **Symptom tags:** bounce
- **Remediation:** what: confirm the delay with field data, then reduce server
  response time on the slowest templates. Where: the origin server and CDN
  configuration for the URLs cited, starting with the slowest. Why: every
  visible milestone waits on the first byte. How: check the site's real-user
  TTFB in its analytics or the Chrome UX Report for these URLs; if it is also
  poor, cache rendered HTML at a CDN edge, profile the slowest templates' server
  work (database queries, uncached API calls), and serve static routes
  statically. Mechanism improved: time until an arriving visitor sees anything.
- **Success criteria:** the 75th-percentile field TTFB for the site's pages is at
  or below 800 ms, web.dev's good threshold, or a re-run of this audit records a
  median below 1,800 ms.
- **Effort:** medium
