# DECISIONS.md — decision register

Decided before the build began. Each entry records the decision, the reasoning,
and what it rules out. Do not silently work around any of these.

## Context

Round 2 (paper round) diagnosed why a brand is invisible in AI assistants, is
represented with stale facts, and loses visitors who do arrive. Round 3 asks us
to encode that reasoning as reusable Agent Skills so a general agent, pointed at
any unseen website, audits it automatically and emits a report of findings plus
prioritised suggested actions.

**The single most important line in the handout (Section 3):** submissions are
evaluated on *the marketplace itself* — its skills' instructions, checks, logic,
and composition — not on any report it happens to produce. A judge may never run
it. Therefore the `SKILL.md` and `references/` files are the primary deliverable
and must read as legible encoded reasoning, not as documentation of code.

## Hard constraints from the handout

- Agent Skills format (agentskills.io): `SKILL.md` with YAML frontmatter, optional
  `scripts/` and `references/`. Every skill folder independently valid.
- Root `marketplace.json` listing every skill, exactly one `entrypoint: true`.
- Entrypoint receives the audit request and emits the single final report.
- Report minimum schema: `site`, `audited_at`,
  `summary{total_findings, critical, high, medium}`,
  `findings[]{id, title, severity, evidence, suggested_action{summary, priority}}`.
  This is a floor, not a ceiling; extra fields allowed.
- Must cover **both** halves: off-site AI discoverability and on-site engagement.
- Suggested actions may exceed detected problems (proactive recommendations are
  explicitly rewarded).
- Recommend-only; read-only; no destructive/authenticated/rate-abusing actions;
  respect robots.txt.
- Portable and provider-neutral; declare tool needs; manifest self-contained
  (no external service needed to *resolve the manifest* — this governs manifest
  resolution, not runtime network access).
- Zip <= 50 MB, no pretrained model weights.
- Typical audit runtime < 5 minutes.
- Root `README.md` describing each skill and how the entrypoint composes them.

Note: the required summary counts are `critical`, `high`, `medium` only. We emit
those three plus `low`, and keep `not_assessed` in a separate array so it never
inflates `total_findings`.

## Decision register

| # | Decision | Reasoning |
|---|---|---|
| D1 | Layered architecture: observation -> shared evidence -> mechanism specialists -> orchestrated synthesis | Directly answers the rubric's "genuine separation of concerns"; makes composition real rather than a for-loop |
| D2 | Single observation layer; diagnostic skills never fetch | Protects runtime, robots posture, and observation consistency. Two skills disagreeing about the same page is the worst failure mode available |
| D3 | Capability **matrix**, not a tier ladder: JS rendering (yes/no) x egress (yes/no) | Revised. The old 3-tier ladder was partly cosmetic: stdlib does HTTP, parsing and concurrency, so "deps available" bought almost nothing, while mixed parsers would have made extraction non-deterministic across machines |
| D4 | Off-site egress assumed; corroboration is a real measured module with a disclosed coverage bound | Half the Round-2 failure modes are off-site phenomena. A site-only auditor cannot see them |
| D5 | Detectors organised by **mechanism**; Round-2 symptoms (invisible / stale / bounce) are a *presentation grouping* only | Symptom-shaped skills would each re-derive the same render gap. That is the padding trap |
| D6 | 8 skills: 1 entrypoint + 1 collector + 6 diagnostics | Each diagnostic has a distinct mechanism, distinct evidence, and a distinct remediation vocabulary |
| D7 | All capability in self-contained scripts; the inter-skill contract is a file, not a tool | The general answer to host-agnosticism. Any host that can run a script satisfies the baseline |
| D8 | Pipeline ordering is a design output: access -> identity -> corroboration | An ambiguous brand name poisons external matching, so identity gates corroboration confidence |
| D9 | Collector runs in **two passes** | Revised. Pass 1 first-party crawl + deterministic claim-candidate extraction; identity promotes candidates to canonical claims; Pass 2 off-site probe seeded by that. Resolves a circular dependency that would otherwise have broken D2 |
| D10 | Severity is a pure function of **observables only** | Revised. We cannot observe whether a fix changes AI citation rates, so severity must not encode predicted AI outcomes |
| D11 | Sample report is generated against our own local fixture site | Fully reproducible by a judge; avoids shipping a critical audit of a named third party |

