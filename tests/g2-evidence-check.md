# G2 — evidence verification against real sites

Gate: **no detection rule is written until every FAIL here is fixed and
re-verified.** A rule authored against a broken evidence bundle encodes the bug
into its thresholds, and fixing the collector afterwards breaks the rule.

This is the one check in the build that a person must do. Every other gate
compares an artifact to another artifact and is automated. G2 compares the
bundle to **reality**, and an agent verifying its own collector's output
against its own beliefs about a site is a closed loop that proves nothing.

Method for each site: run the collector, then open the same pages in a browser
with **JavaScript disabled** (DevTools -> Settings -> Debugger -> Disable
JavaScript) and read view-source. Compare what the bundle says against what is
actually there.

---

## Run order and commands

Run in this order. Site 1 is the calibration site: it is the one expected to be
unremarkable, so a surprise there is a collector bug rather than a property of
the site.

    python scripts/run_audit.py --url https://indianexpress.com --out runs/indianexpress/ --summary
    python scripts/run_audit.py --url https://iflexbtw.in       --out runs/iflexbtw/   --summary
    python scripts/run_audit.py --url https://www.poco.in       --out runs/poco/       --summary
    python scripts/run_audit.py --url https://www.poco.in       --out runs/poco-norender/ --no-render --summary

`www.gadgets360.com` was the original calibration site. It answers **403 to
every request**, so it cannot calibrate anything; it is kept as the
blocked-crawler specimen in site 4 below, and `indianexpress.com` replaced it.
Selected by probing candidates with the collector's own fetcher and user agent,
since the question is whether a site serves *this* client content: of ten
candidates it was the only one combining rich server-rendered text, real
heading anchors, several JSON-LD blocks per page, and AI crawlers disallowed by
name (which makes check 4 a real test rather than a row of "allowed").

**Before reading anything else, read the summary line.** If `js_render=false`
when a browser is installed, stop and resolve that first: seven of the ten
checks below are meaningless without it, and filling them in anyway produces a
sheet that looks complete and proves nothing.

**If a fix lands mid-pass, re-run every site already done.** A bundle produced
by a since-changed collector is not evidence of anything.

Report anything that is clearly a bug immediately rather than batching it. A
bug found on site 1 almost certainly affects sites 2 and 3, and there is no
value in discovering it three times. Anything ambiguous: note it and continue.

---

## Predictions, written before the first run

These are the **implementer's** predictions. They are written down so that the
run falsifies a stated expectation instead of confirming whatever the tool
happens to print. A prediction being wrong is a result, not an embarrassment —
the failure mode this section exists to prevent is reading the output first and
then deciding it was what we expected all along.

| # | Prediction | If wrong, it means |
|---|---|---|
| P1 | indianexpress: `parse_ok: true`, a real `*` group, and `ClaudeBot`/`PerplexityBot` `disallowed` by name | We are misreading a normal robots.txt, or the named-group logic does not beat `*` |
| P2 | indianexpress: article pages classify as `article`, not `other` | `page_type` is undertrained on the commonest page shape on the web |
| P3 | indianexpress: `delta_ratio` low on articles (server-rendered text) | Either extraction is dropping raw body text, or ads/embeds inflate the rendered side |
| P4 | **Settled, artifact-to-artifact.** The home page yields 29 anchors: 9 heading `id=` attributes plus their containers' ids, paired deliberately (`extract.py:118-127`). The extractor fires. One note for rule authoring: a page reusing an id produces duplicate entries, so a rule counting deep-link targets must count *distinct* ids, never `len(anchors)` | — |
| P5 | **Settled before the run, artifact-to-artifact.** Across ten real pages the count of `<script type="application/ld+json">` blocks in the raw bytes matched `len(jsonld_scripts)` exactly, including a 4-block article and a 5-block home page. The Day-2 "reads only the first block" worry is dead | — |
| P6 | iflexbtw: `parse_ok: true`; Shopify's default robots.txt, server-rendered product text, low `delta_ratio` | Shopify's default template is not what we think it is |
| P7 | POCO **with** render: `soft_404.detected: true`, `baseline_text_hash` set, `delta_ratio` very high (raw text near zero) | The two-attempt render fix does not survive a hydration-only page — the single most important open validation in the build (D13) |
| P8 | POCO **without** render: the shell copies collapse, `discovery.collapsed_duplicate_text` > 0, and a `page-content` degradation says no page-level content exists in the server response | The capability-dependent dedupe split (D15) does not work |

