# Identity and Markup — rule set

Every rule below is written in the canonical block defined in
`docs/RULE_FORMAT.md`. One engineering vocabulary across all six diagnostics,
not six voices. CI validates that each block has all fourteen fields present and
non-empty, that every field path named under **Evidence read** exists in
`schemas/evidence.schema.json`, and that the rule count declared below matches
the number of blocks in this file.

## Mechanism owned

Is the brand a well-formed, unambiguous, credible entity to a machine? When
several things share a name, a retrieval system mixes them up unless something
distinguishes one from the others. The rules here cover a home page with no
machine-readable organization identity, `sameAs` identity links that identify
nothing, JSON-LD that no parser can read, and a structured price that
contradicts the prices a page shows. Name-collision scoring, markup
completeness beyond identity, and trust affordances were considered and cut;
the reasons are in `tests/rule-review.md`. This skill also owns the promotion of
claim candidates to canonical claims, in `scripts/promote.py`.

## Not owned by this skill

Whether the outside world agrees with the brand's claims
(`freshness-and-corroboration`). Whether the text is present at all
(`render-and-extraction`). Whether prose is quotable (`answerability`).

## Evidence this skill may read

This skill reads `evidence/evidence.json` and nothing else. It never touches the
network. Every field path a rule consumes must appear in this list, and every
path in this list must exist in the evidence schema — CI enforces both
directions, which is what makes fabricated evidence impossible.

- `pages[].url`
- `pages[].status`
- `pages[].jsonld`
- `pages[].jsonld[].type`
- `pages[].jsonld[].valid`
- `pages[].jsonld[].errors`
- `pages[].jsonld[].fields_present`
- `pages[].jsonld[].values`
- `pages[].jsonld[].contradicts_visible_text`
- `pages[].microdata_or_rdfa`
- `pages[].raw.headings`
- `pages[].raw.links`
- `pages[].text.visible_excerpt`
- `pages[].page_type`
- `claim_candidates`
- `claim_candidates[].kind`
- `claim_candidates[].value_normalized`
- `claim_candidates[].observed_count`
- `claim_candidates[].extraction_method`
- `canonical_claims`
- `canonical_claims[].entity_ambiguity`
- `canonical_claims[].first_party_confidence`
- `site.resolved_origin`
- `site.registrable_domain`
- `site.detected_locales`
- `schema_version`
- `pages[].fetched_at`
- `pages[].provenance.layer`
- `pages[].provenance.method`

## Rule budget

Rules defined: 4 of a maximum 12.

The cap is deliberate. A thirteenth rule means something must be cut or merged.
Rule-count inflation reads as padding under this rubric, and a false positive
costs more than a miss.

## Definitions shared by the rules below

**A 2xx page.** An entry in `pages[]` whose `status` is 200-299. A refused page
is recorded with an empty body and no JSON-LD, so without this gate a CDN block
page would read as a page with no markup.

**An organization node.** A JSON-LD node whose `type` is `Organization` or one
of its schema.org subtypes (the list is in `scripts/diagnose.py`, and includes
`Corporation`, `NewsMediaOrganization`, `OnlineStore`, `LocalBusiness` and its
common subtypes such as `Store` and `Restaurant`), or any node carrying a nested
organization, such as a `WebSite` whose `publisher.@type` is `Organization`.
Any node that carries a `logo` or `sameAs` also counts as the site describing
itself, so that a subtype missing from the list cannot make a site read as
having no identity markup.

**Usable sameAs entry.** A value under a node's `sameAs` that is an absolute
`http` or `https` URL. schema.org defines `sameAs` as the "URL of a reference
Web page that unambiguously indicates the item's identity", so an empty string
or a bare handle identifies nothing.

**What the markup evidence covers.** `pages[].jsonld` is parsed from the server
response. Identity markup injected only by client-side script is not in it, so
on a site where `render-and-extraction` reports the server response empty, a
missing-markup finding here is conditional on that fix, which the orchestrator's
arbitration states. Microdata and RDFa are detected (`microdata_or_rdfa`) but
not parsed, so a rule that would conclude markup is absent treats their presence
as "cannot see" and emits `not_assessed`.

