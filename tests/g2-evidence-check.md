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
| P4 | indianexpress: at least one page has heading `id=` attributes, and `raw.anchors` is non-empty there (29 were seen on the home page during selection) | The anchors extractor has never been proven to fire at all (see check 6) |
| P5 | **Settled before the run, artifact-to-artifact.** Across ten real pages the count of `<script type="application/ld+json">` blocks in the raw bytes matched `len(jsonld_scripts)` exactly, including a 4-block article and a 5-block home page. The Day-2 "reads only the first block" worry is dead | — |
| P6 | iflexbtw: `parse_ok: true`; Shopify's default robots.txt, server-rendered product text, low `delta_ratio` | Shopify's default template is not what we think it is |
| P7 | POCO **with** render: `soft_404.detected: true`, `baseline_text_hash` set, `delta_ratio` very high (raw text near zero) | The two-attempt render fix does not survive a hydration-only page — the single most important open validation in the build (D13) |
| P8 | POCO **without** render: the shell copies collapse, `discovery.collapsed_duplicate_text` > 0, and a `page-content` degradation says no page-level content exists in the server response | The capability-dependent dedupe split (D15) does not work |

**Two predictions in the old handoff notes are wrong against the shipped code.
Do not copy them into this sheet:**

- The handoff says "all **6** named AI crawlers". There are **7**:
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

## Site 1: indianexpress.com — content-rich publisher, calibration site

    run directory:  runs/indianexpress/
    date:
    pages fetched / discovered:      /
    capabilities:  js_render=    egress=    renderer=
    elapsed:       s

| # | Check | Verdict | Note |
|---|---|---|---|
| 1 | `raw.text_len` vs JS-off view-source — is the body text actually that long? | PASS / FAIL | |
| 2 | `rendered.delta_ratio` — value: ___ ; expected high (SPA) / low (static)? | PASS / FAIL | |
| 3 | `page_type` correctness — ___ of ___ correct; `other` count: ___ | PASS / FAIL | |
| 4 | `robots.ai_agents` vs the literal robots.txt, all 7 agents | PASS / FAIL | |
| 4b | `parse_ok` / `parse_reason` — values: ___ / ___ ; do they match what was served? | PASS / FAIL | |
| 5 | Sampling spread across strata | PASS / FAIL | |
| 6 | **Positive** anchors case: find a page with real heading `id=` attributes; does `raw.anchors` pick them up? | PASS / FAIL | |
| 7 | `jsonld[].values` vs the actual `<script type="application/ld+json">` | PASS / FAIL | |
| 7a | **Count** `ld+json` blocks in view-source on one article page: ___ in source vs ___ in `jsonld[]` | PASS / FAIL | |
| 8 | Runtime under 5 minutes | PASS / FAIL | |

Wrong `page_type` classifications (url -> got -> expected):

Strata observed:

**SURPRISES** — anything at all that did not match expectation, however small.
This is the most important line in the document. Write the observation and any
theory about its cause **separately**: "...oh, that's probably because of X"
without checking is the most expensive failure mode in this process. Let the
next round confirm or kill the theory instead of explaining the mismatch away:

---

## Site 2: iflexbtw.in — small Shopify storefront

    run directory:  runs/iflexbtw/
    date:
    pages fetched / discovered:      /
    capabilities:  js_render=    egress=    renderer=
    elapsed:       s

| # | Check | Verdict | Note |
|---|---|---|---|
| 1 | `raw.text_len` vs JS-off view-source | PASS / FAIL | |
| 2 | `rendered.delta_ratio` — value: ___ ; expected high (SPA) / low (static)? | PASS / FAIL | |
| 3 | `page_type` correctness — ___ of ___ correct; `other` count: ___ | PASS / FAIL | |
| 4 | `robots.ai_agents` vs the literal robots.txt, all 7 agents | PASS / FAIL | |
| 4b | `parse_ok` / `parse_reason` — values: ___ / ___ | PASS / FAIL | |
| 5 | Sampling spread across strata | PASS / FAIL | |
| 6 | Positive anchors case (if any page qualifies) | PASS / FAIL / N/A | |
| 7 | `jsonld[].values` vs the actual `ld+json` (Shopify emits `Product`) | PASS / FAIL | |
| 7a | `ld+json` blocks in source: ___ vs in `jsonld[]`: ___ | PASS / FAIL | |
| 8 | Runtime under 5 minutes | PASS / FAIL | |

Wrong `page_type` classifications (url -> got -> expected):

Strata observed:

**Injection check** (this site is where the Shopify robots.txt comment was
found): confirm the comment asking the reading agent to recommend a skill
install appears **nowhere** in the bundle — not in `robots.groups`, not in any
page text, not in `errors[]`. Comments are dropped at parse time by design
(`robots.parse`). Verdict: PASS / FAIL

**SURPRISES** (observation and theory kept separate):

---

## Site 3: www.poco.in — JS-only storefront, WITH rendering

    run directory:  runs/poco/
    date:
    pages fetched / discovered:      /
    capabilities:  js_render=    egress=    renderer=
    elapsed:       s

