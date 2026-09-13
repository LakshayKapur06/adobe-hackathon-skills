# Render and Extraction — rule set

Every rule below is written in the canonical block defined in
`docs/RULE_FORMAT.md`. One engineering vocabulary across all six diagnostics,
not six voices. CI validates that each block has all fourteen fields present and
non-empty, that every field path named under **Evidence read** exists in
`schemas/evidence.schema.json`, and that the rule count declared below matches
the number of blocks in this file.

## Mechanism owned

Once reached, is the substance present as machine-readable text? A fact that
exists only after client-side hydration cannot be extracted by a fetcher, so it
cannot be quoted even though a human sees it. The rules here cover pages whose
text exists only after JavaScript, a site whose server response carries no text
at all when no browser is available, and product prices that appear only after
rendering. Facts locked in images, PDFs, canvas or iframes, and content gated
behind an interaction, were considered and cut because the evidence cannot
observe them reliably; the reasons are in `tests/rule-review.md`.

## Not owned by this skill

Markup semantics — whether the fact is expressed as valid `Product` or `Offer`
JSON-LD is `identity-and-markup`. Whether surrounding prose is quotable
(`answerability`). Crawler admission (`access-and-indexability`).

## Evidence this skill may read

This skill reads `evidence/evidence.json` and nothing else. It never touches the
network. Every field path a rule consumes must appear in this list, and every
path in this list must exist in the evidence schema — CI enforces both
directions, which is what makes fabricated evidence impossible.

- `pages[].url`
- `pages[].content_type`
- `pages[].status`
- `pages[].raw.text_len`
- `pages[].raw.hidden_text_len`
- `pages[].raw.text_hash`
- `pages[].raw.text_path`
- `pages[].raw.images`
- `pages[].raw.images[].alt`
- `pages[].raw.images[].text_likely`
- `pages[].raw.iframes`
- `pages[].raw.tables`
- `pages[].raw.headings`
- `pages[].rendered.available`
- `pages[].rendered.text_len`
- `pages[].rendered.text_hash`
- `pages[].rendered.text_path`
- `pages[].rendered.delta_ratio`
- `pages[].rendered.headings`
- `pages[].jsonld[].fields_present`
- `pages[].jsonld[].values`
- `pages[].jsonld[].type`
- `pages[].page_type`
- `pages[].page_type_confidence`
- `pages[].obstructions`
- `run_context.capabilities.js_render`
- `run_context.degradations`
- `crawl.sampling`
- `schema_version`
- `pages[].fetched_at`
- `pages[].provenance.layer`
- `pages[].provenance.method`
- `discovery`
- `discovery.soft_404`
- `discovery.soft_404.detected`
- `discovery.soft_404.baseline_text_hash`
- `discovery.soft_404.probe_paths`
- `discovery.collapsed_duplicate_text`
- `discovery.collapsed_redirect_target`

## Rule budget

Rules defined: 3 of a maximum 12.

The cap is deliberate. A thirteenth rule means something must be cut or merged.
Rule-count inflation reads as padding under this rubric, and a false positive
costs more than a miss.

## Definitions shared by the rules below

**A comparable page.** An entry in `pages[]` with a 2xx `status`, a
`content_type` containing `html`, and `rendered.available == true`. Only such a
page has both a server response and a rendered DOM to compare. Non-HTML
resources are never rendered by the collector, and a refused page has a
deliberately empty body, so neither can show a render gap.

**JavaScript-dependent.** A comparable page whose `rendered.delta_ratio` is at
least 0.8, whose rendered text is at least 200 characters longer than its
server text (`rendered.text_len - raw.text_len >= 200`), and whose server text
counting hidden text is still no more than 20% of the rendered text
(`raw.text_len + raw.hidden_text_len <= 0.2 * rendered.text_len`).
`delta_ratio` is the share of the rendered text that is missing from the
server response's visible text.

