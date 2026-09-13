# Budgets — staying under five minutes without lying about coverage

The handout requires a typical audit to finish in under five minutes. A budget
that is merely hoped for is not a budget, so every stage has an explicit
allowance and an explicit overrun behaviour. Overrun never fails the run; it
narrows the claim and says so in the report. The figures are the `BUDGETS` table
in `scripts/collect.py` and the diagnosis reserve in the orchestrator's `run.py`.

| Stage | Budget | On overrun |
|---|---|---|
| robots.txt and sitemaps | 15s | Continue without the remaining sitemaps. Discovery falls back to navigation and links, and `crawl.sampling.strategy` records which sources were used. |
| Agent-facing files | 5s total, three paths | Paths not answered in time are recorded with `status: null`; the audit continues. |
| First-party crawl | 90s | Stop. `crawl.fetched` is reported against `crawl.discovered`, so every denominator stays honest. |
| Rendering | 60s, at most 3 pages at once | Remaining pages stay fetch-only and a `render` degradation names how many; raw-versus-rendered rules count only rendered pages. |
| User-agent probe | 15s, two URLs | Fewer identities are probed; an absent entry means unprobed, never "served nothing". |
| Off-site probe | 90s | Partial results, `external.truncated = true`, and the frontier size still reported. |
| Diagnosis and synthesis | 25s | Six diagnostics over one local file, then assembly: no network. A diagnostic that fails or times out costs only its own rules, reported as `not_assessed`. |
| **Global** | **300s**, enforced by the orchestrator | Whatever completed is reported; the rest becomes `not_assessed` with reason `budget_exhausted`. |

The stage budgets sum to 300s exactly. They are not expected to all be spent: on
the sites this build was verified against, audits run one at a time finished in
14 to 178 seconds.

## Why the numbers are these numbers

**15s for robots.txt and sitemaps.** Small documents on the critical path of
everything else. A site that cannot serve them in fifteen seconds is telling us
something, and waiting longer buys nothing.

**5s for the agent-facing files.** Three small fixed-path requests whose only job
is to establish whether each file exists. Nothing downstream depends on them, and
no major assistant is documented to read them, so they get a hard ceiling.

**90s for the crawl.** The only stage whose cost scales with site size, so it
gets the largest single share. Requests to one host are sequential and spaced by
its `Crawl-delay`, which is what makes the audit polite and what makes this the
binding constraint on a slow site.

**60s and 3 concurrent renders.** Rendering costs an order of magnitude more per
page than fetching, and its job is a raw-versus-rendered comparison across a
sample, not a census. One page of every page type is rendered first, so the
budget buys a baseline for every template before it buys depth in any. Each page
gets a capped attempt (an 8s navigation cap under an 11s kill) and, only if that
returns under 500 characters of text, a second attempt with a 5s quiet period
under a 9s kill, for pages that assemble their content after the load event. The
reasons, measured, are D13 in `docs/DECISIONS.md`. Three concurrent renders is a
memory bound on an ordinary machine, and the renderer shares the CPU with
everything else: run one audit at a time.

**15s for the user-agent probe.** The one stage that deliberately varies the
request identity. Two URLs under up to eight identities is at most sixteen
requests, and repeating it across more pages would be probing rather than
measuring.

**90s for the off-site probe.** A handful of keyless providers, queried in order
within one budget. A slow third party may cost its own hits; it cannot consume
the audit.

**25s for diagnosis.** Every diagnostic reads one local JSON file and applies
bounded arithmetic, and assembly renders two files. It does not approach the
figure.

## Sampling under the budget

Sampling is stratified by page type, not breadth-first, because a breadth-first
crawl of a 50,000-page catalogue spends the whole budget inside one template and
then reports a site-wide conclusion from it. Strata are derived from URL patterns
before fetching, because sampling has to choose what to fetch before any content
exists; each page's own `page_type` is decided from its content afterwards, and
the two can differ. Every finding counts from the pages actually fetched and
states its denominator: "12 of 12 sampled product pages" is a claim a reader can
check, and "product pages lack the fact" is not.
