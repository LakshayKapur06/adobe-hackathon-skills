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