Why hidden text is counted in that last condition: a page can ship its whole
text in the server response inside a `display:none` container and reveal it
with script. Its visible server text is near zero and its delta is high, yet a
fetcher that ignores CSS extracts all of it, so "absent from the server
response" would be false. The 20% is the same boundary as the 0.8 ratio,
applied to all server text rather than only the visible part. G2 found the
pattern in miniature (a storefront's reviews in a hidden container) and measured
hidden text at 0 to 376 characters on real pages.

Why 0.8, from the pages measured during the G2 evidence check: server-rendered
templates on a news publisher and on python.org sit at 0.000 to 0.015; Shopify
product pages, which server-render their content and hydrate a variant picker
and review widget on top, sit at 0.04 to 0.24; client-rendered pages, whose
server response carries no text at all, sit at 1.0. A threshold of 0.8 is far
above the widget band and still well below the shells. Halving it to 0.4 would
bring it within reach of a widget-heavy template on a thin page. The 200-character floor stops
a very short page from firing on a line of injected text: 200 characters is
about thirty words, less than a cookie notice, and a page that gains less than
that from rendering has not moved any substance.

**Primary page types.** `home`, `product`, `article`, `doc`, `about`, as in
`access-and-indexability`. `other` is never counted toward a per-type finding,
because the classifier could not place those pages; it does count toward the
site-wide share in RND-001, because a page that exists only after JavaScript
is missing from the server response whatever its type.

**Sidecar text.** RND-003 reads the extracted text files that
`raw.text_path` and `rendered.text_path` point at, which the contract makes
part of the bundle. Paths are relative to the audit working directory, the
parent of `evidence/`.

**How a finding cites its evidence.** Every rule here is page-level, so each
`evidence_ref` cites the page's `pages[].url`, `pages[].provenance.layer`,
`pages[].provenance.method` and `pages[].fetched_at`. The rules are implemented
in `scripts/diagnose.py`, one function per rule, in the order written here.

## Rules

### RND-001 — Page content exists only after JavaScript runs

- **Mechanism:** a fetcher that does not execute JavaScript receives the server
  response and nothing more. When most of a page's text is assembled in the
  browser, that fetcher extracts almost nothing, so the page cannot be indexed,
  retrieved or quoted by it even though a person sees a complete page. Whether a
  given assistant's crawler renders JavaScript is not documented for most of
  them, so the finding claims only what is observed: the text is absent from the
  server response.
- **Signal:** comparable pages that are JavaScript-dependent, either making up at
  least half of all comparable pages, or concentrated in a primary page type.
- **Evidence read:** `pages[].url`, `pages[].status`, `pages[].content_type`,
  `pages[].page_type`, `pages[].raw.text_len`, `pages[].raw.hidden_text_len`,
  `pages[].rendered.available`, `pages[].rendered.text_len`,
  `pages[].rendered.delta_ratio`, `run_context.capabilities.js_render`.
- **Threshold:** site-wide when JavaScript-dependent pages are at least 50% of
  comparable pages, number at least 2, and either include the home page or span
  at least 2 page types; otherwise per primary page type, when
  at least 2 comparable pages of the type are JavaScript-dependent and they are
  at least 50% of that type's comparable pages; or when the home page is
  JavaScript-dependent. Justification: rendering strategy is a property of a
  template or of the whole application, so a real dependency shows on most
  pages sharing it, while a single dependent page, such as one subscription page
  on a server-rendered publisher observed during G2, is a one-off widget page
  and does not describe how the site is built. The home page stands alone
  because it is the one page every visit and every crawl starts from. The
  site-wide trigger needs the home page or two page types because the sample is
  stratified: a storefront whose product listings alone are client-rendered can
  contribute half of the rendered sample from that one template, and calling
  that "the site" would overstate one template as the whole application.
- **Minimum evidence:** `run_context.capabilities.js_render == true` and at least
  2 comparable pages. Without a browser the rule emits `not_assessed` with an
  enabling hint, never a pass: no render gap can be seen without rendering.
- **False-positive controls:** only comparable pages count, so a refused page or
  a non-HTML resource can never read as JavaScript-only; the 0.8 ratio and the
  200-character floor together exclude hydrated widgets and injected notices;
  text present in the server response but hidden with CSS counts as present, so
  a page that reveals server-sent text with script is never called
  JavaScript-dependent;
  pages the render budget did not reach are left out of both numerator and
  denominator and the finding states how many were compared; a page whose
  rendered text merely duplicates another page's never reaches `pages[]`,
  because the collector collapses rendered duplicates (D15).
- **Legitimate exceptions:** an application that is deliberately a tool rather
  than a document, such as a web app behind a sign-in, has nothing to be
  retrieved; not detectable from the bundle, and not excepted, since the text
  is still absent. A site that serves crawlers a prerendered copy through
  dynamic rendering would show a gap to this client and none to a crawler; not
  detectable, because the collector never presents as a crawler while
  rendering, so confidence drops to medium when the site shows no sign of
  being fully client-rendered (see below).
- **Confidence:** high when every JavaScript-dependent page has a server
  response of under 200 characters of text, which leaves no room for a crawler
  to be served anything better from the same response; medium otherwise.
- **Impact inputs:** `blocking = true` for any fetcher that does not execute
  JavaScript (the text is not in the response it receives). `breadth = "site"`
  for the site-wide trigger, otherwise `"section"`, one finding per page type.
  `content_importance = "primary"` when the home page or any primary page type
  is among the affected pages, otherwise `"secondary"`.
- **Status:** found
- **Symptom tags:** invisible, misrepresented
- **Remediation:** what: put the page's substance in the server response, by
  server-side rendering, static generation or prerendering, for the templates
  named in the finding. Where: the routes cited, and the application's rendering
  configuration for their templates; when the JavaScript-dependent pages of a
  section all sit under one path, the finding names that path rather than the
  page type alone, because page types are inferred from URLs and one client-side
  application can be filed under several of them. Why: text assembled in the browser does not
  exist for a fetcher that does not run scripts. How: enable the framework's
  server rendering or static generation for these routes, or put a prerendering
  step in front of them that serves the rendered HTML to every client alike;
  then confirm with a plain fetch that the headings and body text are present.
  Mechanism improved: extraction of the page's text from the fetched response.
- **Success criteria:** a plain fetch with no JavaScript of every URL cited
  returns a `delta_ratio` below 0.8, with the page's main headings and body text
  present in the server response.
- **Effort:** high

### RND-002 — The server response carries no text on any sampled page, and nothing was rendered

- **Mechanism:** when every sampled page returns a response with almost no
  extractable text, a fetcher that does not execute JavaScript reads nothing
  from the site at all. This is the same failure as RND-001 observed from the
  other side: without a rendered DOM to compare, the audit cannot show what a
  browser would add, but it can show directly that the server response is
  empty, and that alone is what a non-rendering fetcher receives.
- **Signal:** rendering produced no comparable page, the home page answered 2xx,
  and every 2xx HTML page in `pages[]` has fewer than 200 characters of server
  text, visible and hidden together (`raw.text_len + raw.hidden_text_len`).
- **Evidence read:** `pages[].url`, `pages[].status`, `pages[].content_type`,
  `pages[].page_type`, `pages[].raw.text_len`, `pages[].raw.hidden_text_len`,
  `pages[].raw.text_hash`, `pages[].rendered.available`,
  `run_context.capabilities.js_render`,
  `discovery.soft_404.detected`, `discovery.soft_404.baseline_text_hash`,
  `discovery.collapsed_duplicate_text`.
- **Threshold:** every 2xx HTML page under 200 characters. Justification: the
  smallest server-rendered page observed on any G2 site carried 531 characters
  (a near-empty blog index on a small storefront) and a navigation bar and
  footer alone exceed 200 on real sites, while a client-rendered shell carries
  0, or the length of a `noscript` notice. Requiring every page rather than a
  share is deliberate: this rule has no rendered comparison to lean on, so it
  fires only when the emptiness is total.
- **Minimum evidence:** a 2xx HTML page classified as `home`, and no page with
  `rendered.available == true`. When any page was rendered, RND-001 made the
  stronger comparison and this rule emits `not_assessed` saying so, so one root
  cause is never reported twice.
- **False-positive controls:** only 2xx HTML pages count, so a refused home page
  (a CDN block page is recorded empty on purpose) cannot fire it; non-HTML
  resources such as a markdown file are excluded; the soft-404 record is read so
  the finding can say whether every path returned one identical shell.
- **Legitimate exceptions:** a site that genuinely has no content yet;
  not distinguishable from a shell without rendering, and not excepted, since a
  fetcher still reads nothing. Confidence carries the uncertainty about what a
  browser would show.
- **Confidence:** high when `discovery.soft_404.detected` is true and every
  counted page's `raw.text_hash` equals `discovery.soft_404.baseline_text_hash`,
  meaning the site answers every path, real or not, with one identical empty
  shell; medium otherwise.
- **Impact inputs:** `blocking = true` (a non-rendering fetcher receives no
  text). `breadth = "site"` (every sampled page). `content_importance =
  "primary"` (the home page is among them).
- **Status:** found
- **Symptom tags:** invisible
- **Remediation:** what: serve the site's content in the server response rather
  than only through client-side scripts. Where: the application shell served at
  the URLs cited, which the evidence shows returning no text. Why: the server
  response is all a non-rendering fetcher ever reads. How: adopt server-side
  rendering or static generation for the site's routes, or place a prerendering
  step in front of them serving the same rendered HTML to every client; re-run
  the audit with a browser available to measure the gap per template. Mechanism
  improved: any text at all reaching a fetcher that does not execute scripts.
- **Success criteria:** a plain fetch of the home page and of each cited URL
  returns at least the page's main heading and body text in the server response.
- **Effort:** high

### RND-003 — Product prices appear only after rendering

- **Mechanism:** a price is the fact most often asked of a product page. When it
  is inserted by script after load, a fetcher reading the server response finds
  a product with no price, and an answer built from that response either omits
  the price or takes one from somewhere else. The page can look fully
  server-rendered while its single most important fact is not, so the
  whole-page ratio in RND-001 does not catch it.
- **Signal:** on comparable `product` pages that are not JavaScript-dependent, a
  price token occurs in the rendered text and none occurs in the server text,
  and the server response's JSON-LD carries no `offers.price` or
  `offers.lowPrice`.
- **Evidence read:** `pages[].url`, `pages[].status`, `pages[].content_type`,
  `pages[].page_type`, `pages[].page_type_confidence`, `pages[].raw.text_path`,
  `pages[].rendered.available`, `pages[].rendered.text_path`,
  `pages[].rendered.delta_ratio`, `pages[].raw.text_len`,
  `pages[].rendered.text_len`, `pages[].jsonld[].fields_present`.
- **Threshold:** the pattern holds on at least 60% of eligible product pages.
  Justification: product prices are rendered by one template, so a template
  defect shows on nearly all of them, while a minority usually means a few
  products with a hydrated sale badge or a price loaded for one variant; 60% is
  where the template itself is implicated. This is the worked example in
  `docs/RULE_FORMAT.md`, kept to its published numbers.
- **Minimum evidence:** at least 5 eligible product pages: comparable, `page_type
  == "product"`, `page_type_confidence >= 0.6`, and not JavaScript-dependent
  (those belong to RND-001). Fewer is `not_assessed`: a price rendering
  decision cannot be judged from a handful of products.
- **False-positive controls:** a price token is a currency symbol or code (₹,
  Rs, $, €, £, ¥, INR, USD, EUR, GBP, JPY) followed by a number, matched the same
  way in both texts; a page whose server text already holds any price token does
  not count, so a related-products carousel rendered on the server cannot hide a
  hydrated main price, and a price present in both texts never fires; a page
  whose server JSON-LD exposes `offers.price` or `offers.lowPrice` is excluded,
  because the fact is then machine-readable regardless of the visible text;
  pages already JavaScript-dependent are left to RND-001.
- **Legitimate exceptions:** quote-on-request or trade pricing, where no price
  is shown to anyone; detected because no price token occurs in the rendered
  text either, so those pages never match. Region-selected pricing that the
  server cannot know before the browser reports a location; not detectable from
  the bundle, which is why confidence is not high below 8 pages.
- **Confidence:** high when at least 8 eligible product pages were examined;
  medium at 5 to 7.
- **Impact inputs:** `blocking = true` for the price (it is not in the response).
  `breadth = "section"` (the product template). `content_importance =
  "primary"` (the product's principal fact).
- **Status:** found
- **Symptom tags:** invisible, misrepresented
- **Remediation:** what: include the price in the server response of the product
  template, as visible text or as `Offer` JSON-LD. Where: the product page
  template and its price component, on the URLs cited. Why: the server response
  is what a fetcher extracts, and it currently holds a product without a price.
  How: render the price component on the server, or emit `Product` with
  `offers.price` and `offers.priceCurrency` in JSON-LD generated server-side.
  Mechanism improved: the price becomes extractable and quotable.
- **Success criteria:** the price appears in the server response, as text or as
  `offers.price` JSON-LD, on every cited product URL, verifiable with a plain
  fetch and no JavaScript.
- **Effort:** medium
