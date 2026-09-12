# Budgets — staying under five minutes without lying about coverage

The handout requires a typical audit to finish in under five minutes. A budget
that is merely hoped for is not a budget, so every stage has an explicit
allowance and an explicit overrun behaviour. Overrun never fails the run; it
narrows the claim and says so in the report.

| Stage | Budget | On overrun |
|---|---|---|
| robots + sitemap | 15s | Continue without the sitemap. Discovery falls back to navigation and the link graph, and `crawl.sampling.strategy` records that. |
| Well-known probe | 5s total, three paths | Paths not answered in time are recorded with `status: null`; the audit continues. |
| First-party crawl | 90s | Stop. Report `crawl.fetched` against `crawl.discovered` so every denominator stays honest. |
| Rendering | 60s, at most 3 concurrent renders | Remaining pages stay fetch-only and are marked degraded; render-delta rules on them become `not_assessed`. |
| External probe | 90s | Partial results, `external.truncated = true`, and the frontier size still reported. |
| Diagnosis + synthesis | 40s | Local and fast; no network, no overrun path needed. |
| **Global** | **300s**, enforced by the orchestrator | Whatever completed is reported; the rest becomes `not_assessed` with reason `budget_exhausted`. |

## Why the numbers are these numbers

**15s for robots and sitemaps.** Both are single small documents on the critical
path of everything else. A site that cannot serve them in fifteen seconds is
telling us something, and waiting longer buys nothing.

**5s for the well-known probe.** Three small fixed-path requests whose only
job is to establish whether each file exists. Nothing downstream depends on
them, and no major assistant is documented to read them, so they get a hard
ceiling rather than a share that could grow. The 5s was taken from the
diagnosis stage's headroom, which keeps the stage budgets summing to the 300s
global deadline.

**90s for the crawl.** The crawl is the only stage whose cost scales with site
size, so it gets the largest single share. With bounded concurrency and typical
response times this samples enough pages per stratum for the minimum-evidence
clauses of the content rules to be satisfiable on an ordinary site.

**60s and 3 concurrent renders.** Rendering is an order of magnitude more
expensive per page than fetching, and its only job is to establish a
raw-versus-rendered delta. That is a comparison across a sample, not a census,
so a bounded subset answers the question. Three concurrent renders is a
memory-safety bound on an ordinary developer machine, not a throughput target.

**90s for the external probe.** Several independent providers are queried and
each is capped individually — Common Crawl is hard-limited to 10 seconds and is
never allowed to block, being the slowest and least valuable of the keyless set.
A slow third party must not be able to consume the audit.

**40s for diagnosis.** Every diagnostic reads one local JSON file and applies
bounded arithmetic. This is generous on purpose: the remaining headroom in the
300s global budget lives here.

The stage budgets sum to 300s exactly. They are not expected to all be spent —
a typical small site finishes well inside the crawl allowance — but the sum is
the guarantee.

## Sampling under the budget

Sampling is stratified by page type, not breadth-first, because a breadth-first
crawl of a 50,000-page catalogue spends the entire budget inside one template
and then reports a site-wide conclusion from it. Strata are derived from
URL patterns, sitemap structure and navigation, and each stratum's `discovered`
and `sampled` counts are written to the bundle so that every downstream finding
can state its denominator.

Every finding states its scope and denominator, and severity accounts for
sampled breadth. "Crawled 12 product pages; 0/12 contain the fact" is a claim a
reader can check. "Product pages lack the fact" is not.
