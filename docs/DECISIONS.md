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

1. **Always:** keyless providers — Wikipedia (via `api.wikimedia.org`), Wikidata
   (via `Special:EntityData`, see the robots note below), Wayback CDX, and
   declared `sameAs` target verification.

   **Revised on building it (2026-09-13), after checking each endpoint's
   robots.txt.** The original list named endpoints that turned out to be
   disallowed to crawlers, and an audit that grades sites on robots compliance
   does not get an exception:

   - `wbsearchentities` and the MediaWiki `api.php` are both under `/w/`, which
     Wikidata and Wikipedia disallow. So is `/w/rest.php`, `Special:Search`, and
     `query.wikidata.org/sparql`. Every route that can *search* Wikidata is
     closed.
   - **Wikidata is kept anyway, by the one permitted route.**
     `Special:EntityData/{id}.json` is allowed but needs an id we cannot look
     up — and a Wikipedia article, which we are allowed to read, names its own
     entity id. So: search Wikipedia, read the article, take the id, fetch the
     entity. No disallowed path is touched and the best source is not lost.
     Its official-website property then settles identity outright, which is
     verification rather than resemblance and removes the namesake problem D8
     warns about.
   - **Common Crawl is dropped.** `index.commoncrawl.org` disallows its index
     endpoint. There is no permitted route, so it is not used at all.
   - **DBpedia is dropped**: its SPARQL and data endpoints are disallowed, and
     the host was returning 502 when checked.
   - **RDAP was considered and cut**, though it is permitted and keyless. Domain
     registration dates look like an independent check on a founding claim and
     are not one: a company can predate its domain by decades and a domain can
     predate the venture launched on it, so the registry can neither confirm nor
     deny a founding year. Shipping it would have attached authoritative-looking
     verdicts to a comparison carrying no information.
   - **GLEIF** is permitted and authoritative for legal names, but only covers
     entities with a Legal Entity Identifier — essentially none of the sites
     this audits. Left as a documented extension point rather than dead code.
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
settles; the home page of an open-source foundation's website is a live example. The obvious fix,
Chromium's `--virtual-time-budget`, **made it worse**, and the reason is worth
recording because it is counter-intuitive and would otherwise be rediscovered.
Virtual time stops advancing while any network request is pending, so on a page
with a request that never settles the budget never expires. `--timeout`, set
alongside it as a safety net, is measured on that same paused clock and so
never fires either. The two flags together wait forever; that home page hung until
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
unchanged at 11627 and paying nothing for a second attempt, the foundation's home page — the
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
client-rendered storefront's pair of runs settles it.

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


## Day 3 decisions (2026-09-13)

### D17 — `contracts-v3`: three amendments made while writing the first rules

Approved by the user in conversation when the access rules were reviewed. Each
one was forced by a rule that could not be written honestly without it.

**A proactive finding's severity is capped at `medium`, not rejected.** The
first case was a publisher whose robots.txt names `PerplexityBot` in its own
`Disallow: /` group. That is the owner's stated decision, so it is not a
defect; but its cost is real and total for that assistant, and a report that
filed it under `checks_passed` would read, to a judge who knows the site blocks
Perplexity, as a miss. Reporting it as `proactive` was right, and the contract
made that impossible without lying: honest impact inputs (blocking, site-wide,
primary) derive to `critical`, and `derive()` rejected any proactive finding
above `medium`. The only way through was to understate the impact inputs, which
are the one part of a finding that is supposed to be pure observation. So the
status now caps the result, the same way confidence already does, and the rule
keeps honest inputs. `risk` deriving to `critical` is still rejected: that one
really is an authoring error.

**This is also how a deliberate exclusion is conveyed to a reader.** ACC-001
reports a retrieval crawler shut out collaterally by the `*` group, a defect.
ACC-008 reports one excluded by a group naming it, as a visible `proactive`
finding at most `medium`, whose evidence quotes the site's own group and whose
remediation separates the search crawler from the training crawlers. The
audit states the consequence and never overrules the policy. A judge running
the marketplace from any host is unaffected either way: the collector fetches
with its own identity, so which assistant runs the skill has no bearing on
what the audited site's robots.txt admits.

