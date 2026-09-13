# AI-readiness audit: 127.0.0.1

Audited 2026-09-13T16:58:09Z. 14 of 14 discovered pages sampled; a browser rendered pages; off-site sources were consulted; 39.0 seconds.

## At a glance

- **6 problems found:** 0 critical, 2 high, 3 medium, 1 low.
- **2 suggested improvements** that go beyond the problems.
- **11 checks passed**, and **5 could not be assessed** on this run (listed at the end, with what would make them checkable).

## Problems, in the order to fix them

### 1. Pages of type product refuse indexing

**High** · priority **P1** (fix next) · Being found and cited by AI assistants · confidence high · effort low

- **What we saw:** 7 of 7 sampled 2xx product pages carry noindex or none in their robots meta tag or X-Robots-Tag header (100%). A page excluded from the index cannot be retrieved into an answer.
- **Why it matters:** The directive is applied after fetching, so no amount of crawl access recovers the page.
- **What improves:** Index admission for the affected template.
- **What to do:** Remove noindex (or none) from the product page template, or from the header rule adding it.
- **Where:** The robots meta tag in the product template or the server/CDN rule setting X-Robots-Tag, on the URLs cited.
- **How:** Find the template or SEO-plugin setting that applies the directive to the whole type, often a 'discourage indexing' toggle left on from staging, and scope it to the pages actually meant to be excluded.
- **How you will know it worked:** A plain fetch of every cited URL returns no noindex or none in either the robots meta tag or X-Robots-Tag.
- **Pages behind this:** http://127.0.0.1:58409/products/canyon-jacket, http://127.0.0.1:58409/products/delta-socks, http://127.0.0.1:58409/products/harbor-hoodie, http://127.0.0.1:58409/products/meadow-scarf, http://127.0.0.1:58409/products/ridge-gloves and 2 more (7 of 7 examined) · rule ACC-003

### 2. Product prices appear only after rendering

**High** · priority **P1** (fix next) · Being found and cited by AI assistants · confidence medium · effort medium

- **What we saw:** Rendered 7 eligible product pages; a price appears in the rendered text of 5 and in neither the server text nor server JSON-LD of those 5. Examples: http://127.0.0.1:58409/products/trail-tee (rendered shows ₹999.00); http://127.0.0.1:58409/products/summit-cap (rendered shows ₹999.00); http://127.0.0.1:58409/products/delta-socks (rendered shows ₹999.00); http://127.0.0.1:58409/products/canyon-jacket (rendered shows ₹999.00); http://127.0.0.1:58409/products/harbor-hoodie (rendered shows ₹999.00).
- **Why it matters:** The server response is what a fetcher extracts, and it holds a product without a price.
- **What improves:** The price becomes extractable and quotable.
- **What to do:** Include the price in the server response of the product template, as visible text or Offer JSON-LD.
- **Where:** The product page template and its price component, on the URLs cited.
- **How:** Render the price component on the server, or emit Product with offers.price and offers.priceCurrency in JSON-LD generated server-side.
- **How you will know it worked:** The price appears in the server response, as text or as offers.price JSON-LD, on every cited product URL, verifiable with a plain fetch and no JavaScript.
- **Pages behind this:** http://127.0.0.1:58409/products/canyon-jacket, http://127.0.0.1:58409/products/delta-socks, http://127.0.0.1:58409/products/harbor-hoodie, http://127.0.0.1:58409/products/summit-cap, http://127.0.0.1:58409/products/trail-tee (5 of 7 examined) · rule RND-003

### 3. Organization markup declares sameAs links that identify nothing

**Medium** · priority **P2** (plan it in) · Being found and cited by AI assistants · confidence high · effort low

- **What we saw:** 1 of 12 2xx pages carry an organization node (Organization) whose sameAs is declared with 3 entries and not one absolute URL: ["", "", ""].
- **Why it matters:** An empty identity link is noise a consumer has to discard.
- **What improves:** Identity anchoring to external descriptions of the same entity.
- **What to do:** Fill sameAs with the organization's real profile URLs, or remove the property.
- **Where:** The theme or template setting that populates the organization markup's sameAs, usually the social-links configuration.
- **How:** Enter the absolute URLs of the organization's official profiles in the theme's social settings, or edit the template to omit empty entries.
- **How you will know it worked:** Every organization node's sameAs in the server response contains only absolute http or https URLs, or the property is absent.
- **Pages behind this:** http://127.0.0.1:58409/ (1 of 12 examined) · rule IDM-002

### 4. A named AI crawler identity is refused where robots.txt admits it

**Medium** · priority **P2** (plan it in) · Being found and cited by AI assistants · confidence low · effort low