**Two predictions in the old handoff notes are wrong against the shipped code.
Do not copy them into this sheet:**

- The handoff says "all **6** named AI crawlers". There were **7** when this was written, and **8** since `contracts-v3` added `Claude-SearchBot`:
  `GPTBot`, `ClaudeBot`, `PerplexityBot`, `Google-Extended`, `OAI-SearchBot`,
  `CCBot`, `Googlebot` (`schemas/evidence.schema.json`, `robots.AI_AGENTS`).
- The handoff predicts POCO's crawlers will read `allowed` because robots.txt
  is absent. The code records **`unspecified`**: when no group applies at all,
  that is the verdict, and `absent` mode sets it for every agent
  (`robots.evidence_block`). `unspecified` and `allowed` mean different things
  and only one of them is right here. Expect `parse_ok: false`,
  `parse_reason: not_plausibly_robots`, and all 7 agents `unspecified`.

Publishers increasingly disallow AI crawlers by name, and the candidate probe
confirmed it: TechCrunch disallows four of the seven tracked crawlers, The Verge
four, GSMArena four, indianexpress two. A `disallowed` verdict is **not** a FAIL
— check 4 asks only whether the bundle matches the literal file.

---

## How this pass was completed (2026-09-13)

The verdicts below were filled in after the collector had changed since the
original G2 runs, so, as this sheet requires, every site was re-run first
(`runs/g2-ie`, `g2-iflex`, `g2-poco`, `g2-poco-norender`, `g2-g360`, plus the
sequential re-runs `g2-ie-seq` and `g2-iflex-seq` explained under surprises).

**Division of labour, so the loop is not closed.** The user saved, from their own
browser, the robots.txt of each site and the server HTML of eight pages, and
judged the page type of every sampled URL. The agent compared those files with
the bundle mechanically. The user's browser is a different client on a different
network path from the collector, so agreement is independent evidence;
disagreement could be the site treating clients differently, and observation and
theory are kept apart wherever that arose.

The saved files were Chrome's view-source display pages. The original HTML was
recovered row by row, and the recovery was checked against the collector's own
`raw.bytes`: POCO 1,708 against 1,708, iflexbtw product 234,326 against 234,327,
iflexbtw about 126,351 against 126,352. The larger gaps on indianexpress (a few
hundred bytes on a 1.5 MB page) are live content, see site 1.

How each mechanical check was made, independently of the collector's code:

- **robots.txt**: the user's file was read with a separate literal reader that
  groups `User-agent` lines and takes each agent's verdict at `/`, then compared
  with `robots.ai_agents`, every group's allow and disallow lists, and the
  declared sitemaps.
- **JSON-LD**: `<script type="application/ld+json">` blocks were pulled from the
  user's source with a regular expression, parsed with `json`, expanded through
  `@graph`, and compared by count, `@type` and the values of `name`, `headline`,
  `legalName` and `foundingDate`.
- **Server text**: every `<p>`, `<h1>`, `<h2>` and `<li>` of at least 60 characters
  in the user's source had to appear verbatim in the collector's raw text
  sidecar, and an independent text-length estimate was compared with
  `raw.text_len`.

---

## Site 1: indianexpress.com — content-rich publisher, calibration site

    run directory:  runs/g2-ie/ (parallel), runs/g2-ie-seq/ (sequential)
    date:           2026-09-13
    pages fetched / discovered:   30 / 1295
    capabilities:  js_render=yes (system-chromium)  egress=yes
    elapsed:       138.4 s parallel, 94.0 s sequential