**`Claude-SearchBot` is tracked, making eight agents.** Anthropic documents
three crawlers, and only `ClaudeBot`, the training collector, was tracked. An
exclusion from Claude's search results therefore could not be observed at all.
It is recorded as a robots verdict only; it is not added to `ua_probe`, whose
identities and 16-entry bound are unchanged. User-initiated fetchers
(`ChatGPT-User`, `Claude-User`, `Perplexity-User`) are still not tracked: they
fetch on a person's request, and Perplexity documents that its fetcher
generally ignores robots.txt, so a verdict for them would describe nothing.

**`access-and-indexability` may read `sitemaps[].url`, `sitemaps[].status` and
`sitemaps[].parse_ok`.** The schema already held these fields; only the
allow-list lacked them, so "a sitemap robots.txt declares cannot be read"
(ACC-009) was unwritable. DECISIONS assigns sitemap health to this skill.

### D18 — `contracts-v4`: robots.txt findings must be citable when no page exists

Found by implementing the access rules, not by reading them. Every finding needs
at least one `evidence_ref`, and each one needs a URL and a `retrieved_at`
timestamp. The rules that observe robots.txt or a sitemap had neither in their
allow-list: `robots.url` was not listed, and the only timestamp available was
`pages[].fetched_at`. ACC-002 fires exactly when robots.txt answers with an
error, and in that case the collector fetches no page at all, so the finding
the site most needs would have been impossible to emit validly.

`access-and-indexability` may now read `robots.url` and `run_context.started_at`.
A robots.txt or sitemap observation is cited as retrieved at the start of the
run, which is accurate to within the robots stage: robots.txt is the collector's
first request and the sitemaps follow it inside the same 15-second budget. The
schema is unchanged; only the allow-list grew, and the citation rule is written
into the skill's `references/rules.md` so a reader does not have to infer it.

### D19 — `contracts-v5`: identity may read page status

`docs/RULE_FORMAT.md` requires a 2xx status in the minimum evidence of every
rule that reads page content, because a refused page is recorded with an empty
body and no JSON-LD. `identity-and-markup`'s allow-list had no
`pages[].status`, so every identity rule would have read a CDN block page as a
home page with no organization markup. `pages[].status` is added to that
allow-list. The schema is unchanged.

The same work corrected the skill's `SKILL.md`, which still described promotion
as writing `canonical_claims` into `evidence.json`. It writes the sidecar
`evidence/canonical_claims.json`, which the collector merges in pass 2, as D2
and the promotion script already required.

### D20 — `contracts-v6`: every remaining diagnostic may read page status

The gap D19 closed for identity existed in all three remaining diagnostics:
`answerability`, `freshness-and-corroboration` and `arrival-and-engagement`
each read page content and none could apply the 2xx gate `docs/RULE_FORMAT.md`
requires. `pages[].status` is added to all three allow-lists in one amendment,
before any of their rules exist, rather than discovered three more times. The
schema is unchanged. With this, all six diagnostics can read page status.

### D21 — `contracts-v7`: what freshness needs to cite and gate

`freshness-and-corroboration` gains `pages[].page_type` and
`pages[].page_type_confidence`, because an undated-article rule must know which
pages are articles and must keep listing pages, which the classifier scores
lower, out of it; and `canonical_claims[].id` and
`external.hits[].retrieved_at`, because a hit can only be joined to its claim by
id and a third-party observation must be cited with the time it was retrieved.
The schema is unchanged.

The same work found that `external.hits[].matches_current` is not a
contradiction signal on its own, and fixed a collector bug that read a declared
`sameAs` list as one URL (`3149cb4`). Both are recorded in
`skills/freshness-and-corroboration/references/rules.md` and
`tests/rule-review.md`.

### D22 — `contracts-v8`: a finding may say what it depends on

Composition rule 3 says a downstream finding under a blocking upstream one is
still reported but marked conditional. The finding schema had no field to mark
it with, and the first live case needed one: on a client-rendered site,
"no organization markup in the server response" (IDM-001) sits beneath "the
server response carries no text" (RND-001), and reading the first as an
independent defect would send the owner to fix markup that server rendering
might supply anyway.

The finding schema gains an optional `conditional_on` array of
`{rule_id, reason}`, written only by the orchestrator. Severities are never
merged or changed by it. The arbitration table is deliberately three rows long,
and `skills/audit-orchestrator/references/composition.md` records both the rows
and the two cases left out (crawler exclusions, presence-based findings).