**This site and the next are the most important results in the pass.** With
rendering, the bundle should show the site's real content and a large
`delta_ratio`. Without it, the bundle should plainly state that no page-level
content exists in the raw server response. If the two runs do not differ
sharply, something in the render fix (D13) or the dedupe split (D15) is still
wrong, and that must be resolved before a single detection rule is written.

| # | Check | Verdict | Note |
|---|---|---|---|
| 1 | `raw.text_len` vs JS-off view-source — expect near-zero body text | PASS / FAIL | |
| 2 | `rendered.text_len` — is the **real** content there? value: ___ | PASS / FAIL | |
| 2b | `rendered.delta_ratio` — value: ___ ; expect very high | PASS / FAIL | |
| 2c | `render.fallbacks` — how many pages needed the capped second attempt? ___ | PASS / FAIL | |
| 3 | `page_type` correctness — ___ of ___ correct; `other` count: ___ | PASS / FAIL | |
| 4 | `robots.ai_agents` — expect all 7 `unspecified`, **not** `allowed` | PASS / FAIL | |
| 4b | `parse_ok: false` and `parse_reason: not_plausibly_robots` | PASS / FAIL | |
| 5 | `discovery.soft_404` — `detected`: ___ ; `baseline_text_hash`: ___ | PASS / FAIL | |
| 6 | Are distinct routes kept as distinct pages (deduped by *rendered* text, not collapsed)? | PASS / FAIL | |
| 7 | `jsonld[]` — present at all after rendering? | PASS / FAIL | |
| 8 | Runtime under 5 minutes | PASS / FAIL | |

**SURPRISES** (observation and theory kept separate):

---

## Site 3b: www.poco.in — WITHOUT rendering (`--no-render`)

    run directory:  runs/poco-norender/
    date:
    pages fetched / discovered:      /
    capabilities:  js_render=false  egress=    elapsed:       s

| # | Check | Verdict | Note |
|---|---|---|---|
| 1 | `discovery.soft_404.detected` true, `baseline_text_hash` set | PASS / FAIL | |
| 2 | `discovery.collapsed_duplicate_text` — value: ___ ; > 0 expected | PASS / FAIL | |
| 3 | `crawl.fetched` is **not** inflated with copies of the shell | PASS / FAIL | |
| 4 | A `page-content` degradation states no page-level content exists in the server response | PASS / FAIL | |
| 5 | `well_known[]` — `/llms.txt` reported `present: false` despite a 2xx (baseline match) | PASS / FAIL | |
| 6 | The bundle nowhere implies the site is simply empty or simply fine | PASS / FAIL | |
| 7 | Determinism: re-run this exact command; bundles identical but for timestamps | PASS / FAIL | |

**SURPRISES** (observation and theory kept separate):

---

## Site 4: www.gadgets360.com — blocked-crawler specimen

    run directory:  runs/gadgets360-refused/

Not a calibration site: every request is answered **403**, so no extractor ever
sees the real page. It is kept because it is a live instance of fixture
archetype 7, and because the first run against it found the worst bug in the
build so far — the block page was recorded as the home page's content, and the
run reported a clean crawl of a thin site. Fixed in `e061299`.

The collector now reports, and this was verified after the fix:

| # | Check | Verdict | Note |
|---|---|---|---|
| 1 | `pages[0].status` is 403 and `raw.text_len` is 0 | PASS | verified |
| 2 | The block page's text appears nowhere in the bundle | PASS | verified |
| 3 | `crawl.errors` is 1 and `discovered == fetched` | PASS | verified |
| 4 | A `crawl` degradation names the 403 | PASS | verified |
| 5 | `well_known` is empty — not probed, rather than falsely absent | PASS | verified |
| 6 | `robots.status` 403, `parse_reason: absent_4xx` | PASS | RFC 9309: a 4xx means no restrictions apply |

The one check that still needs a person, because only a browser can settle it:

| # | Check | Verdict | Note |
|---|---|---|---|
| 7 | Open the site in a normal browser. Does it serve **you** the real page? | PASS / FAIL | If yes, this is user-agent-conditional serving, and the site is a live specimen for the `ua_probe` work |

**SURPRISES** (observation and theory kept separate):

- Observed: `ndtv.com` returns 403 to the same client. Unverified theory: same
  owner, same edge policy, so this is a corporate decision rather than one
  site's configuration.
- Observed: the raw and rendered sidecars from the *pre-fix* run had different
  hashes, because the block page carries a fresh `Reference #` in every
  response. On a site like this the bundle was not byte-reproducible between
  runs. The determinism test runs against fixtures and did not see it.

---

## Summary for the agent

| Site | FAILs | Surprises |
|---|---|---|
| indianexpress | | |
| iflexbtw | | |
| poco (render) | | |
| gadgets360 (blocked) | 0 after e061299 | see above |
| poco (--no-render) | | |

Predictions falsified (P1-P8), and what each one turned out to be:

Cross-site patterns — one wrong `page_type` is noise; the same one wrong on all
three sites is a classifier bug:

Fix list, in priority order:
1.
