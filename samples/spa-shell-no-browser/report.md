# AI-readiness audit: 127.0.0.1

Audited 2026-09-13T12:28:04Z. 1 of 1 discovered pages sampled; no browser was available; no off-site sources were consulted; 1.0 seconds.

## At a glance

- **2 problems found:** 1 critical, 0 high, 1 medium, 0 low.
- **1 suggested improvement** that go beyond the problems.
- **6 checks passed**, and **15 could not be assessed** on this run (listed at the end, with what would make them checkable).

This run had limits that narrow what it could see: render: rendering disabled (--no-render); page-content: every one of 1 sampled URL returned the same server response as a path that cannot exist, and rendering is unavailable; external: third-party egress disabled (--no-egress); claims: no claim was promoted from the candidates observed.

## Problems, in the order to fix them

### 1. The server response carries no text on any sampled page

**Critical** · priority **P0** (fix first: it blocks a stage of being found or used) · Being found and cited by AI assistants · confidence high · effort high

- **What we saw:** The only 2xx HTML page sampled returned fewer than 200 characters of text in the server response (http://127.0.0.1:60142/: 0). The site answered two paths that cannot exist with the identical response, so every URL serves one empty application shell. No page was rendered because no browser was available, so what a browser would add is not measured here; what a fetcher that does not execute JavaScript receives is observed directly.
- **Why it matters:** The server response is all a non-rendering fetcher ever reads.
- **What improves:** Any text at all reaching a fetcher that does not execute scripts.
- **What to do:** Serve content in the server response instead of only through client-side scripts.
- **Where:** The application shell served at the URLs cited.
- **How:** Adopt server-side rendering or static generation for the site's routes, or place a prerendering step in front of them serving the same rendered HTML to every client; re-run this audit with a browser available to measure the gap per template.
- **How you will know it worked:** A plain fetch of the home page and each cited URL returns at least the page's main heading and body text in the server response.
- **Pages behind this:** http://127.0.0.1:60142/ (1 of 1 examined) · rule RND-002

### 2. The home page carries no machine-readable organization identity

**Medium** · priority **P2** (plan it in) · Being found and cited by AI assistants · confidence high · effort low

> **Fix RND-002 first.** the server response carries little or no page text, so this absence may disappear once the content is server-rendered; re-assess after that fix

- **What we saw:** The home page's server response has 0 JSON-LD nodes and none describes an organization; no 2xx about page carries one either, and no microdata or RDFa is present.
- **Why it matters:** It states the entity behind the site explicitly instead of leaving it to be inferred from a name.
- **What improves:** Entity disambiguation.
- **What to do:** Add an Organization JSON-LD block, or the most specific subtype that applies, to the home page.
- **Where:** The home page template's <head>, in the server response (http://127.0.0.1:60142/).
- **How:** Emit @type, name, url, logo and sameAs with the organization's profile URLs on other sites, plus legalName and address where they apply, generated server-side.
- **How you will know it worked:** The home page's server response contains a JSON-LD node of an Organization type with at least name and url.
- **Pages behind this:** http://127.0.0.1:60142/ (1 of 1 examined) · rule IDM-001

## Suggested improvements beyond the problems

### 1. Optional and speculative: publish /llms.txt

**Low** · priority **P2** (plan it in) · Being found and cited by AI assistants · confidence low · effort low

- **What we saw:** /llms.txt at http://127.0.0.1:60142 answered HTTP 200 and is not present. No major assistant is documented to read this file, so this is listed only as a low-cost hedge, not as a gap.
- **Why it matters:** It is a proposed convention some tools read; no major assistant documents consuming it, which is why this is proactive and never a finding.
- **What improves:** A possible, undocumented discovery channel for tools that adopt the convention.
- **What to do:** Publish a plain-text /llms.txt summarising what the site is and linking its key pages.
- **Where:** http://127.0.0.1:60142/llms.txt
- **How:** Write a short markdown file: one paragraph describing the organization, then links to the pages that answer the questions people ask about it. Keep it consistent with those pages.
- **How you will know it worked:** /llms.txt answers 200 with content that is not the site's soft-404 page.
- **Pages behind this:** http://127.0.0.1:60142/llms.txt · rule PRO-001

## Checks that passed

- **ACC-001:** robots.txt imposes no restrictions (parse_reason not_plausibly_robots), so no crawler is excluded by it
- **ACC-002:** robots.txt answered HTTP 200, which lets compliant crawlers proceed
- **ACC-003:** No primary page template carries noindex or none (1 primary 2xx page examined)
- **ACC-004:** No primary page template carries nosnippet or max-snippet:0 (1 primary 2xx page examined)
- **ACC-006:** No named AI crawler identity was refused where browser-ua received 2xx (1 URL compared)
- **ACC-008:** robots.txt imposes no restrictions (parse_reason not_plausibly_robots), so no crawler is excluded by it

## What could not be checked, and how to make it checkable

- **ACC-005:** fewer than 2 non-root 2xx pages declare a canonical (0 found). *To enable:* re-run with a larger sample; a site declaring no canonicals has nothing for this rule to check
- **ACC-007:** the sample holds 1 URL, fewer than 5. *To enable:* needs at least 5 sampled URLs behind a home page that answers this client
- **ACC-009:** robots.txt was not parsed. *To enable:* applies only to sitemaps declared in a parsed robots.txt that answer this client
- **ANS-001:** long-form article or doc pages of at least 1500 words sampled, news reporting excluded: 0; the recommendation needs 2. *To enable:* applies only to sites publishing long articles or documentation
- **ARR-001:** 2xx pages with a recorded time to first byte: 1; 5 are needed for a median. *To enable:* needs at least 5 sampled pages that answer this client
- **FRC-001:** article pages classified with confidence >= 0.8 sampled: 0; 2 are needed. *To enable:* applies to sites publishing articles; for articles in other languages, check by hand that each shows a date and carries datePublished
- **FRC-002:** the off-site probe did not run (egress False, attempted False), so no claim was checked. *To enable:* run with network access to public records and without --no-egress
- **IDM-002:** no organization node on a 2xx page declares sameAs with its value recorded. *To enable:* applies only to organization markup that declares sameAs
- **IDM-003:** no 2xx page carries any JSON-LD to parse. *To enable:* applies only to pages that emit JSON-LD
- **IDM-004:** no 2xx page carries a commerce node (Product or Offer) stating a price above zero. *To enable:* applies only to pages with Offer or price markup
- **PRO-002:** no organization name was promoted with at least medium confidence and a plain short value, so there is nothing safe to build a prompt panel around. *To enable:* state the organization's name in Organization JSON-LD
- **PRO-003:** no 2xx home or about page carries organization markup to add identity links to. *To enable:* add Organization JSON-LD to the home page first; identity links are then checked on the next audit
- **PRO-004:** 0 sampled articles show a visible date; at least 2 are needed to judge the article template. *To enable:* only applies to sites that publish dated articles; audit the blog or news section's URL directly to sample more of them
- **RND-001:** no browser was available, so no page could be rendered and compared with its server response. *To enable:* install a Chromium-based browser (Chrome, Edge or Chromium) and re-run without --no-render
- **RND-003:** no browser was available, so no page could be rendered and compared with its server response. *To enable:* install a Chromium-based browser (Chrome, Edge or Chromium) and re-run without --no-render

## How this audit was run

- Read-only: every request was a GET, robots.txt was obeyed for this site and for every other site consulted, and nothing on the site was changed.
- Sampling: stratified:nav; home 1 of 1.
- Off-site coverage: none, over 0 enumerable sources. This is not a search of the whole web.
- Severity is computed from what was observed (whether a stage is blocked, how widely, and how central the content is), capped by confidence; it is never assigned by hand.
