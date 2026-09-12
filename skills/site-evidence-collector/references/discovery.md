# Discovery, sampling and deduplication

How the collector decides which pages to fetch, and when two URLs are one page.
The decisions here set every denominator in every finding, so each is stated
precisely, along with the failure it prevents.

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

The home page is always fetched first. After that, each pick goes to the page
type sampled least so far, so no single template can consume the budget. Within
a type, URLs without a query string come first (sorted and faceted variants are
the least representative pages a site has), then shallower and shorter paths.

`crawl.sampling.strata` records how many URLs of each type were discovered and
how many were sampled, so every finding can state its denominator.

## Soft-404 and URL echo

Some sites return 200 and a substantive page for every path, including paths
that cannot exist. At the extreme, one byte-identical shell is served
everywhere, `/robots.txt` included, and all content is assembled in the
browser. Left undetected, that inflates `crawl.discovered` with copies of one
page and makes every denominator fictional. Handled crudely, it blinds the crawl
on exactly the kind of site that most needs rendering.

**The probe.** Once per audit, two paths that cannot exist (`/<16 random hex>`)
are requested, where robots.txt permits. The random paths themselves are never
recorded. The outcome depends on what comes back:

| Result | Recorded in `errors[]` with stage `discovery` |
|---|---|
| Either path returns non-2xx or a trivial body | Nothing; the site has normal 404s |
| Both return 2xx, identical substantive bodies | `soft-404 baseline sha256:<hash>: two paths that cannot exist both returned status <n> with this identical body` |
| Both return 2xx, bodies differ | A note that the site echoes the requested path, so no single baseline exists and URL-level deduplication is not possible |

**Deduplication depends on capability, and the distinction is load-bearing.**

- **Rendering available:** pages are deduplicated by their *rendered* text.
  Raw identity across distinct URLs is never a reason to skip a page; it is the
  observation itself, and render-and-extraction needs those pages present to
  make it.
- **Rendering unavailable:** a URL whose raw text matches the soft-404 baseline
  contributes no distinct content. It is not counted in `crawl.fetched` and not
  placed in any stratum, and the count is recorded:
  `collapsed <n> of <m> fetched URLs whose server response matched the soft-404 baseline <hash>; …`.
  That record is what lets a rule tell a genuinely small site from one that
  echoes a single page at every URL.
- **Rendering unavailable, canonical aliases:** a URL whose extracted text is
  identical to an earlier page *and* that is joined to it by a canonical link
  (either page's canonical naming the other, or both naming the same URL) is
  the same document under a second address — `/` and `/index.html`, typically.
  It is collapsed and recorded as `collapsed <n> URLs that are the same
  document as an earlier page …`. Both conditions are required. Neither alone
  is enough, and this rule is never applied when rendering is available,
  because a client-rendered shell often carries one fixed canonical on every
  route.

**When every URL is the same shell and rendering is unavailable,** the bundle
holds one representative page, the home page, and a `page-content` degradation
says plainly that no page-level content exists in the server response at all.
That is not `not_assessed`. It is the observation a render-and-extraction rule
reports, and the audit never presents it as a one-page site.

## Rendering

When a Chromium-family browser is found — through `CHROME_PATH`,
`CHROMIUM_PATH` or `BROWSER_PATH`, then the PATH, then each platform's standard
install locations — and passes a render probe, the collector renders the home
page during discovery and every kept page afterwards:

- at most three at once
- 20s per page
- 60s for the stage

Rendering is navigate, wait, dump the DOM. The browser receives nothing but a
URL, so it cannot click, type, submit or inject. A page that fails or times out
stays fetch-only, and a `render` degradation records how many did; a render
failure never fails the run. With `--no-render`, or with no working browser,
every page is fetch-only and a `render` degradation says why.

Known limit: the browser also fetches the page's own scripts and stylesheets,
exactly as a visitor's browser would. The page URL itself is checked against
robots.txt; those subresource requests are not individually checked, which a
plain browser does not support. Images are not loaded at all.