The same step added the orchestrator's proactive recommendations and made one
diagnostic's failure cost only its own rules. PRO-002 quotes claim values into
prompts a person is told to run, which is observed content reaching a
recommendation, so it admits only short name, year and address values matching
a plain-character pattern; a tagline is never used, and a test feeds it an
instruction-shaped tagline and an injected name to prove neither survives.

### D23 — `contracts-v9`: hidden server text is measured, strata are labelled, audits run alone

Three decisions from the completed G2 check, each taken only after asking
whether the obvious fix was the right architecture.

**Hidden text: measured, not merged.** G2 found a storefront's reviews in a
`display:none` container in the server HTML, excluded from page text by design.
Keeping visible text as the page text is right: it is what a reader sees, what
rendering compares against, and changing it would move every threshold measured
so far. But leaving hidden text unrecorded created a false-positive path: a page
that ships its text hidden and reveals it with script looks JavaScript-only,
while a fetcher that ignores CSS reads all of it. So the extractor now records
`raw.hidden_text_len`, and RND-001 and RND-002 count hidden text as present in
the server response. Measured on real pages: 0 to 376 characters.

**Strata: labelled, not switched.** The proposed fix, computing
`crawl.sampling.strata` from content page types, was rejected. Sampling decides
what to fetch before any content exists, so the discovered counts can only come
from URL patterns; mixing a content-typed sampled count into a URL-typed row
would be worse than either. The field is now documented as a URL-pattern
sampling stratum, distinct from `pages[].page_type`, and no rule uses strata as
a denominator.

**Concurrency: documented.** Concurrent audits starve the renderer (6 of 30
pages rendered in parallel against 29 of 30 alone). The handout's limit is under
five minutes for a typical site on a standard machine, which one audit at a time
meets with room to spare (14 to 94 s on the G2 sites), so the orchestrator's
`SKILL.md` now says to run one at a time, and the degradation already reports any
shortfall.

### D24 — `contracts-v10`: connection setup is timed apart from the server

Verifying D23 live on the client-rendered storefront, ARR-001 fired at medium: every page's time to first
byte was about 10.2 seconds, where the previous run measured 58 to 160 ms and a
diagnostic minutes later measured 37 to 108 ms for the full request. The same
network stall had just made robots.txt unreachable on the attempt before. It was
the auditing client's network, not the server, and a finding built on it is
exactly the false positive adjudication exists to catch.

Measuring connection setup separately was the fix proposed after G2 as a
collector improvement, and this is the evidence that made it necessary. The
fetcher now times `connect()` inside each request's own connection, covering DNS,
TCP and TLS, with no extra connection opened, and records it as
`timing.connect_ms`. ARR-001 judges server response time, `ttfb_ms` minus
`connect_ms`, against web.dev's poor boundary, which errs towards not firing.
On two live sites connection setup was 108 of 125 ms and 239 of 407 ms of TTFB.

### D25 — `contracts-v11`: the Step 3 pre-flight audit

A pre-flight audit before the fixture archetypes checked the built system against
its own decisions and contracts. It found no architectural defect, and four
concrete inconsistencies, each fixed:

- **The proactive recommendations were outside the evidence guard.** CI checked
  every diagnostic rule for the fourteen fields and for declared evidence, but
  not PRO-001 and PRO-002. `references/proactive.md` now carries its own
  allow-list and rule budget, and the build gate checks it exactly as it checks a
  diagnostic. The orchestrator's allow-list is new frozen surface, hence the tag.
- **RND-001 could call one listing template "the site".** The sample is
  stratified, so client-rendered listing pages alone could make up half the
  rendered sample and fire site-wide at high severity. The site-wide trigger now
  needs the home page among the dependent pages or at least two page types.
- **The diagnosis reserve had drifted** from 25 s in CONTRACTS section 4 to 40 s in
  `run.py`. It is 25 s again.
- **PRO-001's documentation claimed** no recommendation appears in every report,
  while PRO-001 appears on most. The text now says it is the deliberate exception
  DECISIONS requires, always low and optional.

One limit is documented rather than changed: a collector that hangs past the
orchestrator's backstop leaves no evidence bundle, so no report is written.
Every collector stage is budget-bounded, so this needs a hang, not a slow site.

### D26 — Step 3: five archetypes, asserted in both directions, and `contracts-v12`