**How a finding cites its evidence.** Every rule here is page-level: each
`evidence_ref` cites `pages[].url`, `pages[].provenance.layer`,
`pages[].provenance.method` and `pages[].fetched_at`. The rules are implemented
in `scripts/diagnose.py`, one function per rule, in the order written here.

## Rules

### IDM-001 — The home page carries no machine-readable organization identity

- **Mechanism:** a name on a page is a string, and several organizations can
  share it. Organization structured data states, in a form a machine does not
  have to guess at, which organization this site belongs to: its name, URL,
  logo and profiles elsewhere. Google documents that it uses this markup to
  "disambiguate your organization in search results" and recommends placing it
  on the home page. Without it, every system consuming the site must infer the
  entity from prose, and an ambiguous name is resolved by resemblance.
- **Signal:** the 2xx home page's JSON-LD contains no organization node.
- **Evidence read:** `pages[].url`, `pages[].status`, `pages[].page_type`,
  `pages[].jsonld[].type`, `pages[].jsonld[].fields_present`,
  `pages[].jsonld[].values`, `pages[].microdata_or_rdfa`,
  `site.resolved_origin`, `site.registrable_domain`.
- **Threshold:** the home page alone. Justification: Google names the home page
  (or a single about page) as the place for this markup, so the question is
  asked of that one page rather than averaged over a sample; an about page
  carrying the markup satisfies it too, as the exception below records.
- **Minimum evidence:** a 2xx page classified `home`. With none, `not_assessed`.
  When the home page carries microdata or RDFa, `not_assessed` as well, because
  the identity may be expressed there and the collector does not parse it. When
  the audited host is a subdomain of its registrable domain other than `www`,
  `not_assessed`: the organization's home page is on the main domain, which the
  audit did not fetch.
- **False-positive controls:** only 2xx pages; organization subtypes and nested
  publisher organizations count; any node carrying `logo` or `sameAs` counts;
  microdata or RDFa on the home page stops the rule rather than firing it; a
  2xx `about` page carrying an organization node satisfies the rule.
- **Legitimate exceptions:** identity stated on an about page instead of the
  home page, which Google accepts; detected by an organization node on any 2xx
  `about` page. A subdomain (`docs.`, `help.`, `blog.`) of an organization
  whose identity is stated on its main domain's home page; detected by the
  audited host differing from the registrable domain and its `www` form, and
  reported as not assessed with the main domain to check (found in adjudication
  on a documentation subdomain whose parent domain carries complete
  Organization markup). A personal site whose subject is a person rather than an
  organization; detected by a `Person` node on the home page.
- **Confidence:** high. The observation is the parsed markup itself.
- **Impact inputs:** `blocking = false` (the site is still reachable and
  readable). `breadth = "site"` (identity describes the whole site).
  `content_importance = "secondary"` (identity metadata, not the site's
  content).
- **Status:** found
- **Symptom tags:** misrepresented
- **Remediation:** what: add an `Organization` JSON-LD block, or the most
  specific subtype that applies, to the home page. Where: the home page
  template's `<head>`, in the server response. Why: it states the entity behind
  the site explicitly instead of leaving it to be inferred from a name. How:
  emit `@type`, `name`, `url`, `logo` and `sameAs` with the organization's
  profile URLs on other sites, plus `legalName` and `address` where they apply,
  generated server-side. Mechanism improved: entity disambiguation.
- **Success criteria:** the home page's server response contains a JSON-LD node
  of an Organization type with at least `name` and `url`.
- **Effort:** low

### IDM-002 — Organization markup declares sameAs links that identify nothing

- **Mechanism:** `sameAs` is how markup ties this site's entity to the same
  entity described elsewhere: its profiles, its encyclopedia entry, its
  registry record. schema.org defines each value as a URL that "unambiguously
  indicates the item's identity". When the property is present but every value
  is empty or not a URL, the site announces an identity link and supplies none,
  which is typically a theme emitting a field for social profiles that were
  never filled in.
