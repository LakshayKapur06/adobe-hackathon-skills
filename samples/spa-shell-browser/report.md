# AI-readiness audit: 127.0.0.1

Audited 2026-09-13T16:12:22Z. 5 of 5 discovered pages sampled; a browser rendered pages; no off-site sources were consulted; 5.0 seconds.

## At a glance

- **3 problems found:** 1 critical, 1 high, 1 medium, 0 low.
- **1 suggested improvement** that go beyond the problems.
- **8 checks passed**, and **12 could not be assessed** on this run (listed at the end, with what would make them checkable).

This run had limits that narrow what it could see: external: third-party egress disabled (--no-egress); claims: no claim was promoted from the candidates observed.

## Problems, in the order to fix them

### 1. Page content exists only after JavaScript runs (site-wide)

**Critical** · priority **P0** (fix first: it blocks a stage of being found or used) · Being found and cited by AI assistants · confidence high · effort high

- **What we saw:** 5 of 5 rendered pages compared across the site are JavaScript-dependent: at least 80% of their rendered text is missing from the server response. Examples: http://127.0.0.1:55528/ (server response 0 characters, rendered page 583); http://127.0.0.1:55528/warranty (server response 0 characters, rendered page 1968); http://127.0.0.1:55528/aboutus (server response 0 characters, rendered page 1712); http://127.0.0.1:55528/grievance (server response 0 characters, rendered page 1558); http://127.0.0.1:55528/extended-warranty (server response 0 characters, rendered page 2111). Every sampled HTML page was rendered.
- **Why it matters:** Text assembled in the browser does not exist for a fetcher that does not run scripts.
- **What improves:** Extraction of the page's text from the fetched response.
- **What to do:** Put the page's substance in the server response for the templates across the site.
- **Where:** The routes cited and the rendering configuration of their templates.
- **How:** Enable the framework's server rendering or static generation for these routes, or put a prerendering step in front of them serving the rendered HTML to every client alike; then confirm with a plain fetch that headings and body text are present.
- **How you will know it worked:** A plain fetch with no JavaScript of every cited URL returns the main headings and body text, so that at least a fifth of what the rendered page shows is already in the server response.
- **Pages behind this:** http://127.0.0.1:55528/, http://127.0.0.1:55528/aboutus, http://127.0.0.1:55528/extended-warranty, http://127.0.0.1:55528/grievance, http://127.0.0.1:55528/warranty (5 of 5 examined) · rule RND-001

### 2. Distinct pages declare the home page as their canonical URL

**High** · priority **P1** (fix next) · Being found and cited by AI assistants · confidence high · effort medium

- **What we saw:** 4 of 4 non-root 2xx pages that declare a canonical name http://127.0.0.1:55528/, the site root, as their canonical URL. Each tells an indexer it is a duplicate of the home page.
- **Why it matters:** A canonical is per-page by definition, so a fixed value in a shared layout declares every page a duplicate of one.
- **What improves:** Deep pages indexed as themselves.
- **What to do:** Make each page's rel=canonical name its own URL.
- **Where:** The shared layout, head component or application shell that emits rel=canonical on the URLs cited.
- **How:** Generate the href from the request path, or from the router's resolved route in a client-rendered application, and make sure the server response carries the per-page value.
- **How you will know it worked:** Every cited URL returns a canonical equal to its own final URL in the server response.
- **Pages behind this:** http://127.0.0.1:55528/aboutus, http://127.0.0.1:55528/extended-warranty, http://127.0.0.1:55528/grievance, http://127.0.0.1:55528/warranty (4 of 4 examined) · rule ACC-005

### 3. The home page carries no machine-readable organization identity

**Medium** · priority **P2** (plan it in) · Being found and cited by AI assistants · confidence high · effort low

> **Fix RND-001 first.** the server response carries little or no page text, so this absence may disappear once the content is server-rendered; re-assess after that fix

- **What we saw:** The home page's server response has 0 JSON-LD nodes and none describes an organization; no 2xx about page carries one either, and no microdata or RDFa is present.
- **Why it matters:** It states the entity behind the site explicitly instead of leaving it to be inferred from a name.
- **What improves:** Entity disambiguation.
- **What to do:** Add an Organization JSON-LD block, or the most specific subtype that applies, to the home page.
- **Where:** The home page template's <head>, in the server response (http://127.0.0.1:55528/).
- **How:** Emit @type, name, url, logo and sameAs with the organization's profile URLs on other sites, plus legalName and address where they apply, generated server-side.
- **How you will know it worked:** The home page's server response contains a JSON-LD node of an Organization type with at least name and url.
- **Pages behind this:** http://127.0.0.1:55528/ (1 of 1 examined) · rule IDM-001

## Suggested improvements beyond the problems

### 1. Optional and speculative: publish /llms.txt

**Low** · priority **P2** (plan it in) · Being found and cited by AI assistants · confidence low · effort low