## Deliberate exclusions (do not implement)

| Excluded | Why |
|---|---|
| **Scraping search-engine result pages** | Major engines disallow their result endpoints in their own robots.txt. Implementing this would violate the exact guardrail our skill audits for, in the one category cheapest to score against us. Also fragile and non-reproducible |
| **Probing live AI assistants during the audit** | Non-deterministic, key-dependent, slow, unreproducible. It belongs in the *remediation* as a recommended monitoring practice with a defined prompt panel, not in the audit |
| **`llms.txt` as a defect** | No major assistant is documented to consume it. Ships as a clearly-labelled speculative, low-priority proactive item, with two sentences of mechanism reasoning. Most submissions will flag its absence as critical; being the team that explains why it is not is a rubric asset |
| **Core Web Vitals as a discoverability signal** | Weak causal link to AI citation specifically. A light latency check stays on the engagement side only, undressed |
| **Context-adaptation probe as a defect** | Downgraded. Diffing a response fetched with a synthetic query param has high false-positive potential (param echo, cache variance, CDN behaviour). It may feed a *proactive recommendation* only, never a finding |

## Corroboration providers

Escalating, all writing the identical `external_hits` schema. Nothing downstream
branches on which provider ran, except a `coverage.method` label and a
confidence gate.

1. **Always:** keyless providers — Wikidata (`wbsearchentities` + entity fetch),
   Wikipedia/MediaWiki API, Wayback CDX, declared `sameAs` target verification,
   linked-press verification, Common Crawl index (best-effort, hard 10s timeout,
   never blocking).
2. **If the host volunteers it:** the host agent's own search capability. No
   script can detect a host tool, so this is agent-volunteered only: the SKILL.md
   says "if you have a web search capability, run these queries and write results
   to `evidence/external_hits.json` in this schema; otherwise skip."
3. **If configured:** a generic env-key search provider. See the containment
   rules below.

**Known coverage bound, to be stated in the report, not hidden:** without
privileged search access we do not have open-web recall. Breadth is measured
over an enumerable frontier (encyclopedic entries, profiles the brand itself
points to, press it links, its own archived history), and the frontier size is
reported. Never imply open-web omniscience.

**Wayback correction:** CDX gives snapshot timestamps and content digests, and a
digest changes on any byte including rotating tokens. Use it for coarse signals
(first-seen date, snapshot cadence, digest-change frequency) and fetch at most
two snapshots for the single highest-value claim to diff extracted text.

### Optional env-key provider — containment rules (all nine are mandatory)

1. Absent from every graded surface: not in `marketplace.json`, not in any
   `SKILL.md` frontmatter, not in `allowed-tools`, not in any Procedure section.
   It lives in one script file.
2. Not in the README body. README setup states **no configuration required**;
   one line at the bottom points to `docs/OPTIONAL_ENHANCEMENTS.md`.
3. Byte-identical default behaviour with no key: never instantiated, no network
   calls, no warnings, and **no "configure X for better coverage" nag** in the
   report. That nag is precisely what would read as a dependency.
4. No downstream branching. Same output file, same schema.
5. Fails closed and silent: invalid, rate-limited or slow -> recorded in
   `run_context` as `provider_unavailable`, audit continues.
6. Vendor-neutral naming: `SEARCH_API_ENDPOINT` + `SEARCH_API_KEY` against a
   documented contract. Not a named commercial integration.
7. Tested against a recorded fixture, with a test asserting the report shape is
   identical with and without.
8. Covered by the zero-egress proof run.
9. **Hard cut rule:** if it is not tested by end of Day 5, delete the file and
   keep the documented extension point. Untested code is the only version of
   this that can hurt us.

## The six diagnostic skills