| # | Check | Verdict | Note |
|---|---|---|---|
| 1 | `raw.text_len` vs JS-off view-source | PASS | 3 pages. Independent length within 0.3%, 0.2% and 0.3% (28,599 vs 28,592; 6,780 vs 6,764; 11,140 vs 11,105). 133 of 134 paragraphs found verbatim; the one missing is a trending item stamped "3 min ago" in the user's copy, saved about 30 minutes after the collector's fetch |
| 2 | `rendered.delta_ratio` — value: median 0.003, 29 of 30 rendered (sequential run); expected low | PASS | the only page at or above 0.8 is `/subscribe` (1.0), the page D13 already identified as mounting its content after the load event |
| 3 | `page_type` correctness — 22 of 30 confirmed by the user, 0 marked wrong, 8 marked ambiguous; `other` count: 4 | PASS | the 8 ambiguous rows are a taxonomy question, not a classifier failure: see surprises |
| 4 | `robots.ai_agents` vs the literal robots.txt, all 8 agents | PASS | all 8 match; ClaudeBot and PerplexityBot disallowed by name, as P1 predicted |
| 4b | `parse_ok` / `parse_reason` — values: true / ok ; do they match what was served? | PASS | 20 group entries literal, 20 in the bundle, every allow and disallow list identical; declared sitemaps identical |
| 5 | Sampling spread across strata | PASS | home 1/3, article 9/479, about 9/130, contact 1/1, policy 2/2, other 8/680. See surprises on what the strata's `about` actually contains |
| 6 | **Positive** anchors case | PASS | closed artifact-to-artifact: home page carries 29 anchors, 9 from heading `id=` attributes and the rest from their containers, which `extract.py:118-127` pairs deliberately. The extractor fires |
| 7 | `jsonld[].values` vs the actual `<script type="application/ld+json">` | PASS | all checked `name`, `headline`, `legalName` and `foundingDate` values present with matching types, on all 3 pages |
| 7a | `ld+json` blocks in source vs in `jsonld[]` | PASS | 6 blocks and 6 nodes on each of the 3 pages, types identical |
| 8 | Runtime under 5 minutes | PASS | 94 s sequential; 138 s while three other audits ran alongside |

Wrong `page_type` classifications (url -> got -> expected): none marked wrong.
Marked ambiguous by the user: `/subscribe` (doc; user: other or doc),
`/26-11/` (other; user: other or category), `/audio/` (category; user: between
category and article), `/shorts/` (other; user: possibly category),
`/about/1more/`, `/about/100-days/`, `/about/17-again/`, `/about/2-states/`
(category; user: closer to a landing or search-results page).

Strata observed: home, article, about, contact, policy, other.

**SURPRISES**

- Observed: the user distinguished `/about/politics/` (a genre, accepted as
  category) from `/about/2-states/` (a single film, called closer to a search
  result). Theory, the user's: topic tags naming one entity are not categories.
  Consequence checked: no rule's outcome depends on category versus other for
  these pages (ACC-003 and ACC-004 exclude both), so this changes no finding.
- Observed: the strata report `about` with 130 discovered URLs, while only one
  sampled page is the organization's about page; the others are `/about/<topic>/`
  tag archives that `pages[].page_type` classifies as `category`. Theory: strata
  are computed from the URL pattern before fetching (`discover.classify_url`)
  and `page_type` from content after it, so the two vocabularies disagree on the
  same page. This makes the strata denominators misleading, which matters for W4.
- Observed: in the parallel re-run only 6 of 30 pages rendered, with "5 of 30
  failed to render" and "19 not reached". Theory: four audits ran at once, so
  four browsers competed for the CPU. Tested: re-run alone, 29 of 30 rendered.
  Confirmed. The degradation was reported honestly in both runs, but a judge
  running several audits at once would see much thinner rendering evidence.