- **Signal:** an organization node on a 2xx page has `sameAs` in
  `fields_present`, its `sameAs` value is recorded, and it contains no usable
  entry.
- **Evidence read:** `pages[].url`, `pages[].status`, `pages[].page_type`,
  `pages[].jsonld[].type`, `pages[].jsonld[].fields_present`,
  `pages[].jsonld[].values`.
- **Threshold:** one such node. Justification: a declared property with no
  usable value is a literal defect in the markup, not a statistical pattern, so
  one observation is sufficient; `breadth` records whether a shared template
  repeats it across the sample.
- **Minimum evidence:** at least one organization node on a 2xx page whose
  `sameAs` value is recorded in `values`. The collector caps `values` at 4KB per
  page and drops long values first, so a `sameAs` listed in `fields_present`
  but missing from `values` was truncated, not empty, and is never counted.
  With no assessable node, `not_assessed`.
- **False-positive controls:** a truncated `sameAs` is excluded rather than read
  as empty; any single `http` or `https` URL makes the node pass; only
  organization nodes count, so an unrelated node's `sameAs` cannot fire it.
- **Legitimate exceptions:** an organization with no profile anywhere else,
  which would be correct to omit `sameAs`; that site does not declare the
  property at all, so the rule, which requires the property to be declared, does
  not fire on it.
- **Confidence:** high.
- **Impact inputs:** `blocking = false`. `breadth = "site"` when the home page is
  among the affected pages or at least 50% of 2xx pages are, otherwise
  `"page"`. `content_importance = "secondary"`.
- **Status:** found
- **Symptom tags:** misrepresented
- **Remediation:** what: fill `sameAs` with the organization's real profile
  URLs, or remove the property until there are some. Where: the theme or
  template setting that populates the organization markup's `sameAs`, usually
  the social-links configuration. Why: an empty identity link is noise a
  consumer has to discard, and it signals configuration nobody checked. How:
  enter the absolute URLs of the organization's official profiles in the
  theme's social settings, or edit the template to omit empty entries. Mechanism
  improved: identity anchoring to external descriptions of the same entity.
- **Success criteria:** every organization node's `sameAs` in the server response
  contains only absolute http or https URLs, or the property is absent.
- **Effort:** low

### IDM-003 — JSON-LD blocks that no parser can read

- **Mechanism:** a JSON-LD block is only useful if it parses as JSON. A syntax
  error, such as a trailing comma, an unescaped quote or template text spliced
  into the object, makes a standard parser reject the whole block, so every
  statement in it is lost, not just the malformed one. The page looks marked up
  to anyone reading the source and says nothing to a machine.
- **Signal:** a 2xx page has a JSON-LD entry that failed to parse: `valid` is
  false, `type` is empty and `fields_present` is empty, the structural shape the
  collector gives exactly and only to a parse failure.
- **Evidence read:** `pages[].url`, `pages[].status`, `pages[].page_type`,
  `pages[].jsonld[].type`, `pages[].jsonld[].valid`,
  `pages[].jsonld[].fields_present`, `pages[].jsonld[].errors`.
- **Threshold:** one page. Justification: a parse failure is a literal defect in
  the response, with no sampling variance to average out; how widely a template
  repeats it is carried by `breadth`.
- **Minimum evidence:** at least one 2xx page with any JSON-LD entry. A site
  with no JSON-LD at all has nothing to parse, which is IDM-001's question, so
  this rule emits `not_assessed`.
- **False-positive controls:** only parse failures count, identified by the
  entry's structure rather than by reading its error text; a node that parsed
  but omits `@type` is not counted, because JSON-LD permits an untyped node
  that is typed where its `@id` is referenced elsewhere in the graph; HTML
  comment wrappers around the block are stripped by the collector before
  parsing.
- **Legitimate exceptions:** none leaves the markup usable: a block that does not
  parse is discarded by standard parsers whatever produced it. A lenient
  consumer that tolerates the error is not something the site can rely on.
