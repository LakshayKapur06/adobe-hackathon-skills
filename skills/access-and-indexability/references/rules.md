# Access and Indexability — rule set

Every rule below is written in the canonical block defined in
`docs/RULE_FORMAT.md`. One engineering vocabulary across all six diagnostics,
not six voices. CI validates that each block has all fourteen fields present and
non-empty, that every field path named under **Evidence read** exists in
`schemas/evidence.schema.json`, and that the rule count declared below matches
the number of blocks in this file.

## Mechanism owned

Can a machine legally and technically reach the content at a stable address?
This is the first of the three retrieval gates — be let in, be readable, be
quotable — and a failure here makes every downstream gate unreachable. The rules
in this file cover AI-crawler policy in robots.txt, a robots.txt that answers
with errors, user-agent-conditional refusal, `noindex` and `nosnippet` in meta
robots and `X-Robots-Tag`, canonicals that collapse distinct pages into the home
page, advertised URLs that return errors, and sitemaps robots.txt declares but
that cannot be read. Redirect chains, hreflang and
canonical host mismatches were considered and cut; the reasons are recorded in
`tests/rule-review.md`.

## Not owned by this skill

Content quality once reached (`answerability`). Whether the response body
actually contains the substance (`render-and-extraction`). Entity identity and
markup validity (`identity-and-markup`). Rendering of any kind: this skill reads
what the collector observed and renders nothing itself.

## Evidence this skill may read

This skill reads `evidence/evidence.json` and nothing else. It never touches the
network. Every field path a rule consumes must appear in this list, and every
path in this list must exist in the evidence schema — CI enforces both
directions, which is what makes fabricated evidence impossible.

- `robots`
- `robots.ai_agents`
- `robots.groups`
- `robots.fetched`
- `robots.status`
- `robots.sitemaps`
- `sitemaps`
- `sitemaps[].url`
- `sitemaps[].status`
- `sitemaps[].parse_ok`
- `crawl`
- `crawl.blocked_by_robots`
- `crawl.discovered`
- `crawl.fetched`
- `pages[].url`
- `pages[].final_url`
- `pages[].status`
- `pages[].redirect_chain`
- `pages[].headers.x_robots_tag`
- `pages[].meta_robots`
- `pages[].canonical`
- `pages[].canonical_self`
- `pages[].lang`
- `pages[].hreflang`
- `ua_probe`
- `ua_probe[].url`
- `ua_probe[].user_agent`
- `ua_probe[].status`
- `ua_probe[].text_len`
- `ua_probe[].text_hash`
- `well_known`
- `well_known[].path`
- `well_known[].present`
- `well_known[].status`
- `pages[].page_type`
- `site.resolved_origin`
- `site.registrable_domain`
- `site.detected_locales`
- `schema_version`
- `pages[].fetched_at`
- `pages[].provenance.layer`
- `pages[].provenance.method`
- `robots.parse_ok`
- `robots.parse_reason`
- `discovery`
- `discovery.soft_404`
- `discovery.soft_404.detected`
- `discovery.soft_404.baseline_text_hash`
- `discovery.soft_404.probe_paths`
- `discovery.collapsed_duplicate_text`
- `discovery.collapsed_redirect_target`

## Rule budget

Rules defined: 9 of a maximum 12.

The cap is deliberate. A thirteenth rule means something must be cut or merged.
Rule-count inflation reads as padding under this rubric, and a false positive
costs more than a miss.

## Definitions shared by the rules below