---

## Site 2: iflexbtw.in — small Shopify storefront

    run directory:  runs/g2-iflex/ (parallel), runs/g2-iflex-seq/ (sequential)
    date:           2026-09-13
    pages fetched / discovered:   30 / 144
    capabilities:  js_render=yes (system-chromium)  egress=yes
    elapsed:       121.6 s parallel, 60.0 s sequential

| # | Check | Verdict | Note |
|---|---|---|---|
| 1 | `raw.text_len` vs JS-off view-source | PASS | 3 pages. 109 of 109 home paragraphs, 2 of 3 product, 4 of 4 about found verbatim. The one missing is a customer review inside `<div class="jdgm-legacy-widget-content" style="display: none;">`, which the collector excludes by design. Independent length within 0.4%, 7.5% and 5.2%, the gaps being hidden widget text the independent estimate did not exclude |
| 2 | `rendered.delta_ratio` — value: median 0.0, max 0.263, 29 of 30 rendered (sequential run); expected low | PASS | server-rendered, as P6 predicted |
| 3 | `page_type` correctness — 30 of 30 confirmed; `other` count: 2 | PASS | includes the login redirect as other |
| 4 | `robots.ai_agents` vs the literal robots.txt, all 8 agents | PASS | all 8 allowed, matching the literal file |
| 4b | `parse_ok` / `parse_reason` — values: true / ok | PASS | 2 group entries literal and in the bundle, rule lists identical, sitemap identical |
| 5 | Sampling spread across strata | PASS | home 1/1, product 10/106, category 10/28, about 1/1, contact 1/1, policy 5/5, other 2/2 |
| 6 | Positive anchors case | PASS | the product page's 3 distinct anchor ids all exist as `id=` attributes in the user's source |
| 7 | `jsonld[].values` vs the actual `ld+json` (Shopify emits `Product`) | PASS | Organization and Product values match on all 3 pages |
| 7a | `ld+json` blocks in source: 2, 2, 1 vs in `jsonld[]`: 2, 2, 1 | PASS | types identical |
| 8 | Runtime under 5 minutes | PASS | 60 s sequential; 122 s in parallel |

Wrong `page_type` classifications (url -> got -> expected): none.

Strata observed: home, product, category, about, contact, policy, other.

**Injection check**: PASS. The user's robots.txt carries 17 comment lines longer
than 30 characters, including the comment addressed to reading agents. None of
them appears in `evidence.json`, in any extracted-text sidecar, in any findings
file, or in `report.json`.

**SURPRISES**

- Observed: a sampled URL is a login redirect,
  `/customer_authentication/redirect?...`, recorded with status 302 and not
  followed. Theory: it is linked from the site's navigation and the redirect
  target is disallowed or off-host. It affects no rule.
- Observed: customer reviews present in the server HTML are absent from the
  collector's page text because their container carries `style="display: none;"`.
  Theory: the review app hides a legacy copy and shows a scripted one. The
  collector models visible text; a retrieval tool that ignores CSS would read
  those reviews. No current rule depends on review text. Recorded as a policy
  question, not a defect.

---

## Site 3: www.poco.in — JS-only storefront, WITH rendering

    run directory:  runs/g2-poco/
    date:           2026-09-13
    pages fetched / discovered:   5 / 5
    capabilities:  js_render=yes (system-chromium)  egress=yes
    elapsed:       13.9 s