- **Confidence:** high.
- **Impact inputs:** `blocking = false` (the page itself is unaffected).
  `breadth = "site"` when at least 50% of 2xx pages are affected, `"section"`
  when at least 2 pages are, otherwise `"page"`. `content_importance =
  "secondary"`.
- **Status:** found
- **Symptom tags:** misrepresented
- **Remediation:** what: fix the JSON syntax of the failing blocks. Where: the
  template or plugin emitting the `<script type="application/ld+json">` block on
  the URLs cited. Why: one syntax error discards every statement in the block.
  How: generate the block with a JSON serializer rather than string
  concatenation, so quoting and commas are always correct, and validate the
  output of each cited URL with a JSON parser. Mechanism improved: the markup
  the site already wrote becomes readable.
- **Success criteria:** every JSON-LD block on the cited URLs parses as JSON.
- **Effort:** low

### IDM-004 — Structured price contradicts the prices shown on the page

- **Mechanism:** a machine reading a product page takes the price from its
  `Offer` markup, because that is the unambiguous statement. When the page shows
  other prices and none of them is the marked-up one, the machine confidently
  reports a price no visitor sees. Google's structured data policy requires the
  markup to be "a true representation of the page content", and a misleading
  price is the case where the gap between the two reaches a buyer.
- **Signal:** a 2xx page has a JSON-LD commerce node (`Product`,
  `ProductGroup`, `IndividualProduct`, `Offer` or `AggregateOffer`) stating a
  price above zero, with `contradicts_visible_text` true. The collector sets
  that flag only when the markup states a price, the page's visible server text
  shows at least one currency amount, and none of those amounts equals the
  marked-up price.
- **Evidence read:** `pages[].url`, `pages[].status`, `pages[].page_type`,
  `pages[].jsonld[].type`, `pages[].jsonld[].values`,
  `pages[].jsonld[].contradicts_visible_text`.
- **Threshold:** one page. Justification: each contradiction is a direct
  observation of a wrong price on a specific product; `breadth` carries how many
  pages show it, and confidence carries whether one page could be a one-off.
- **Minimum evidence:** at least one 2xx page with a commerce node stating a
  price above zero (`offers.price` or `price` in its values). Otherwise
  `not_assessed`.
- **False-positive controls:** the collector's definition is deliberately
  narrow: a price missing from the visible text never counts (that is a render
  gap, owned by `render-and-extraction`), and a sale page showing both the old
  and the new price matches the marked-up one; only 2xx pages count; only
  commerce nodes count, and a price of zero never does. The last two were added
  when the first adjudication runs met a Hindi news site whose every page
  carries a `MobileApplication` node with `offers.price` of `0` for its free
  app, while market widgets on the same pages show rupee amounts: the markup
  was never a claim about anything the page sells.
- **Legitimate exceptions:** a site-wide promotion of a free app or service
  expressed as an `Offer` at price zero; excluded by the commerce-type and
  above-zero controls. A price converted into the visitor's currency on
  the server, so the markup states the base-currency amount and the page shows
  a converted one; not detectable from the evidence, which is why a single
  affected page is medium confidence. A variant selector whose default variant
  differs from the marked-up one; same treatment.
- **Confidence:** high when at least 2 pages are affected; medium for one.
- **Impact inputs:** `blocking = false` (the price is readable, just wrong).
  `breadth = "section"` when at least 2 pages are affected, otherwise `"page"`.
  `content_importance = "primary"` (the product's principal fact).
- **Status:** found
- **Symptom tags:** misrepresented
- **Remediation:** what: make the marked-up price equal the price the page
  shows. Where: the product template's `Offer` markup on the URLs cited, and the
  data source it reads the price from. Why: markup is taken as the authoritative
  statement, so a stale or base price there is repeated as fact. How: generate
  `offers.price` from the same variable that renders the visible price,
  including sale and selected-variant logic, rather than from a separate field.
  Mechanism improved: the structured statement of price matches what a buyer
  sees.
- **Success criteria:** on every cited URL, the `offers.price` value in the
  server response equals a price shown in the page's visible text.
- **Effort:** medium