- **What we saw:** /llms.txt at http://127.0.0.1:55528 answered HTTP 200 with no file: an empty body or the site's page for unknown addresses, so no /llms.txt is published. No major assistant is documented to read this file, so this is listed only as a low-cost hedge, not as a gap.
- **Why it matters:** It is a proposed convention some tools read; no major assistant documents consuming it, which is why this is a suggestion and never reported as a problem.
- **What improves:** A possible, undocumented discovery channel for tools that adopt the convention.
- **What to do:** Publish a plain-text /llms.txt summarising what the site is and linking its key pages.
- **Where:** http://127.0.0.1:55528/llms.txt
- **How:** Write a short markdown file: one paragraph describing the organization, then links to the pages that answer the questions people ask about it. Keep it consistent with those pages.
- **How you will know it worked:** /llms.txt answers 200 with content that is not the site's soft-404 page.
- **Pages behind this:** http://127.0.0.1:55528/llms.txt · rule PRO-001

## Checks that passed

- **ACC-001:** robots.txt imposes no restrictions (parse_reason not_plausibly_robots), so no crawler is excluded by it
- **ACC-002:** robots.txt answered HTTP 200, which lets compliant crawlers proceed
- **ACC-003:** No primary page template carries noindex or none (2 primary 2xx pages examined)
- **ACC-004:** No primary page template carries nosnippet or max-snippet:0 (2 primary 2xx pages examined)
- **ACC-006:** No named AI crawler identity was refused where browser-ua received 2xx (2 URLs compared)
- **ACC-007:** 0 of 5 sampled URLs returned 404, 410 or 5xx, below the 2-URL and 10% threshold
- **ACC-008:** robots.txt imposes no restrictions (parse_reason not_plausibly_robots), so no crawler is excluded by it
- **ARR-001:** Median server response time (time to first byte minus connection setup) is 1 ms across 5 pages, within web.dev's 1,800 ms poor boundary

## What could not be checked, and how to make it checkable

- **ACC-009:** robots.txt was not parsed. *To enable:* applies only to sitemaps declared in a parsed robots.txt that answer this client
- **ANS-001:** long-form article or doc pages of at least 1500 words sampled, news reporting excluded: 0; the recommendation needs 2. *To enable:* applies only to sites publishing long articles or documentation
- **FRC-001:** article pages classified with confidence >= 0.8 sampled: 0; 2 are needed. *To enable:* applies to sites publishing articles; for articles in other languages, check by hand that each shows a date and carries datePublished
- **FRC-002:** the off-site probe did not run (egress False, attempted False), so no claim was checked. *To enable:* run with network access to public records and without --no-egress
- **IDM-002:** no organization node on a 2xx page declares sameAs with its value recorded. *To enable:* applies only to organization markup that declares sameAs
- **IDM-003:** no 2xx page carries any JSON-LD to parse. *To enable:* applies only to pages that emit JSON-LD
- **IDM-004:** no 2xx page carries a commerce node (Product or Offer) stating a price above zero. *To enable:* applies only to pages with Offer or price markup
- **PRO-002:** no organization name was promoted with at least medium confidence and a plain short value, so there is nothing safe to build a prompt panel around. *To enable:* state the organization's name in Organization JSON-LD
- **PRO-003:** no 2xx home or about page carries organization markup to add identity links to. *To enable:* add Organization JSON-LD to the home page first; identity links are then checked on the next audit
- **PRO-004:** 0 sampled articles show a visible date; at least 2 are needed to judge the article template. *To enable:* only applies to sites that publish dated articles; audit the blog or news section's URL directly to sample more of them
- **RND-002:** rendered pages were available, so RND-001 made the stronger raw-versus-rendered comparison instead. *To enable:* none needed: this rule covers only runs with no rendered page
- **RND-003:** only 0 product pages met the bar (rendered, product with classifier confidence >= 0.6, not already JavaScript-dependent, text sidecars present); 5 are needed. *To enable:* applies to sites with at least 5 sampled, rendered product pages

## Terms used in this report

- **2xx:** a page that loaded successfully: the server answered with a status code from 200 to 299.
- **robots.txt:** a file at the root of a site telling automated crawlers which pages they may fetch.
- **noindex:** an instruction, in a page's robots meta tag or its X-Robots-Tag header, telling search engines to leave the page out of their index.
- **nosnippet:** an instruction telling search engines not to quote the page's text.
- **canonical:** a tag naming the address search engines should treat as a page's main URL.
- **JSON-LD:** structured data in a page's code describing the organization, a product or an article in a form machines read directly.
- **sameAs:** a JSON-LD property listing the organization's profiles elsewhere, such as Wikipedia or LinkedIn, so a machine can tell which organization this is.
- **server response:** the HTML a site sends before any JavaScript runs. Many crawlers and AI fetchers read only this.
- **rendered:** what a page contains after a browser has run its JavaScript.
- **sitemap:** a file listing a site's pages for crawlers.
- **time to first byte:** how long the server takes to start sending a page.

## How this audit was run

- Read-only: every request was a GET, robots.txt was obeyed for this site and for every other site consulted, and nothing on the site was changed.
- Sampling: stratified:nav; home 1 of 1, about 1 of 1, policy 3 of 3.
- Off-site coverage: none, over 0 enumerable sources. This is not a search of the whole web.
- Severity is computed from what was observed (whether a stage is blocked, how widely, and how central the content is), capped by confidence; it is never assigned by hand.