| # | Check | Verdict | Note |
|---|---|---|---|
| 1 | `raw.text_len` vs JS-off view-source — expect near-zero body text | PASS | the user's source for `/` and `/aboutus` is 1,708 bytes with an empty `<div id="root">` and no text; bundle `raw.text_len` 0 on every page |
| 2 | `rendered.text_len` — is the **real** content there? value: 269 (home), 1,246 to 4,038 (inner pages) | PASS | against the user's rendered DOM, saved through Elements, Copy outerHTML (the first attempt went through view-source and only showed the server response): home 304 visible characters against 269, `/aboutus` 1,275 against 1,246, and every text node of 40 characters or more on both pages found verbatim in the rendered sidecar. The small gap is a "Phones Pad Accessories" menu and two extra slider dots in the user's copy |
| 2b | `rendered.delta_ratio` — value: 1.0 on all 5 ; expect very high | PASS | follows from check 1's verified empty server text and a non-zero rendered length |
| 2c | `render.fallbacks` — how many pages needed the capped second attempt? | N/A | not recorded as a typed field in the bundle |
| 3 | `page_type` correctness — first pass 1 of 5 correct; after the fix 5 of 5 | FAIL, fixed and re-verified | the user judged `/aboutus` about, `/warranty` and `/extended-warranty` policy, `/grievance` policy (or doc); all four were `other`. Cause: the classifier reads only the URL and JSON-LD, POCO serves no JSON-LD, and `aboutus`, `warranty` and `grievance` were not in its vocabulary. Fixed in `discover.py` with whole-segment additions and a word-level policy match tried only after every other match fails, with tests that a product URL containing "warranty" or "privacy" stays a product. Re-run `runs/g2-poco-fix`: home, about, policy, policy, policy |
| 4 | `robots.ai_agents` — expect all 8 `unspecified`, **not** `allowed` | PASS | all 8 unspecified; the user's saved `/robots.txt` is the application's HTML page, not a robots file |
| 4b | `parse_ok: false` and `parse_reason: not_plausibly_robots` | PASS | as served |
| 5 | `discovery.soft_404` — `detected`: true ; `baseline_text_hash`: the empty-text hash | PASS | the user's copy of a path that cannot exist is byte-identical to the home page's server response |
| 6 | Are distinct routes kept as distinct pages (deduped by *rendered* text, not collapsed)? | PASS | 5 distinct pages kept, with different rendered lengths |
| 7 | `jsonld[]` — present at all after rendering? | N/A | the bundle records JSON-LD from the server response only; none there, as the user's source confirms |
| 8 | Runtime under 5 minutes | PASS | 13.9 s |

**SURPRISES**

- Observed: the rendered home page carries 269 characters while inner pages carry
  1,246 to 4,038. Theory: the home page is mostly imagery. Tested against the
  user's rendered DOM, which carries 304 characters: confirmed. Rendering does
  recover this client-rendered site; its home page simply has little text.
- Observed: after the classifier fix, ACC-005 on POCO rises from medium to high.
  Cause: `/aboutus` is now a primary page type, and it is one of the pages
  declaring the home page as its canonical URL. This is the more accurate
  severity, and it is the kind of downstream change a classifier fix must be
  re-verified for.

---

## Site 3b: www.poco.in — WITHOUT rendering (`--no-render`)

    run directory:  runs/g2-poco-norender/ and runs/g2-poco-norender-2/
    date:           2026-09-13
    pages fetched / discovered:   1 / 1
    capabilities:  js_render=false  egress=yes  elapsed: 3.2 s

| # | Check | Verdict | Note |
|---|---|---|---|
| 1 | `discovery.soft_404.detected` true, `baseline_text_hash` set | PASS | |
| 2 | `discovery.collapsed_duplicate_text` — value: 0 ; > 0 expected | PASS, prediction falsified | the shell carries no links, so only the home page is ever discovered and there is nothing to collapse. This is the degenerate case `8a28d0f` handles explicitly; the check's purpose, no inflated denominators, holds |
| 3 | `crawl.fetched` is **not** inflated with copies of the shell | PASS | 1 fetched, 1 discovered |
| 4 | A `page-content` degradation states no page-level content exists in the server response | PASS | present, naming 1 sampled URL |
| 5 | `well_known[]` — `/llms.txt` reported `present: false` despite a 2xx (baseline match) | PASS | 200, present false; `/agents.md` likewise |
| 6 | The bundle nowhere implies the site is simply empty or simply fine | PASS | the degradation and RND-002 both state that content is absent from the server response, not from the site |
| 7 | Determinism: re-run this exact command; bundles identical but for timestamps | PASS | `g2-poco-norender` and `g2-poco-norender-2` identical after normalising clock fields |