**Answer-time retrieval crawlers.** Of the eight agents in `robots.ai_agents`,
four fetch pages into an index that an assistant searches when it answers, as
documented by their operators: `OAI-SearchBot` (ChatGPT search), `PerplexityBot`
(Perplexity's search index, which Perplexity states is not used for training),
`Claude-SearchBot` (Claude's search results) and `Googlebot` (the Search index
that AI Overviews draw from). The other four govern training or reuse rather than answer-time
retrieval: `GPTBot` and `ClaudeBot` collect training data, `CCBot` builds the
open Common Crawl corpus, and `Google-Extended` is a use-control token with no
crawler behind it. Excluding a training agent changes what a model may know
from its training data; it does not remove a page from any answer-time index.
The rules separate the two because the consequences, and the remediation, are
different. OpenAI and Anthropic both document that each of their crawlers is
governed independently, so a site can refuse training without refusing
citation. One limit of the tracked set is stated rather than hidden:
user-initiated fetchers such as `ChatGPT-User`, `Claude-User` and
`Perplexity-User` are not tracked, since they fetch on a person's request
rather than crawling, and Perplexity documents that its user fetcher generally
ignores robots.txt. This table is kept here, in one place, so that when an operator
changes what a crawler is for, one edit updates every rule that relies on it.

**Primary page types.** `home`, `product`, `article`, `doc` and `about`: the
pages that carry what a site is for. `category` is excluded because keeping
thin archive and facet listings out of the index is a deliberate, widespread
consolidation practice; `contact` and `policy` are excluded because they are
rarely the answer to anything. `other` is never counted toward firing a rule:
it is the classifier saying it cannot place the page, and a finding about a
page we cannot place could not name what was lost.

**A 2xx page.** An entry in `pages[]` whose `status` is 200-299. A refused or
errored page is recorded with its status and an empty body, so every rule that
reads page content counts only 2xx pages.

## Rules

### ACC-001 — Answer-time retrieval crawler shut out by a wildcard robots.txt group

- **Mechanism:** a crawler that robots.txt disallows at `/` does not fetch the
  site, so its index holds none of the site's pages and the assistant it serves
  cannot retrieve, quote or cite any of them. When the exclusion comes from the
  `*` group rather than a group naming the crawler, the site never made a
  decision about that crawler at all: it was swept up by a rule written for
  something else, which is the unintended form of this failure.
- **Signal:** at least one answer-time retrieval crawler (`OAI-SearchBot`,
  `PerplexityBot`, `Claude-SearchBot`, `Googlebot`) has the verdict `disallowed`, and no entry in
  `robots.groups` names that crawler, so the verdict comes from the `*` group.
- **Evidence read:** `robots.parse_ok`, `robots.parse_reason`,
  `robots.ai_agents`, `robots.groups`, `site.resolved_origin`.
- **Threshold:** one retrieval crawler is enough. Justification: the verdict is
  a literal reading of one file, not a sample, so there is no variance to
  average out; a single disallowed retrieval crawler already removes the whole
  site from one assistant's index, and a higher count would only measure how
  many assistants are affected, which the finding reports separately.
- **Minimum evidence:** `robots.parse_ok == true` and `robots.parse_reason ==
  "ok"`. Only a parsed file can exclude a crawler by rule. The other two
  values are resolved, not guessed: `absent_4xx` and `not_plausibly_robots` mean
  RFC 9309 imposes no restrictions, so every crawler is admitted and the rule
  emits `checks_passed` saying so; `unreachable`, `server_error` and
  `rate_limited` record every agent as `disallowed` without a single rule having
  been read, so this rule emits `not_assessed` and the situation belongs to
  ACC-002.
- **False-positive controls:** the unreachable-family verdicts are excluded by
  the minimum evidence, so a robots.txt that returned 503 never reads as a
  policy; a crawler whose exclusion comes from a group naming it is excluded,
  since that is a stated decision rather than collateral, and belongs to
  ACC-008;
  the verdict is the collector's RFC 9309 matching, in which a group naming a
  crawler always overrides `*`, so a site that disallows `*` and then allows
  `Googlebot` by name correctly reads `Googlebot` as allowed.
- **Legitimate exceptions:** a crawler excluded by a group that names it is a
  deliberate policy, often a publisher's licensing position; detected by a
  matching `user_agent` in `robots.groups`, and never reported by this rule.
  ACC-008 reports it instead, as a consequence to weigh rather than a defect. A site that intends to be private, such as a pre-launch or staging
  host, is not detectable from robots.txt alone and is not excepted; the
  finding is still true of it.
- **Confidence:** high, always. The observation is the parsed file itself, and
  a partial exclusion is not less certain, only narrower, which `breadth`
  already records; lowering confidence for it as well would count the same
  fact twice.
- **Impact inputs:** `blocking = true` (the crawler fetches nothing it is
  disallowed from). `breadth = "site"` when the governing `*` group has no
  `allow` entries, otherwise `"section"`, because re-allowed paths leave part of
  the site reachable. `content_importance = "primary"`, since a root exclusion
  covers every primary page.
- **Status:** found
- **Symptom tags:** invisible
- **Remediation:** what: add a group naming each excluded retrieval crawler
  that allows the content paths, placed so it overrides the `*` group. Where:
  the robots.txt at `site.resolved_origin`. Why: a named group
  replaces the `*` group entirely for that crawler under RFC 9309, so the
  crawler is readmitted without loosening the rule for anything else. How:
  `User-agent: OAI-SearchBot` followed by `Allow: /` and the site's existing
  private-path `Disallow` lines, repeated per crawler; keep training agents
  such as `GPTBot` under whatever policy the owner chooses, since they do not
  serve answer-time retrieval. Mechanism improved: admission to the retrieval
  index of each assistant named in the finding.
- **Success criteria:** re-fetching robots.txt yields `allowed` for every
  retrieval crawler named in the finding, with the owner's disallowed private
  paths still disallowed.
- **Effort:** low

### ACC-002 — robots.txt answers with a server error or rate limit, so compliant crawlers fetch nothing

- **Mechanism:** RFC 9309 section 2.3.1.4 says a crawler that cannot obtain
  robots.txt because of a server error MUST assume complete disallow. Google
  documents the practical form: it stops crawling the site for the first 12
  hours, then crawls against its last good copy for up to 30 days, so new and
  changed pages stop being picked up while the error lasts. A crawler with no
  earlier copy has nothing to fall back on and fetches nothing. RFC 9309 does
  not name 429; Google's documentation sets it apart from the other 4xx codes,
  which it treats as "no robots.txt", and groups it with server errors as a
  signal to crawl less, which is why it is counted here.
- **Signal:** `robots.parse_reason` is `server_error` (a 5xx) or `rate_limited`
  (a 429).
- **Evidence read:** `robots.fetched`, `robots.status`, `robots.parse_reason`,
  `site.resolved_origin`.
- **Threshold:** a single observed 5xx or 429 on robots.txt. Justification: the
  collector requests robots.txt once per host, so there is no second
  observation to require; the uncertainty this leaves about whether the error
  persists is carried by `confidence` and `status`, not hidden by a threshold
  that could never be met.
- **Minimum evidence:** `robots.fetched == true` and a non-null `robots.status`,
  meaning a server actually answered. `parse_reason == "unreachable"` (no
  response at all: timeout, DNS or connection failure) is `not_assessed`,
  because it cannot separate a robots.txt defect from a host that is down or a
  network path that failed between us and it.
- **False-positive controls:** only an HTTP response counts, so a network
  failure on our side cannot fire the rule; 4xx responses are excluded, since
  under RFC 9309 a 4xx means no restrictions apply; the finding states the exact
  status received and that it was observed once.
- **Legitimate exceptions:** a transient outage or a deploy in progress at the
  moment of the audit; not detectable from one request, which is why the rule
  never claims more than `risk` at `low` confidence and its success criteria
  ask for repeated fetches. A rate limit triggered by this audit itself is
  excluded by construction: robots.txt is the first request the collector makes
  to the host.
- **Confidence:** low, always. One response cannot show that the condition
  persists, and persistence is what turns it from a blip into an exclusion.
- **Impact inputs:** `blocking = true` (a compliant crawler fetches nothing).
  `breadth = "site"` (robots.txt governs the whole host). `content_importance =
  "primary"`.
- **Status:** risk
- **Symptom tags:** invisible
- **Remediation:** what: make the robots.txt endpoint answer 200 with the
  intended policy, or 404 if there is none. Where: the server, CDN or web
  application firewall rule serving `/robots.txt` at `site.resolved_origin`. Why: under
  RFC 9309 only those answers let a crawler proceed; an error answer is read as
  "crawl nothing". How: serve robots.txt as a static file outside the
  application and exempt it from rate limiting and bot challenges, then check
  the server logs for the status crawlers have been receiving. Mechanism
  improved: admission of every compliant crawler.
- **Success criteria:** repeated fetches of robots.txt over at least a day
  return 200 or 404, never 5xx or 429.
- **Effort:** low

### ACC-003 — Primary page templates refuse indexing

- **Mechanism:** a `noindex` directive, in a robots meta tag or an
  `X-Robots-Tag` header, tells an indexing crawler to drop the page even after
  fetching it. A page absent from the index cannot be retrieved into an answer.
  When the directive sits in a template it removes every page of that type at
  once, which is a configuration error rather than an editorial choice.
- **Signal:** 2xx pages of a primary page type carry `noindex` or `none` in
  `meta_robots`, or in `headers.x_robots_tag` either unscoped or scoped to a
  retrieval crawler (`googlebot`, `oai-searchbot`, `perplexitybot`).
- **Evidence read:** `pages[].url`, `pages[].final_url`, `pages[].status`,
  `pages[].page_type`, `pages[].meta_robots`, `pages[].headers.x_robots_tag`,
  `pages[].canonical`, `pages[].canonical_self`.
- **Threshold:** per primary page type, the directive is present on at least 2
  sampled 2xx pages of that type and on at least 50% of them; or it is present
  on the home page, which is its own type with exactly one member.
  Justification: a CMS applies robots directives per template, so a template
  defect shows on all or nearly all pages of a type, while an editorial
  `noindex` (a draft, a retired article, a duplicate) shows on a minority. One
  page of a type is exactly what an editorial choice looks like, so it never
  fires alone. At 25% a sample of four articles with one intentional exclusion
  would fire; at 100% a template with a single hand-overridden page would be
  missed.
- **Minimum evidence:** at least one 2xx page of a primary page type. With none,
  emit `not_assessed`: there is nothing whose indexability could be judged.
- **False-positive controls:** only 2xx pages count; tokens are matched exactly
  after lower-casing, so `noodp`, `noimageindex` and `max-image-preview` never
  match; `X-Robots-Tag` directives scoped to any crawler other than the three
  retrieval crawlers are ignored; a page whose `canonical` is non-null and not
  self is excluded, because it has declared another URL as the one to index and
  `noindex` on the duplicate is consistent with that; `other`, `category`,
  `contact` and `policy` pages never count.
- **Legitimate exceptions:** internal search results, thank-you and account
  pages, which classify as `other` and are excluded; syndicated copies pointing
  at the original through `canonical`, excluded by the canonical control; a
  site that intends to stay out of indexes entirely, which is not detectable and
  not excepted, since the finding is still true of it. A directive written in a
  crawler-named meta tag such as `<meta name="googlebot">` is not recorded by
  the collector, which reads only `name="robots"`; that case is a miss, never a
  false positive.
- **Confidence:** high when the affected type has at least 3 affected pages or
  the affected page is the home page; medium when the type fires on exactly 2.
- **Impact inputs:** `blocking = true` (an unindexed page cannot be retrieved).
  `breadth = "site"` when the affected pages span at least 2 page types and make
  up at least 50% of all sampled 2xx pages, otherwise `"section"`, one finding
  per page type. `content_importance = "primary"`, since only primary types can
  fire.
- **Status:** found
- **Symptom tags:** invisible
- **Remediation:** what: remove `noindex` from the named page template, or from
  the header rule emitting it. Where: the robots meta tag in the template for
  the page type named in the finding, or the server or CDN rule adding
  `X-Robots-Tag`, whichever the evidence refs show. Why: the directive is
  applied after fetching, so no amount of crawl access recovers the page. How:
  find the template or SEO-plugin setting that applies the directive to the
  whole type, often a "discourage indexing" toggle left on from staging, and
  scope it to the pages actually meant to be excluded. Mechanism improved:
  index admission for the affected template.
- **Success criteria:** a plain fetch of every URL cited in the finding returns
  no `noindex` or `none` in either the robots meta tag or `X-Robots-Tag`.
- **Effort:** low

### ACC-004 — Primary page templates forbid snippets

- **Mechanism:** `nosnippet` and `max-snippet:0` permit a page to be indexed
  but forbid showing any of its text. Google's robots meta documentation
  states that `nosnippet` applies to AI Overviews and AI Mode and "will also
  prevent the content from being used as a direct input" to them, and that
  `max-snippet:0` is equivalent to `nosnippet`. A page carrying either can be
  found in Search yet cannot feed or be quoted in Google's AI answers. Other
  operators do not document their handling, so the finding states the effect
  Google documents and claims nothing further.
- **Signal:** 2xx pages of a primary page type that are not excluded from the
  index carry `nosnippet` or `max-snippet:0` in `meta_robots`, or in
  `headers.x_robots_tag` unscoped or scoped to `googlebot`.
- **Evidence read:** `pages[].url`, `pages[].final_url`, `pages[].status`,
  `pages[].page_type`, `pages[].meta_robots`, `pages[].headers.x_robots_tag`.
- **Threshold:** the same shape as ACC-003, for the same reason: at least 2
  sampled 2xx pages of a type and at least 50% of them, or the home page.
  A template applies snippet controls to every page of a type; an editor
  restricts one page. `max-snippet` with any positive value does not fire,
  because a positive limit still permits a quote and we cannot observe how long
  a quote an answer needs.
- **Minimum evidence:** at least one 2xx page of a primary page type that does
  not carry `noindex` or `none`. Otherwise `not_assessed`.
- **False-positive controls:** only 2xx pages count; pages carrying `noindex`
  or `none` are excluded, so one page never produces both this finding and
  ACC-003's; exact token matching, so `max-snippet:-1` (no limit) and
  `max-snippet:160` never match; header directives scoped to crawlers other
  than `googlebot` are ignored; `other`, `category`, `contact` and `policy`
  pages never count.
- **Legitimate exceptions:** licensed or paywalled content whose owner permits
  indexing but not reproduction; this is an owner decision the evidence cannot
  distinguish from a template error, so confidence is capped at medium rather
  than the case being silently excepted. Snippet controls applied only to part
  of a page with `data-nosnippet` are not recorded by the collector and cannot
  fire this rule.
- **Confidence:** medium at most, because a deliberate reproduction policy and a
  template error produce the same markup; low when the affected type fires on
  exactly 2 pages.
- **Impact inputs:** `blocking = true` for the quoting stage (the text may not
  be shown at all). `breadth` derived exactly as in ACC-003. `content_importance
  = "primary"`.
- **Status:** found
- **Symptom tags:** invisible, misrepresented
- **Remediation:** what: remove `nosnippet` or `max-snippet:0` from the named
  template, or replace a page-wide `nosnippet` with `data-nosnippet` on only the
  passages that must not be reproduced. Where: the robots meta tag or
  `X-Robots-Tag` rule for the page type in the finding. Why: a page-wide snippet
  ban forbids quoting every passage, including the ones the owner wants
  attributed. How: edit the template's robots meta output, or the server rule,
  and mark any genuinely restricted passages with `data-nosnippet`. Mechanism
  improved: quotability in answers that cite the page.
- **Success criteria:** every URL cited in the finding returns neither
  `nosnippet` nor `max-snippet:0` in its robots meta tag or `X-Robots-Tag`.
- **Effort:** low

### ACC-005 — Distinct pages declare the home page as their canonical URL

- **Mechanism:** `rel=canonical` tells an indexer which URL stands for a page.
  When distinct pages all name the home page, each one tells the indexer it is
  a duplicate of the home page, so the indexer may keep only the home page and
  drop the rest, and a retrieval system working from that index then has
  nothing at the deep URLs to return. The usual cause is a canonical tag
  hard-coded in a shared layout or an application shell.
- **Signal:** 2xx pages whose final URL is not the site root declare a
  `canonical` that is not self and whose path is `/` on a host within the
  site's registrable domain.
- **Evidence read:** `pages[].url`, `pages[].final_url`, `pages[].status`,
  `pages[].page_type`, `pages[].canonical`, `pages[].canonical_self`,
  `site.resolved_origin`, `site.registrable_domain`.
- **Threshold:** at least 2 such pages with distinct paths, making up at least
  50% of the non-root 2xx pages that declare any canonical. Justification: one
  page pointing at the home page can be a deliberate consolidation, such as a
  retired campaign page, and is exactly the case `canonical` exists for; two
  different paths doing so and forming at least half of the pages that declare
  a canonical is the pattern a shared template produces and an editor does not.
- **Minimum evidence:** at least 2 non-root 2xx pages declaring a canonical.
  Otherwise `not_assessed`.
- **False-positive controls:** only 2xx pages count; root aliases are not
  treated as distinct pages (`/index.html`, `/index.php`, `/home`,
  `/default.aspx`, and the root with only a query string), since those genuinely
  are the home page; a canonical on a different registrable domain is out of
  scope, because cross-domain canonicals are the normal mechanism for
  syndication; pages the collector found to be copies are already gone, since a
  URL whose extracted text matches a kept page, or matches the soft-404
  baseline, is collapsed before it reaches `pages[]` (D14, D15), so every page
  this rule counts carries distinct text.
- **Legitimate exceptions:** a one-page site whose other routes are anchors
  into the home page; detected because such routes produce the same text as the
  home page and are collapsed by the collector before this rule sees them.
  Consolidation of retired pages into the home page; detected by being a single
  page, which the threshold never fires on.
- **Confidence:** high when at least 3 distinct pages are affected; medium when
  exactly 2.
- **Impact inputs:** `blocking = false` (canonical is a hint that an indexer may
  override when content plainly differs). `breadth = "site"` when the affected
  pages make up at least 50% of all sampled 2xx pages, otherwise `"section"`.
  `content_importance = "primary"` when any affected page is of a primary page
  type, otherwise `"secondary"`.
- **Status:** found
- **Symptom tags:** invisible
- **Remediation:** what: make each page emit a canonical naming its own URL.
  Where: the shared layout, head component or application shell that emits the
  `rel=canonical` link on the URLs cited in the finding. Why: a canonical is
  per-page by definition, so a fixed value in a shared layout declares every
  page a duplicate of one. How: generate the href from the request path, or
  from the router's resolved route in a client-rendered application, and make
  sure the server response carries the per-page value rather than relying on
  script to replace it. Mechanism improved: deep pages indexed as themselves.
- **Success criteria:** every URL cited in the finding returns a canonical equal
  to its own final URL in the server response.
- **Effort:** medium

### ACC-006 — A named AI crawler identity is refused where robots.txt admits it

- **Mechanism:** a server or firewall rule matching the crawler's user-agent
  string can refuse a crawler that robots.txt admits. The crawler then fetches
  nothing despite a permissive policy, and the owner reading their own
  robots.txt sees no reason for it.
- **Signal:** on the same URL, the `browser-ua` entry in `ua_probe` received a
  2xx and an entry for `GPTBot`, `ClaudeBot`, `PerplexityBot`, `OAI-SearchBot`
  or `CCBot` received 401, 403, 404, 406, 410 or 451.
- **Evidence read:** `ua_probe[].url`, `ua_probe[].user_agent`,
  `ua_probe[].status`, `robots.ai_agents`.
- **Threshold:** the refusal holds for that agent on every probed URL where
  `browser-ua` received a 2xx (one or two URLs). Justification: a rule keyed on
  a user-agent string applies to every path, so the same refusal on both URLs is
  what such a rule produces, while a refusal on one URL and not the other points
  to a path-specific rule or a momentary limit instead.
- **Minimum evidence:** at least one probed URL on which `browser-ua` received a
  2xx and at least one named agent was probed. When every identity including
  `browser-ua` was refused, emit `not_assessed`: the site refused this client,
  and nothing about how it treats real crawlers can be inferred from that.
- **False-positive controls:** 429 and 5xx are excluded, because a limit or an
  outage can arrive mid-probe; `Googlebot` is excluded entirely, because
  Google publishes both its crawler address ranges and a reverse-DNS
  verification procedure for site owners worried about impersonators, so
  refusing unverified Googlebot requests is a documented, widespread defence; an agent that robots.txt disallows is never probed, so it cannot
  appear as refused here; the finding states the comparison actually made, a
  client presenting two different user-agent strings, not a browser against a
  crawler.
- **Legitimate exceptions:** verification of claimed identity: OpenAI
  and Perplexity publish the address ranges of their crawlers, and CDN bot
  management verifies declared bots by published ranges rather than by the
  user-agent string, and an edge that refuses a request claiming to be one of them
  from any other address will also refuse this probe while admitting the real
  crawler. The evidence cannot distinguish that from a user-agent block, because
  this collector can only ever present the header and never the crawler's
  network origin. That is why the rule is `risk` at `low` confidence, and why
  the remediation begins with checking the server logs rather than changing
  anything.
- **Confidence:** low, always, for the reason given under legitimate
  exceptions.
- **Impact inputs:** `blocking = true` for that agent. `breadth = "site"` when
  the home page is among the refused URLs, otherwise `"section"`.
  `content_importance = "primary"`.
- **Status:** risk
- **Symptom tags:** invisible
- **Remediation:** what: establish whether requests from the named crawler's
  published address ranges receive 2xx, and if they do not, remove the
  user-agent match refusing them. Where: server access logs first, then the web
  server, CDN bot-management or firewall rules that match on `User-Agent`. Why:
  robots.txt admits this crawler, so a refusal at the server contradicts the
  site's own stated policy. How: filter the logs for the crawler's user-agent
  string, compare the source addresses against the operator's published ranges,
  and check the status those verified requests received; if verified requests
  are refused, change the matching rule to verify identity by address instead of
  refusing by string. Mechanism improved: admission of that crawler where the
  policy already grants it.
- **Success criteria:** the server logs show 2xx responses to requests from the
  crawler's published address ranges on the URLs cited in the finding.
- **Effort:** low

### ACC-007 — URLs the site links to or lists return not-found or server errors

- **Mechanism:** every URL the collector sampled was discovered from the site's
  own sitemap, navigation or links, so each one is an address the site
  advertises. A crawler following those references receives an error instead
  of content, and an index or an answer holding the URL points at nothing.
  When a meaningful share of the sample fails, the cause is usually a
  sitemap generator or link template producing addresses that do not exist.
- **Signal:** entries in `pages[]` with `status` 404, 410 or 500-599.
- **Evidence read:** `pages[].url`, `pages[].final_url`, `pages[].status`,
  `site.resolved_origin`.
- **Threshold:** at least 2 such pages and at least 10% of the entries in
  `pages[]`. Justification: a single dead URL in a sample of thirty is the
  ordinary link rot every living site carries and says nothing about how the
  site is built; one in ten sampled addresses failing is well above that
  background and points to a systematic source. Two is required so that a
  small sample, where one page is already 10% or more, cannot fire on one
  broken link.
- **Minimum evidence:** at least 5 entries in `pages[]` and a 2xx entry whose
  `final_url` is the root of `site.resolved_origin`. A refused home page stops the crawl, so the sample never
  exists; that case is `not_assessed`.
- **False-positive controls:** 401, 403 and 429 are excluded, because they are
  refusals addressed to this client, not missing content; a redirect is judged
  by the status at its final URL, not the hop; confidence drops when any
  counted error is a 5xx, because a server error can be transient.
- **Legitimate exceptions:** deliberately retired content served as 410 behind
  a link the site has not yet cleaned up; not distinguishable from link rot and
  counted, which is the correct outcome, since the advertising reference is
  still the defect. A server error caused by a momentary outage during the
  audit; handled by the confidence rule rather than excepted.
- **Confidence:** high when every counted error is 404 or 410; medium when any
  is a 5xx.
- **Impact inputs:** `blocking = true` for the affected URLs (nothing is
  served). `breadth = "site"` when at least 50% of the entries in `pages[]`
  failed, `"section"` when at least 25%, otherwise `"page"`, so the severity
  follows the share of the sample rather than the raw count.
  `content_importance = "secondary"`, because an error response carries no
  content from which to establish what the page was for.
- **Status:** found
- **Symptom tags:** invisible
- **Remediation:** what: stop advertising URLs that do not resolve, and
  restore or redirect the ones that should. Where: the sitemap generator and
  the navigation or link templates that produced the URLs cited in the finding.
  Why: each reference sends crawlers to an error and wastes the crawl they would
  otherwise spend on real pages. How: for each cited URL, either restore the
  page, add a 301 to its current equivalent, or remove it from the sitemap and
  the linking template; for 5xx responses, check the application logs for the
  failing route. Mechanism improved: every advertised address yields content.
- **Success criteria:** a plain fetch of every URL cited in the finding returns
  2xx, a redirect to a 2xx, or the URL no longer appears in the sitemap or on
  the linking pages.
- **Effort:** medium

### ACC-008 — Answer-time retrieval crawler excluded by name in robots.txt

- **Mechanism:** a retrieval crawler disallowed at `/` fetches nothing, so the
  assistant it serves cannot retrieve, quote or cite the site. Here the
  exclusion is written in a group naming that crawler, so it is the owner's
  stated decision, and the audit's job is to make its cost visible, not to
  overrule it. The cost is often unintended all the same: widely copied
  "block AI bots" lists put search crawlers next to training crawlers, although
  OpenAI and Anthropic document each crawler as governed independently and
  Perplexity states its search crawler is not used for training, so refusing
  training never required refusing citation.
- **Signal:** at least one answer-time retrieval crawler (`OAI-SearchBot`,
  `PerplexityBot`, `Claude-SearchBot`, `Googlebot`) has the verdict
  `disallowed`, and an entry in `robots.groups` names that crawler.
- **Evidence read:** `robots.parse_ok`, `robots.parse_reason`,
  `robots.ai_agents`, `robots.groups`, `site.resolved_origin`.
- **Threshold:** one retrieval crawler is enough. Justification: as in ACC-001,
  the verdict is a literal reading of one file with nothing to average, and one
  excluded retrieval crawler already removes the site from one assistant's
  answers.
- **Minimum evidence:** `robots.parse_ok == true` and `robots.parse_reason ==
  "ok"`. `absent_4xx` and `not_plausibly_robots` impose no restrictions and
  emit `checks_passed`; the unreachable family emits `not_assessed`, because it
  records every agent as `disallowed` without a rule having been read.
- **False-positive controls:** training agents (`GPTBot`, `ClaudeBot`, `CCBot`,
  `Google-Extended`) never fire this rule, because excluding them removes no
  page from any answer-time index; the `checks_passed` summary names them so the
  training policy is still on record. A group that names a crawler and allows
  it reads `allowed` and does not fire. The finding's evidence quotes the named
  group, so a reader can see the exclusion is the site's own wording.
- **Legitimate exceptions:** the exclusion is intended, for example a publisher
  withholding content pending a licensing agreement. This is the expected case
  and it is why the rule is `proactive`: it reports a consequence of a
  deliberate choice and never calls that choice a defect. It is detected
  structurally, by the named group, which is what separates this rule from
  ACC-001.
- **Confidence:** high, always. The observation is the parsed file, and the
  rule claims only its consequence, not that the choice was a mistake.
- **Impact inputs:** `blocking = true` for that assistant. `breadth = "site"`
  when the naming group has no `allow` entries, otherwise `"section"`.
  `content_importance = "primary"`. These describe the cost honestly; under
  `contracts-v3` the `proactive` status caps the derived severity at `medium`,
  so a stated policy is never ranked alongside an accidental block.
- **Status:** proactive
- **Symptom tags:** invisible
- **Remediation:** what: decide, per assistant named in the finding, whether
  appearing in its answers is wanted; where it is, readmit only that search
  crawler and leave the training crawlers excluded. Where: the group naming the
  crawler in robots.txt at `site.resolved_origin`. Why: search and training
  crawlers are separate products, so the two decisions can be made separately.
  How: keep `User-agent: GPTBot` with `Disallow: /` if training is refused, and
  change the `User-agent: OAI-SearchBot` or `User-agent: PerplexityBot` group
  from `Disallow: /` to `Allow: /` with the site's private-path `Disallow`
  lines. Mechanism improved: citation eligibility in the assistants readmitted.
- **Success criteria:** re-fetching robots.txt yields `allowed` for each
  retrieval crawler the owner chose to readmit, while the training agents keep
  the verdict the owner chose for them.
- **Effort:** low

### ACC-009 — A sitemap declared in robots.txt cannot be read

- **Mechanism:** a `Sitemap:` line in robots.txt tells every crawler reading the
  file where the site's full list of URLs is, including pages few or no links
  reach. When the declared file errors or is not a sitemap, that list is lost
  and discovery falls back to following links, which reaches deep and poorly
  linked pages late or never. Search engines document sitemaps as a discovery
  input; AI operators do not document their use, so the finding claims the
  lost discovery channel and nothing about any particular assistant.
- **Signal:** a URL listed in `robots.sitemaps` whose entry in `sitemaps[]` has
  a status of 404, 410 or 500-599, or a 2xx status with `parse_ok == false`.
- **Evidence read:** `robots.parse_ok`, `robots.sitemaps`, `sitemaps[].url`,
  `sitemaps[].status`, `sitemaps[].parse_ok`.
- **Threshold:** one failing declared sitemap. Justification: a declaration is a
  literal statement in one file, not a sample, and each failing declaration
  loses a whole URL list; how many of the declared files failed is carried by
  `breadth`, not by the trigger.
- **Minimum evidence:** `robots.parse_ok == true`, a non-empty
  `robots.sitemaps`, and at least one declared URL with a `sitemaps[]` entry
  whose `status` is not null. A declared URL with no entry was not requested,
  because robots.txt disallowed it or the stage budget ran out, and a null
  status means no response arrived; neither is evidence about the file, so with
  no assessable declaration the rule emits `not_assessed`.
- **False-positive controls:** only URLs the site itself declares count, so the
  collector's fallback request for `/sitemap.xml` on a site that declares none
  never fires, since a sitemap is optional; sitemaps reached through a sitemap
  index are not counted, because they are fetched in order under a shared
  budget and one failing child loses far less than a failing declaration; 401,
  403 and 429 are excluded as refusals addressed to this client; gzip-compressed
  sitemaps are decompressed by the collector before parsing, so a `.xml.gz`
  file does not read as unparseable.
- **Legitimate exceptions:** none leaves the site fine: a declaration pointing
  at a retired or broken file is itself the defect, whatever the reason. A
  sitemap over the protocol's 50 MB uncompressed limit reads as unparseable,
  which is correct, because crawlers following the protocol reject it too. An
  outage at the moment of the audit is handled by confidence, not excepted.
- **Confidence:** high when the failure is a 404, 410, or a 2xx that is not a
  sitemap; medium when it is a 5xx, which can be transient.
- **Impact inputs:** `blocking = false` (links still lead crawlers to most
  pages). `breadth = "site"` when every assessable declared sitemap failed,
  otherwise `"section"`. `content_importance = "secondary"`, because a sitemap
  is a discovery aid, not content.
- **Status:** found
- **Symptom tags:** invisible
- **Remediation:** what: make each declared sitemap URL return a valid sitemap,
  or remove declarations that point at retired files. Where: the `Sitemap:`
  lines in robots.txt and the sitemap generator behind each URL cited in the
  finding. Why: a crawler trusts the declaration and does not guess
  alternatives. How: request each declared URL; if it returns an error, fix the
  generator route or correct the path in robots.txt; if it returns an HTML page,
  typically an application shell answering every path, exempt the sitemap path
  from that routing so the XML file is served. Mechanism improved: complete URL
  discovery for every crawler that reads robots.txt.
- **Success criteria:** every URL in the robots.txt `Sitemap:` lines returns 2xx
  and parses as a `urlset` or `sitemapindex` document.
- **Effort:** low