| Skill | Mechanism it owns | Absorbs | Explicitly does NOT do |
|---|---|---|---|
| `access-and-indexability` | Can a machine legally and technically reach the content at a stable address? | AI-crawler robots policy, UA-conditional blocks, status/redirect chains, host and URL canonical fragmentation, sitemap health, meta robots + `X-Robots-Tag` incl. `nosnippet`, hreflang/locale fragmentation | Judge content quality; render |
| `render-and-extraction` | Once reached, is the substance present as machine-readable text? | raw vs rendered text delta, facts locked in images/PDF/canvas/iframe, interaction-gated price or availability | Evaluate markup semantics |
| `identity-and-markup` | Is the brand a well-formed, unambiguous, credible entity to a machine? | JSON-LD presence/validity/completeness, markup-vs-visible-text contradiction, `Organization` `@id` + `sameAs`, name-collision risk, trust and provenance affordances, promotion of claim candidates to canonical claims | Off-site fact checking |
| `answerability` | Is the content shaped so a retrieval system can locate and quote an answer? | passage/chunk hostility, boilerplate dominance, heading architecture, summarisation survivability, evidence-gated query-intent coverage | Crawlability, freshness |
| `freshness-and-corroboration` | Are current facts datable, internally consistent, and independently supported? | declared vs actual freshness, undated content, intra-site contradictions, external breadth / agreement rate / contradiction inventory | On-site structure |
| `arrival-and-engagement` | Does a visitor arriving mid-journey orient and complete their task? | task-completability probe, deep-linkability and anchors, content-obstructing interstitials, above-the-fold answer completeness, internal reachability and orphans, light latency | Anything aesthetic |

Plus `site-evidence-collector` (observation, two-pass) and `audit-orchestrator`
(the single entrypoint).

**The consolidation rule, to be stated verbatim in the README:** a concern earns
its own skill only if it has (1) a distinct causal mechanism, (2) distinct
evidence, and (3) a distinct remediation vocabulary. Fail any one and it becomes
a rule inside an existing skill.

## Known weaknesses and their agreed mitigations

| # | Weakness | Mitigation |
|---|---|---|
| W1 | Query-intent coverage is the softest check and closest to generic SEO | Evidence-gate it. Flag an intent gap **only** when a structured attribute the site itself publishes has no page that answers by it (e.g. `Offer.price` on 40 products but no page filters, compares or answers by price band). Cannot tie it to an observed attribute -> emit nothing |
| W2 | Task-completability risks subjectivity | Applicability gating. Each task activates only when evidence says it should (price task requires an `Offer` or a detected price pattern; location task requires a claimed physical presence). Score only applicable tasks and report the denominator |
| W3 | Context-adaptation probe is weak | Downgraded to proactive-only. See exclusions |
| W4 | Sampling representativeness on large sites | Stratified sampling seeded from sitemap + nav + link graph, grouped by URL-pattern-derived page type. Every finding states its scope and denominator. Severity accounts for sampled breadth. The handout's own example finding does this ("Crawled 12 product pages; 0/12...") |
| W5 | Claim extraction is interpretation, not observation | Resolved by D9's two-pass split: collector extracts candidate strings with provenance, identity promotes them to canonical claims |
| W6 | Judges running without a browser see a thinner report and may read it as weak detection | `not_assessed` entries are visible in the report with the reason and the one-line command to enable the capability |
| W7 | Generalisation is currently asserted, not proven | The adversarial fixture set is a Day 5 deliverable, not optional polish. It is the evidence for an entire rubric row |
| W8 | Host may run skills in isolated sandboxes with no shared filesystem | Orchestrator states all skills run in one working directory, and can execute the specialists' scripts directly itself if that guarantee does not hold |

## Three additions worth building

- **A1 — a canonical rule format shared across all six diagnostics.** Since the
  marketplace itself is graded, `references/` is a primary deliverable. One
  engineering vocabulary across six skills, not six voices. See
  `docs/RULE_FORMAT.md`. Highest-leverage item on the list.
- **A2 — a `samples/` folder** with one pre-generated report plus its evidence
  bundle, from the local fixture site. If the judge cannot or will not run it,
  the artifact is still inspectable end to end.