- **What we saw:** The same client sent the same request with different user-agent strings: browser-ua received 2xx, while GPTBot received a refusal (GPTBot: 403 on http://127.0.0.1:58409/, 403 on http://127.0.0.1:58409/pages/about-us). robots.txt admits these agents. This compares two header strings, not a browser against a crawler, and cannot show how requests from the operators' own addresses are treated.
- **Why it matters:** robots.txt admits these crawlers, so a refusal at the server contradicts the site's own policy.
- **What improves:** Admission of the crawler where the policy already grants it.
- **What to do:** Establish whether requests from the named crawler's published address ranges receive 2xx, and if not, remove the user-agent match refusing them.
- **Where:** Server access logs first, then web server, CDN bot-management or firewall rules matching on User-Agent.
- **How:** Filter logs for the crawler's user-agent string, compare source addresses against the operator's published ranges, and check the status verified requests received; if refused, verify identity by address instead of refusing by string.
- **How you will know it worked:** Server logs show 2xx responses to requests from the crawler's published address ranges on the cited URLs.
- **Pages behind this:** http://127.0.0.1:58409/, http://127.0.0.1:58409/pages/about-us (2 of 2 examined) · rule ACC-006

### 5. Structured price contradicts the prices shown on the page

**Medium** · priority **P2** (plan it in) · Being found and cited by AI assistants · confidence high · effort medium

- **What we saw:** On 2 of 2 2xx pages with price markup, the page shows currency amounts and none equals the marked-up price: http://127.0.0.1:58409/products/meadow-scarf (markup 1499.00); http://127.0.0.1:58409/products/ridge-gloves (markup 1499.00).
- **Why it matters:** Markup is taken as the authoritative statement, so a stale or base price there is repeated as fact.
- **What improves:** The structured statement of price matches what a buyer sees.
- **What to do:** Make the marked-up price equal the price the page shows.
- **Where:** The product template's Offer markup on the URLs cited, and the data source it reads the price from.
- **How:** Generate offers.price from the same variable that renders the visible price, including sale and selected-variant logic, rather than from a separate field.
- **How you will know it worked:** On every cited URL, the offers.price value in the server response equals a price shown in the page's visible text.
- **Pages behind this:** http://127.0.0.1:58409/products/meadow-scarf, http://127.0.0.1:58409/products/ridge-gloves (2 of 2 examined) · rule IDM-004

### 6. URLs the site links to or lists return not-found or server errors

**Low** · priority **P3** (when convenient) · Being found and cited by AI assistants · confidence high · effort medium

- **What we saw:** 2 of 14 sampled URLs (14%), all discovered from the site's own sitemap, navigation or links, returned an error: 404 http://127.0.0.1:58409/products/retired-logo-tee, 404 http://127.0.0.1:58409/products/retired-classic-tee.
- **Why it matters:** Each reference sends crawlers to an error and spends crawl they would otherwise use on real pages.
- **What improves:** Every advertised address yields content.
- **What to do:** Restore, redirect, or stop linking the cited URLs.
- **Where:** The sitemap generator and the navigation or link templates that produced the cited URLs.
- **How:** For each cited URL restore the page, add a 301 to its current equivalent, or remove it from the sitemap and linking template; for 5xx, check application logs for the failing route.
- **How you will know it worked:** A plain fetch of every cited URL returns 2xx, a redirect to a 2xx, or the URL no longer appears in the sitemap or on linking pages.
- **Pages behind this:** http://127.0.0.1:58409/products/retired-classic-tee, http://127.0.0.1:58409/products/retired-logo-tee (2 of 14 examined) · rule ACC-007

## Suggested improvements beyond the problems

### 1. Monitor how assistants describe northwind threads with a fixed prompt panel

**Medium** · priority **P2** (plan it in) · Being found and cited by AI assistants · confidence medium · effort low

- **What we saw:** This audit observes the site, not assistants' answers, by design. 1 claim was promoted with at least medium first-party confidence, which gives a panel whose expected answers are known: What is northwind threads, and what is its official website? (expected: 127.0.0.1).
- **Why it matters:** Whether a fix changes what assistants say is not observable from the site, so it has to be measured where it happens.
- **What improves:** Turns the audit's fixes into something whose effect can be seen.
- **What to do:** Run a fixed panel of questions about northwind threads against the assistants that matter to the site, on a schedule, and record each answer against the expected value.
- **Where:** Outside the site: a shared sheet or a scheduled script owned by whoever owns the brand's facts.
- **How:** Use exactly these prompts each time, record date, assistant, answer and whether it matches: What is northwind threads, and what is its official website? (expected: 127.0.0.1). Re-run after each fix from this report to see whether it moved anything.
- **How you will know it worked:** A dated record of answers per assistant exists, and each answer is marked as matching or not matching the site's stated value.
- **Pages behind this:** http://127.0.0.1:58409/ · rule PRO-002

### 2. Optional and speculative: publish /llms.txt

**Low** · priority **P2** (plan it in) · Being found and cited by AI assistants · confidence low · effort low

- **What we saw:** /llms.txt at http://127.0.0.1:58409 answered HTTP 404, so no /llms.txt is published. No major assistant is documented to read this file, so this is listed only as a low-cost hedge, not as a gap.
- **Why it matters:** It is a proposed convention some tools read; no major assistant documents consuming it, which is why this is a suggestion and never reported as a problem.
- **What improves:** A possible, undocumented discovery channel for tools that adopt the convention.
- **What to do:** Publish a plain-text /llms.txt summarising what the site is and linking its key pages.
- **Where:** http://127.0.0.1:58409/llms.txt
- **How:** Write a short markdown file: one paragraph describing the organization, then links to the pages that answer the questions people ask about it. Keep it consistent with those pages.
- **How you will know it worked:** /llms.txt answers 200 with content that is not the site's soft-404 page.
- **Pages behind this:** http://127.0.0.1:58409/llms.txt · rule PRO-001

## Checks that passed

- **ACC-001:** No answer-time retrieval crawler (OAI-SearchBot, PerplexityBot, Claude-SearchBot, Googlebot, Bingbot) is shut out by the * group in robots.txt
- **ACC-002:** robots.txt answered HTTP 200, which lets compliant crawlers proceed
- **ACC-004:** No primary page template carries nosnippet or max-snippet:0 (9 primary 2xx pages examined)
- **ACC-005:** Distinct pages do not declare the home page as canonical (0 of 11 non-root pages with a canonical do)
- **ACC-008:** No answer-time retrieval crawler is excluded by name in robots.txt
- **ACC-009:** Every assessable sitemap declared in robots.txt returned a readable sitemap (1 file)
- **ARR-001:** Median server response time (time to first byte minus connection setup) is 1 ms across 12 pages, within web.dev's 1,800 ms poor boundary
- **IDM-001:** The home page's JSON-LD states an organization identity
- **IDM-003:** Every JSON-LD block parsed on 8 pages carrying JSON-LD
- **PRO-003:** Identity links (sameAs) are declared in the markup, so none is recommended; whether their values identify anything is checked by IDM-002
- **RND-001:** No template depends on JavaScript for its text: 0 of 12 rendered pages compared are JavaScript-dependent, below the template threshold

## What could not be checked, and how to make it checkable

- **ANS-001:** long-form article or doc pages of at least 1500 words sampled, news reporting excluded: 0; the recommendation needs 2. *To enable:* applies only to sites publishing long articles or documentation
- **FRC-001:** article pages classified with confidence >= 0.8 sampled: 0; 2 are needed. *To enable:* applies to sites publishing articles; for articles in other languages, check by hand that each shows a date and carries datePublished
- **FRC-002:** no founding-year claim with medium or high first-party confidence and an unambiguous name was matched to a Wikidata record (frontier: 3 sources). *To enable:* applies when the site states a founding year and its organization has a Wikidata item naming the site as official website
- **PRO-004:** 0 sampled articles show a visible date; at least 2 are needed to judge the article template. *To enable:* only applies to sites that publish dated articles; audit the blog or news section's URL directly to sample more of them
- **RND-002:** rendered pages were available, so RND-001 made the stronger raw-versus-rendered comparison instead. *To enable:* none needed: this rule covers only runs with no rendered page

## Terms used in this report

- **2xx:** a page that loaded successfully: the server answered with a status code from 200 to 299.
- **robots.txt:** a file at the root of a site telling automated crawlers which pages they may fetch.
- **noindex:** an instruction, in a page's robots meta tag or its X-Robots-Tag header, telling search engines to leave the page out of their index.
- **nosnippet:** an instruction telling search engines not to quote the page's text.
- **X-Robots-Tag:** an HTTP header that carries the same instructions as the robots meta tag.
- **canonical:** a tag naming the address search engines should treat as a page's main URL.
- **JSON-LD:** structured data in a page's code describing the organization, a product or an article in a form machines read directly.
- **sameAs:** a JSON-LD property listing the organization's profiles elsewhere, such as Wikipedia or LinkedIn, so a machine can tell which organization this is.
- **server response:** the HTML a site sends before any JavaScript runs. Many crawlers and AI fetchers read only this.
- **rendered:** what a page contains after a browser has run its JavaScript.
- **user agent:** the name a client sends with each request; crawlers identify themselves with names such as GPTBot or PerplexityBot.
- **sitemap:** a file listing a site's pages for crawlers.
- **time to first byte:** how long the server takes to start sending a page.

## How this audit was run

- Read-only: every request was a GET, robots.txt was obeyed for this site and for every other site consulted, and nothing on the site was changed.
- Sampling: stratified:sitemap+nav; home 1 of 1, product 9 of 9, category 2 of 2, about 1 of 1, policy 1 of 1.
- Off-site coverage: keyless, over 3 enumerable sources. This is not a search of the whole web.
- Severity is computed from what was observed (whether a stage is blocked, how widely, and how central the content is), capped by confidence; it is never assigned by hand.