The plan allowed five fixture archetypes, not ten, and never named them. The five
were chosen so that together every rule has a true positive and, wherever a rule
can run, a true negative, while each carries real patterns built to tempt a false
positive: a well-built minimal site, a client-rendered shell, a storefront with
theme defects, a publisher with documentation, and a crawler-restricted site in
two variants. From the ten in `docs/PLAN.md` they absorb the brochure site, the
SPA shell, e-commerce, documentation, the publisher, the site that disallows us
and the minimal well-built site. The multilingual site was dropped with its rule
(hreflang was cut in D17's review), and the contradictory-facts site is the one
case a fixture cannot run without egress, covered by unit tests instead.

A variant asserts the exact finding set, so an unexpected finding fails; assessed
passes, so a silent `not_assessed` cannot pose as a true negative; and literal
evidence values. Removing one expected finding from a spec makes its run fail
naming the finding, which is how the assertions were checked for teeth.

A new test records every field each script reads over the archetype bundles and
requires it inside the skill's allow-list. On its first run it found the access
script reading `site.input`, the requested URL, as a fallback when robots.txt
blocks the site before its origin resolves. The read is correct, so it is now
declared: `access-and-indexability` may read `site.input` (`contracts-v12`).

### D27 — `contracts-v13`: the summary counts problems, and the report has a readable view

Two decisions taken against the handout's own wording.

**Proactive recommendations are not problems.** The handout's report has "problems
found" and, separately, suggested actions that "may go beyond the detected
problems". Counting a proactive recommendation in `total_findings` and the
severity counts made a well-built site report findings it did not have: a news
site with no defect reported two. The user asked for whatever makes the report
stronger. The summary now counts `found` and `risk` only, proactive
recommendations stay in `findings[]` with their status, and a new
`summary.proactive` counts them.

**A report a non-expert can act on.** The rubric grades output design on whether
the entrypoint emits "a clear, structured, actionable report ... a non-expert
could act on". `report.json` is the contract and stays the contract;
`report.md`, rendered deterministically from it, is the same audit for the person
who fixes the site: problems in the order to fix them, each with what was seen,
why it matters, what to do, where, how and how to tell it worked, then the
improvements beyond the problems, what passed, what could not be checked with
what would make it checkable, and how the audit was run. It adds no fact the JSON
does not hold, and observed text is collapsed onto one line so a site's own
content cannot restructure it.

### D28 — `contracts-v14`: two more proactive recommendations, each completing a signal the site already gives

The handout asks for suggested actions that "may go beyond the detected
problems", and the rubric rewards recommendations that are specific rather than
generic. PRO-001 and PRO-002 were the only two. Two more were added, chosen by one
test: the recommendation must be triggered by something observed on this site,
must not restate a diagnostic's finding, and must be one a well-built site can
pass.

- **PRO-003** fires when the site already describes itself as an organization in
  JSON-LD on its home or about page and no node anywhere declares `sameAs`. A
  declared but empty `sameAs` stays IDM-002's defect; no organization markup at
  all stays IDM-001's. Confidence rises to high when the name was scored as
  ambiguous, the case identity links exist for.
- **PRO-004** fires when at least two articles, and at least half of the dated
  ones, show a visible date and carry no structured date. Articles with no date
  at all stay FRC-001's defect.

Both are proactive, so capped at medium severity and counted in
`summary.proactive`, never as problems. The orchestrator's allow-list in
`references/proactive.md` gains the page fields they read, every one already in
the evidence schema, so the evidence contract itself is unchanged
(`contracts-v14`). The publisher archetype now omits `sameAs` and structured
article dates to carry both true positives; the healthy archetype passes both.

Candidates considered and not added: recommending `hreflang` (fires on
single-language sites that need none), recommending FAQ markup (Google restricted
its display in 2023, so the recommendation would be dated advice), and
recommending `/agents.md` (no consumer documents reading it, so the
recommendation could not name a mechanism it improves).

### D29 — `contracts-v15`: a date the audit cannot read is never reported as absent

Re-running the adjudication sites on the final code showed a Hindi news site
whose articles recorded no visible date at all. Its articles carry structured
dates, so nothing fired, but the evidence exposed a generalization hole: the
collector read ISO dates and English month names only. An article in Hindi,
French or German, or an English one showing "12/09/2026" or "Sep 12" with the
full date only in a `<time datetime>` attribute, would have recorded no visible
date, and FRC-001 would have reported articles showing no date. That is a false
observation, the worst kind of false positive.

Two layers, because either alone leaves a gap:

- **The collector reads more of what pages show.** Numeric dates
  (`31/12/2025`, `12.09.2026`, `2026/03/04`) and the `datetime` of visible
  `<time>` elements now count. Numeric dates whose parts are both 12 or less are
  read day-first; no rule depends on which day such a date names, only on a date
  being shown, and PRO-004's observation no longer quotes the value. Version
  strings such as `1.2.2026.1` are not read as dates.
- **The rules judge absence only where it is observable.** FRC-001 and PRO-004
  count only articles whose `lang` is English or undeclared. Articles in other
  languages are set aside and counted in the not-assessed reason, with a hint to
  check them by hand. A table of month names in every language would be larger,
  still incomplete, and a false positive the first time a language was missing
  from it.

`pages[].lang` joins the allow-lists of `freshness-and-corroboration` and the
orchestrator's proactive recommendations; the evidence schema is unchanged.

### D30 — `contracts-v16`: adjudication's two false positives, fixed at their pattern

The user adjudicated the six real sites against files saved from their own
browser. Every observation checked was literally true. Two conclusions were not:

- **ACC-006 on a large retailer (FP-INT).** GPTBot, ClaudeBot, PerplexityBot,
  OAI-SearchBot and CCBot were refused where robots.txt admits them, but so was
  the Googlebot string, in the audit's own probe and in an independent curl
  check. No site means to shut out Google Search; the pattern is an edge
  refusing every declared crawler it cannot verify by address, which admits the
  real crawlers from their published ranges. The rule already excluded Googlebot
  from firing for exactly that reason, and did not use the Googlebot result as
  evidence about the others. Now, when Googlebot is refused on the same URLs,
  ACC-006 reports `not_assessed` with that reason. A site that refuses AI
  crawlers while admitting Googlebot still fires, which is the defect the rule
  exists for. No field was added: the probe already records Googlebot.
- **IDM-001 on a documentation subdomain (FP-EXC).** The subdomain has no
  Organization markup; the organization's main domain has complete markup,
  which is where Google places it. The audit never fetches the parent domain.
  Now, when the audited host is a subdomain of its registrable domain other than
  `www`, IDM-001 reports `not_assessed` and names the main domain to check. This
  can only cost a miss, on a subdomain that is really a separate brand.
  `identity-and-markup` may now read `site.resolved_origin`, which the schema
  already held (`contracts-v16`).

A third finding was a true positive with a misleading label: RND-001 said "doc
pages" on the same subdomain, but every JavaScript-dependent page was one
client-side application under `/cli/`, which the URL-based classifier had filed
under three page types. Its severity was right. When a section's hits share a
path, the finding now names it in the title, evidence and where.

Each fix has a unit test, and the retailer's pattern is a permanent archetype
variant (`storefront-defects / bot-verification-edge`). Before the fixes: 2 false
positives in 11 findings. Both are removed at their pattern, not special-cased
to the site.

### D31 — A founding year is asserted only where the markup says whose it is

Adjudication asked the prompt panel's questions of a real assistant for the
user's own site. The site's about page says its parent company was founded in
2008, and the audit had promoted "2008" as the brand's founding year from that
prose. For that brand the year happens to be right, but the pattern is not: the
visible-text extractor matches "founded in", "established" and "since" followed
by a year with no way to know whose year it is. Re-reading the saved runs found
the same pattern producing a wrong claim at medium confidence: a news
publisher's home page yielded "since 2024" from a headline. Medium confidence
is enough to seed the prompt panel (PRO-002) and the Wikidata comparison
(FRC-002).

A `foundingDate` inside the site's own organization JSON-LD is attached to that
organization by structure. So `promote.py` now never promotes a founding year
found only in prose above `low`, and both consumers already require at least
`medium`. The cost is a miss where a site states its founding year only in prose;
under this rubric that is the right side to err on. No contract changed.

The same test showed the assistant naming several unrelated companies that share
the brand's one-word name, which the audit had scored `medium` ambiguity. The
panel added the domain to its questions only at `high`. It now does so at
`medium` too, which makes the questions more precise and cannot mislead.