- **A3 — prove zero-egress completeness.** Run the full audit with all
  third-party endpoints blocked, confirm it still emits a valid useful report
  covering the entire on-site half, and say so in the README. Pre-empts any
  strict reading of the self-contained clause and demonstrates the degradation
  story rather than claiming it.

## Day 2 implementation decisions (2026-09-12)

Everything above was decided before any code existed. The entries below were
decided *while building the collector*, when the real world contradicted an
assumption. Each was approved in conversation and landed in code, and each is
recorded here so the repository explains itself without anyone reading the
commit history. They continue the register's numbering and are citable as D12
to D16.

None of these changed a frozen contract. The contract amendments that ran
alongside them are `contracts-v2`, recorded in `docs/CONTRACTS.md`.

### D12 — RFC 9309 nuances, decided case by case

`skills/site-evidence-collector/scripts/robots.py` implements the standard
rather than an approximation of it, because every verdict it produces can
become a critical finding and a wrong verdict is the one error that would make
us fail the guardrail we audit for. Four cases needed a decision the spec does
not make for us.

**429 is crawl-nothing, not a 4xx.** RFC 9309 2.3.1.3 says an "unavailable"
status means no restrictions apply, and 2.3.1.4 says "unreachable" means treat
everything as disallowed. 429 is numerically a 4xx and would fall into the
permissive branch under a naive reading. We put it in the restrictive branch,
with its own `parse_reason` value `rate_limited`. The reasoning is that 429 is
the server saying "slow down", and answering that by crawling freely would
respond to a rate limit by speeding up. This one was a correction by the
builder of an imprecise instruction, and the correction is what the spec
intends.

**A robots.txt redirect chain over five hops is recorded as `absent_4xx`.**
RFC 9309 2.3.1.2 says a crawler should follow at least five redirects and may
then treat robots.txt as unavailable, which has the same semantics as a 4xx.
Rather than add a seventh `parse_reason` value for a case that differs from
`absent_4xx` only in how it arose, we record the value whose *meaning* it
shares. Accepted as a known limit: a rule cannot distinguish "no robots.txt"
from "a robots.txt behind a redirect loop". Nothing we plan to detect needs
that distinction, and the closed enum stays small enough to reason about.

**Digits are allowed in product tokens.** RFC 9309 2.2.1 asks crawlers to
choose tokens of letters, underscores and hyphens. Real crawlers do not comply:
`MJ12bot` and `360Spider` exist and appear in real robots.txt files. Reading
`MJ12bot` as the token `MJ` would apply that group to no crawler at all, which
silently loses a rule the site author wrote. No tracked AI crawler and no token
of our own parses differently either way, so this is free correctness.

**The body decides whether a response is robots.txt; content-type is
advisory.** A file of valid directives served as `text/html` is honoured as
robots.txt; a response that starts like an HTML document is not robots.txt
whatever its content-type claims. The two errors are not symmetric. Rejecting a
genuine but mislabelled file means crawling paths the owner disallowed, which
is a guardrail violation; accepting a page as a robots file means parsing
nonsense, which under our parser yields no directives and therefore no
restrictions we would not otherwise have had. We chose the error that cannot
make us crawl something forbidden. `looks_like_robots()` holds this test and
`robots.parse_ok` records the outcome, which is why "a valid robots.txt with
zero rules" and "we were served a web page" are not the same observation in the
bundle.

### D13 — The render wait: a capped attempt, then a conditional settle (revised twice)

Waiting for the `load` event hung on pages with one resource that never
settles; the `www.python.org` home page is a live example. The obvious fix,
Chromium's `--virtual-time-budget`, **made it worse**, and the reason is worth
recording because it is counter-intuitive and would otherwise be rediscovered.
Virtual time stops advancing while any network request is pending, so on a page
with a request that never settles the budget never expires. `--timeout`, set
alongside it as a safety net, is measured on that same paused clock and so
never fires either. The two flags together wait forever; python.org hung until
killed at 20s.