---

## Site 4: www.gadgets360.com — blocked-crawler specimen

    run directory:  runs/g2-g360/

Re-verified on 2026-09-13: home page 403 with empty text, robots.txt 403 read as
`absent_4xx`, `crawl.errors` 1, `well_known` empty, and every one of the seven
probed identities, `browser-ua` included, refused with 403.

| # | Check | Verdict | Note |
|---|---|---|---|
| 1 | `pages[0].status` is 403 and `raw.text_len` is 0 | PASS | re-verified |
| 2 | The block page's text appears nowhere in the bundle | PASS | re-verified |
| 3 | `crawl.errors` is 1 and `discovered == fetched` | PASS | re-verified |
| 4 | A `crawl` degradation names the 403 | PASS | re-verified |
| 5 | `well_known` is empty — not probed, rather than falsely absent | PASS | re-verified |
| 6 | `robots.status` 403, `parse_reason: absent_4xx` | PASS | RFC 9309: a 4xx means no restrictions apply |
| 7 | Open the site in a normal browser. Does it serve **you** the real page? | PASS | the user received the real site |

**SURPRISES** (observation and theory kept separate):

- Observed: `ndtv.com` returns 403 to the same client. Unverified theory: same
  owner, same edge policy, so this is a corporate decision rather than one
  site's configuration.
- Observed: the raw and rendered sidecars from the *pre-fix* run had different
  hashes, because the block page carries a fresh `Reference #` in every
  response. On a site like this the bundle was not byte-reproducible between
  runs. The determinism test runs against fixtures and did not see it.
- Observed: a real browser receives the site while the collector's `browser-ua`
  identity, sending the same user-agent string, is refused. Theory: the edge
  fingerprints the client beyond the user-agent header, such as TLS or header
  order. This is the limit `collect.py` documents for `ua_probe`, and it is why
  ACC-006 treats an all-identities refusal as not assessed.

---

## Summary for the agent

| Site | FAILs | Surprises |
|---|---|---|
| indianexpress | 0 | strata vocabulary disagrees with page_type; render coverage collapses under CPU contention; entity tag pages are ambiguous as categories |
| iflexbtw | 0 | login redirect sampled; hidden review text excluded by design |
| poco (render) | 1, fixed and re-verified (page_type vocabulary) | home page renders only 269 characters, confirmed as genuine |
| gadgets360 (blocked) | 0 | a real browser is served while every probed identity is refused |
| poco (--no-render) | 0 | P8's collapse count falsified, behaviour correct |

Predictions falsified (P1-P8), and what each one turned out to be:

- P1, P2, P3, P6: held.
- P7: held. Detection, soft-404 and delta as predicted, and rendering recovers
  the site's content, verified against the user's rendered DOM.
- P8: `collapsed_duplicate_text` is 0, not greater than 0, because a shell with
  no links yields one discovered URL; the page-content degradation is present.

Cross-site patterns: page types were confirmed 52 of 60 on the publisher and the
storefront, with 8 marked ambiguous and none wrong; on the client-rendered site,
where the URL is the only evidence, 4 of 5 were wrong until the vocabulary fix,
and 5 of 5 after it. The classifier is weakest exactly where JSON-LD is absent.

Fix list, in priority order:

1. Done: the page-type vocabulary fix for URL-only classification, re-verified on
   POCO.
2. Decide whether `crawl.sampling.strata` should use content page types rather
   than URL-pattern types, since the two disagree on the same page and the
   strata are the denominators W4 relies on.
3. State in the README that audits should run one at a time on a machine,
   because concurrent runs starve the renderer and thin the evidence.
4. Record a decision on hidden-text policy: the collector models visible text,
   and a CSS-unaware retrieval tool would read `display: none` content.
