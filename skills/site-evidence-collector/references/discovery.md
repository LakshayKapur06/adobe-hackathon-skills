# Discovery, sampling and deduplication

How the collector decides which pages to fetch, and when two URLs are one page.
The decisions here set every denominator in every finding, so each is stated
precisely, along with the failure it prevents. What they decided is recorded in
the bundle's `discovery` object, which rules read. `errors[]` carries a
free-text account of the same events for a human reader, and no rule parses it.

## Scope

The crawl stays on the resolved origin's host and its www/apex twin. A URL on
the twin host is rewritten onto the origin host before it is fetched, so the
same page is never fetched twice under two hosts and the twin's robots.txt is
never needed. Subdomains are out of scope: a shop or blog on its own subdomain
is often a different platform with its own robots.txt.

A link counts as `internal` when its registrable domain matches the page's.
Without the Public Suffix List, which is not in the standard library, the
registrable domain is approximated from a compact list of common two-label
suffixes (`co.uk`, `com.au`, `co.in` and so on). It never decides which URLs
are fetched: scope is decided by host.

## The frontier

Discovered URLs come from three places, recorded in
`crawl.sampling.strategy`:

- `sitemap`: sitemaps named in robots.txt, or `/sitemap.xml` when none are
  named; indexes are followed, up to ten files
- `nav`: links on the home page, and on the rendered home page when a browser
  is available, because the shell of a client-rendered site carries little of
  its navigation
- `linkgraph`: links on each page fetched

URLs are normalised before they are compared: fragments and tracking parameters
(`utm_*`, `gclid` and similar) are dropped, and path case and every other query
parameter are kept.

## Page types and stratified sampling

Every discovered URL is classified by its path into one of the closed
`page_type` values. After the fetch, the page's own JSON-LD can confirm or
override that classification:

| Signal | Confidence |
|---|---|
| Home paths | 0.95 |
| JSON-LD agrees with the URL | 0.9 |
| JSON-LD decides a URL-less case | 0.8 |
| JSON-LD overrides the URL | 0.7 |
| URL alone | 0.6 |
| `other` | 0.3 |

`other` is a real classification, not a failure.

Policy words that are also things a shop sells or a newsroom covers ("cookies",
"shipping", "returns", "legal", "terms", "warranty", "grievance") mark a policy
page only within two path segments of the root, where policy pages live
(`/cookies`, `/pages/shipping`, `/legal/terms`). Deeper, as in a grocery
category `/pc/snacks/biscuits-cookies/cookies/` or a news video about a
grievance hearing, they are ordinary words. Unambiguous names such as
`privacy-policy` count at any depth.

The home page is always fetched first. After that, each pick goes to the page
type sampled least so far, so no single template can consume the budget. Within
a type, URLs without a query string come first (sorted and faceted variants are
the least representative pages a site has), then shallower and shorter paths.

`crawl.sampling.strata` records how many URLs of each type were discovered and
how many were sampled, so every finding can state its denominator.

## Redirects: pages are keyed on their final URL

Two addresses often lead to one page: on one verified site, `/about` and
`/about/` both redirected to `/about-landing/`. Counting both inflates every denominator, so the
crawl keys pages on their final URL after redirects and keeps the set of final
URLs already held:

- a sampled URL that is itself a held final URL is never fetched
- a redirect hop onto a held final URL is never followed
- a URL whose redirects end on a held final URL is dropped

Each of those counts once in `discovery.collapsed_redirect_target`. This is
identity of address, not of content, so it applies whether or not a browser is
available.

## Soft-404 and URL echo

Some sites return 200 and a substantive page for every path, including paths
that cannot exist. At the extreme, one byte-identical shell is served
everywhere, `/robots.txt` included, and all content is assembled in the
browser. Left undetected, that inflates `crawl.discovered` with copies of one
page and makes every denominator fictional. Handled crudely, it blinds the crawl
on exactly the kind of site that most needs rendering.

**The probe.** Once per audit, two paths that cannot exist are requested, where
robots.txt permits. They are sixteen hex digits derived from the host rather
than random, because they are recorded in `discovery.soft_404.probe_paths` and
two runs over one site must produce the same bundle. The outcome:

| Result | `soft_404.detected` | `soft_404.baseline_text_hash` |
|---|---|---|
| Either path returns non-2xx or a trivial body | false | null |
| Both return 2xx, identical substantive bodies | true | the hash of their extracted text |
| Both return 2xx, bodies differ (the page echoes the path) | true | null: no single baseline exists |

**Deduplication by content depends on capability, and the distinction is
load-bearing.** Every URL it drops counts once in
`discovery.collapsed_duplicate_text`.

- **Rendering available:** pages are deduplicated by their *rendered* text.
  Raw identity across distinct URLs is never a reason to skip a page; it is the
  observation itself, and render-and-extraction needs those pages present to
  make it.
- **Rendering unavailable:** a URL whose raw text matches the soft-404 baseline
  contributes no distinct content. It is not counted in `crawl.fetched` and not
  placed in any stratum. That count is what lets a rule tell a genuinely small
  site from one that echoes a single page at every URL.
- **Rendering unavailable, canonical aliases:** a URL whose extracted text is
  identical to an earlier page *and* that is joined to it by a canonical link
  (either page's canonical naming the other, or both naming the same URL) is
  the same document under a second address. It is collapsed. Both conditions
  are required, and this rule is never applied when rendering is available,
  because a client-rendered shell often carries one fixed canonical on every
  route.

**When every URL is the same shell and rendering is unavailable,** the bundle
holds one representative page, the home page, and a `page-content` degradation
says plainly that no page-level content exists in the server response at all.
That is not `not_assessed`. It is the observation a render-and-extraction rule
reports, and the audit never presents it as a one-page site.

**The agent-facing discovery files use the same baseline.** `well_known[].present`
requires a 2xx, a non-empty body, and extracted text that does not match the
soft-404 baseline, so a shell served at `/llms.txt` is not recorded as a file.

## Rendering

When a Chromium-family browser is found — through `CHROME_PATH`,
`CHROMIUM_PATH` or `BROWSER_PATH`, then the PATH, then each platform's standard
install locations — and passes a render probe, the collector renders the home
page during discovery and every kept page afterwards: at most three at once,
10s per page, 60s for the stage.

Rendering is navigate, wait, dump the DOM; the browser receives nothing but a
URL, so it cannot click, type, submit or inject. Each page gets two attempts
inside its 10s:

1. **Settled.** The page loads and then gets a 2s quiet period of virtual time,
   so content a client-rendered page assembles just after load is captured.
   Killed at 5s if it has not returned.
2. **Capped.** Only if the first returns nothing: the navigation is stopped
   after 3s of real time and the DOM is dumped as it stands.

The two cannot be combined into one attempt. Virtual time stops advancing while
any network request is pending, and a navigation cap set alongside it runs on
the same virtual clock, so a page with a request that never settles would wait
forever. One verified site's home page did exactly that on Chrome 153 until killed at
20s; plain navigation returned it in 1.1s. A page rendered the second way is
listed in `errors[]`, so a reader knows it had no quiet period.

A page that fails both attempts stays fetch-only, and a `render` degradation
records how many did; a render failure never fails the run. With
`--no-render`, or with no working browser, every page is fetch-only and a
`render` degradation says why.

Known limit: the browser also fetches the page's own scripts and stylesheets,
exactly as a visitor's browser would. The page URL itself is checked against
robots.txt; those subresource requests are not individually checked, which a
plain browser does not support. Images are not loaded at all.