The first replacement was two attempts per page: a settling attempt using
`--virtual-time-budget`, killed at 5s of real time from outside the browser,
and a real-time `--timeout` attempt only if the first returned nothing. The
per-page cap dropped from 20s to 10s.

**Revised on the first G2 calibration run.** The settling attempt does not
merely fail on pathological pages; it fails on ordinary ones. On an
ad-supported publisher it returned no DOM on **every** sampled page, 15 of 30,
each killed at 5s — and because it ran first, it spent half of each page's
budget before the attempt that works. Only 1 of 30 pages was rendered, and that
one via the fallback.

The strategies were then measured the way D13 was originally decided, on a
topic page, an article and a client-rendered storefront:

| strategy | publisher topic page | article | storefront |
|---|---|---|---|
| virtual-time 2s, killed at 5s | no DOM | no DOM | 269 chars, 4.2s |
| real `--timeout=3000`, killed at 5s | no DOM | 10999, 5.2s | 269 chars, 2.1s |
| real `--timeout=8000`, killed at 10s | **11660, 7.9s** | **10999, 8.6s** | 269 chars, 2.1s |
| load event only, killed at 10s | 11660, 7.9s | 10999, 9.0s | 269 chars, 2.1s |

The 5s kill, not the flag, was what failed: these pages need about eight
seconds to assemble. The first conclusion drawn alongside it — that the
virtual-time attempt never wins and should be deleted — **was wrong, and was
corrected the same day.** It was generalised from three pages, not one of which
was a page that assembles itself after the load event, which is the only case
the flag exists for. A sample that excludes the case under test cannot retire
the feature under test.

The page that showed it was the same publisher's subscription page:

| | capped attempt | 5s virtual time |
|---|---|---|
| `/subscribe` | 33 KB body, **0 characters of text** | **3152 characters**, plans and FAQ present |
| a topic archive | 11660 characters | no DOM |

A real-time cap dumps at the load event, so a page that mounts its content
afterwards is invisible to it. Nothing else available here can see past that
event: this module has no automation channel by design, so it cannot wait on a
selector or poll the DOM.

**So the original error was one of order, not of choice.** The quiet period
used to run first, spending half of every page's budget before the attempt that
usually works. It now runs second, and only when the capped attempt returned
fewer than 500 characters of extracted text — the one signal separating "this
page really has nothing to say" from "this page has not finished saying it".
The decision is made on extracted text rather than DOM size, because the page
that motivated it had a 33 KB body containing no text at all. Whichever attempt
finds more text wins, so settling can never replace a real result with a worse
one.

Virtual time keeps a small budget under a real-time kill, since a larger one
stalls on pending requests: a 5s budget returned in 5.5s, a 15s budget took
32.6s for identical text.

Measured after the change: `/subscribe` 0 to 3152 characters, the topic archive
unchanged at 11627 and paying nothing for a second attempt, python.org — the
original hang — 1.2s, render failures across the sampled site still zero. The
flag pairing that caused that hang stays pinned by a test, so it cannot be
revived by accident.

Which pages get rendered is now chosen rather than incidental: one page of
every `page_type` first, then the remainder. The budget cannot cover a large
sample either way, and a raw-versus-rendered baseline is worth most when every
template has one. 12 of 29 pages were still not reached inside the 60s render
budget, which is reported as a degradation naming the denominator. Raising that
budget would mean taking seconds from another stage and amending the split, and
the coverage it buys is not worth reopening the contract for.

**Still not closed:** the storefront returned 269 characters under every
strategy, so rendering may not recover a fully client-rendered site's content
at all. That is P7, the most important open validation in the build, and the
POCO pair of runs settles it.

### D14 — Pages are keyed on their final URL after redirects

`/psf` redirects to `/psf-landing/`, and so does `/psf/`. Both were fetched,
and the same document entered the crawl twice under two different starting
URLs. Keying on the requested URL cannot see this; only the response knows
where it landed.

So the crawl holds a set of *final* URLs (`held` in `collect.py`): a target
already in that set is never fetched, a redirect hop onto one is never
followed, and a response whose final URL is already held is dropped. Both
outcomes are counted in `discovery.collapsed_redirect_target`, so a rule
reading `crawl.fetched` can tell a small site from a heavily-redirecting one.
Confirming the fix: a 12-page-capped crawl went from "11 of 12 fetched", with
one page silently lost as a duplicate, to a clean 12 of 12.

This matters beyond tidiness. A duplicate page inflates every denominator a
finding reports, and the whole sampling defence (W4) rests on those
denominators being real.

### D15 — Soft-404 handling, and why deduplication depends on capability

Some sites answer every path with the same HTML shell and assemble the real
content client-side. One of the storefronts used while selecting test sites
does exactly this, confirmed by hand with `curl` and `shasum` rather than by
trusting our own collector: its home page, two paths that cannot exist, and
`/robots.txt` all returned a byte-identical body.

The site is deliberately not named. Per D11 we publish no audit finding about a
named third party, and a decision record is a weaker place to verify this than
a fixture is: what was learned from that site is reproduced as the
empty-server-shell archetype in the adversarial fixture set, where a judge can
run it rather than take our word for it.

Two decisions follow.

**The soft-404 probe.** Two paths that cannot exist are requested at the start
of the crawl. If both answer 2xx with a substantive body, the site does not
return real 404s, and `discovery.soft_404.detected` says so. A
`baseline_text_hash` is recorded only when the two bodies are also *identical*:
a site that echoes the requested path into its not-found page is still detected
but has no single baseline, and deduplicating against a hash that varies per
URL would be worse than not deduplicating at all. The probe paths are derived
by hashing the host, not randomly generated, because they are written into the
bundle and CLAUDE.md rule 10 requires two runs over the same site to produce
the same bundle.

The same baseline redefined `well_known[].present`. The original definition,
2xx plus a non-empty body, reported `/llms.txt` as present on every site that
soft-404s its whole domain. Presence now additionally requires that the text
not match the baseline.

**Deduplication splits on capability, because the honest answer differs.**
With a browser, pages are deduplicated by *rendered* text hash: the shells are
distinct pages that happen to share a server response, and collapsing them
would throw away real content. Without a browser, pages are deduplicated by
*raw* text hash against the soft-404 baseline, and the copies are not counted
in `crawl.fetched` or in any stratum, because with no way to execute the page
they genuinely carry no distinct content and counting them would inflate every
denominator with copies of one file.

The degenerate case gets its own statement rather than an empty report: when
every sampled URL matched the baseline and rendering is unavailable, the run
degrades with "no page-level content exists in the server response at all".
The claim the evidence supports is that the content is absent from the server
response, so any retrieval path that does not execute JavaScript sees nothing.
The overclaim we specifically do not make is "invisible to AI assistants" —
some assistants render.

The same split is why basic rendering was pulled forward into Day 2 instead of
waiting for Day 3: `rendered.delta_ratio` is the discriminator, and it had to
exist before G2 could test it.

### D16 — `scripts/package.sh` is a standing gate, not a one-off fix

A `.gitignore` line reading `evidence/` was written to exclude audit output.
Being unanchored, it also matched `tests/fixtures/evidence/`, so the fixture
bundle that CI reads was never committed. Every check passed locally, because
the files were sitting on disk. A fresh clone would have failed from the very
first commit. The line is now anchored (`/audit-run/`, `/runs/`, `/out/`) with
a comment saying why.

Fixing the line was not the point. The bug class is **local disk state
masquerading as a passing build**, and a passing `check.sh` in a working tree
is structurally incapable of detecting it, because the working tree is where
the untracked files are. Nothing caught this; it was noticed. The same class
covers an uncommitted new file, a path that resolves only on this machine, and
a test that reads something no one packaged.

So the gate is not "grep the .gitignore". `scripts/package.sh` builds the zip
from tracked files only (`git archive` of HEAD), refuses it at 50 MB, extracts
it into an empty temporary directory, and runs the full build gate *there*. A
file that is not committed cannot participate. This runs at every freeze and
verification point from here on, because the submission is a zip and not a
clone: anything relying on state that is not tracked in git is invisible to a
judge.
