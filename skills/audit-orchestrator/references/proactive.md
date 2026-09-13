# Proactive recommendations — the orchestrator's four

The orchestrator owns no detection rules. It does own step 8 of its procedure:
strengthening actions the evidence warrants even where nothing is wrong. They are
specified here in the same fourteen-field block the diagnostics use, so a reader
can hold them to the same standard, and implemented in `scripts/proactive.py`.

Both are `status: proactive`. Under `contracts-v3` that caps their severity at
`medium` and holds their priority at P2 or P3, so neither can ever outrank a
finding. Each fires only on evidence, and none repeats a finding: where a
diagnostic reports a defect, the proactive recommendation beside it stays
silent. PRO-002, PRO-003 and PRO-004 are specific to the site by construction.
PRO-001
is the one exception to the rule that a recommendation appearing in most reports
is padding, and it is kept deliberately: `docs/DECISIONS.md` requires the
`llms.txt` position to be stated, calibrated as speculative and low, rather than
left for a reader to assume the audit forgot it. It is always low severity, low
confidence and worded as optional, and it disappears where the file exists.

## Evidence this skill may read

The same guard the diagnostics carry: every field a block below names under
**Evidence read** must appear in this list, and every entry here must exist in
the evidence schema. The repository's build gate enforces both directions.

- `well_known[].path`
- `well_known[].status`
- `well_known[].present`
- `canonical_claims[].kind`
- `canonical_claims[].value_normalized`
- `canonical_claims[].first_party_confidence`
- `canonical_claims[].entity_ambiguity`
- `site.resolved_origin`
- `site.input`
- `run_context.started_at`
- `pages[].url`
- `pages[].status`
- `pages[].page_type`
- `pages[].page_type_confidence`
- `pages[].lang`
- `pages[].fetched_at`
- `pages[].provenance.layer`
- `pages[].provenance.method`
- `pages[].jsonld[].type`
- `pages[].jsonld[].fields_present`
- `pages[].dates.visible_dates`
- `pages[].dates.schema_date_published`
- `pages[].dates.schema_date_modified`

## Rule budget

Rules defined: 4 of a maximum 12.

**Observed content in a recommendation.** PRO-002 quotes claim values the site
wrote about itself into prompts a person is told to run. `CLAUDE.md` forbids
relaying observed content as a recommendation, so only short factual kinds are
used (a name, a year, an address), never a tagline or a product string, and each
value must be at most 80 characters of letters, digits, spaces and ordinary
punctuation. A value that fails is dropped; if the name fails, there is no panel.

### PRO-001 — Optional and speculative: publish /llms.txt

- **Mechanism:** `/llms.txt` is a proposed convention for a plain-text summary of a
  site aimed at language-model tools. No major assistant documents reading it,
  which is the position recorded in `docs/DECISIONS.md` under deliberate
  exclusions: its absence is never a defect. It is listed only as a cheap hedge
  for tools that adopt the convention, with that uncertainty stated in the text.
- **Signal:** the `/llms.txt` probe answered and the file is not present.
- **Evidence read:** `well_known[].path`, `well_known[].status`,
  `well_known[].present`, `site.resolved_origin`, `site.input`, `run_context.started_at`.
- **Threshold:** the single probe result. Justification: presence of one file is
  a yes-or-no observation with nothing to aggregate.
- **Minimum evidence:** a `well_known` entry for `/llms.txt` with a non-null
  status. A missing entry means robots.txt kept the path from being probed, and a
  null status means no answer; both are `not_assessed`, never "absent".
- **False-positive controls:** `present` already excludes a soft-404 shell served
  at the path; the file's contents are never read, as `CLAUDE.md` requires.
- **Legitimate exceptions:** a site that has decided not to publish one; that is
  a fine decision, which is why this is proactive, low severity and worded as
  optional.
- **Confidence:** low, because no consumer of the file is documented.
- **Impact inputs:** `blocking = false`; `breadth = "page"` (one file);
  `content_importance = "secondary"`.
- **Status:** proactive
- **Symptom tags:** invisible
- **Remediation:** what: publish a short plain-text `/llms.txt`. Where: the site
  root. Why: a possible discovery channel for tools that adopt the convention.
  How: one paragraph describing the organization, then links to the pages that
  answer the questions people ask about it, kept consistent with those pages.
  Mechanism improved: an undocumented, possible discovery channel.
- **Success criteria:** `/llms.txt` answers 200 with content that is not the site's
  soft-404 page.
- **Effort:** low

### PRO-002 — Monitor how assistants describe the organization with a fixed prompt panel

- **Mechanism:** this audit observes the site and deliberately never queries live
  assistants (`docs/DECISIONS.md`, deliberate exclusions: non-deterministic,
  key-dependent and unreproducible). So whether any fix in the report changes
  what assistants say cannot be seen from here. The only way to see it is to ask
  the same questions repeatedly and compare the answers with facts whose correct
  value is known, and the claims this audit promoted provide exactly those facts.
  One of them is a buying question, because the answer an assistant gives it is
  often a marketplace's search URL rather than the seller's own product page, and
  which one it names is visible only where answers are produced.
- **Signal:** a `legal_name` canonical claim with at least medium first-party
  confidence and a value that passes the safety filter above.
- **Evidence read:** `canonical_claims[].kind`, `canonical_claims[].value_normalized`,
  `canonical_claims[].first_party_confidence`, `canonical_claims[].entity_ambiguity`,
  `site.resolved_origin`, `site.input`, `run_context.started_at`.
- **Threshold:** one qualifying name. Justification: a panel needs an entity to
  ask about; further claims add questions but are not required.
- **Minimum evidence:** the qualifying name. Without one, `not_assessed`: a panel
  built on a low-confidence or unsafe name would ask about the wrong thing.
- **False-positive controls:** only claims of at least medium confidence; only
  name, founding year and product-name kinds, and at most two product questions;
  one question per kind, so a site promoting three names does not ask the same
  question three times; addresses are not asked about, because a promoted address
  can be any address the markup carried, such as a shop in a store locator, and
  the panel's expected answers must be facts about the organization itself; the value filter above; the name
  question expects the site's own domain rather than the name repeated, since
  an assistant names the right website only if it resolved the right entity;
  when the name was scored of medium or high ambiguity, every other question
  carries the domain
  so its answer is about this organization, and the recommendation says so.
- **Legitimate exceptions:** an organization already monitoring assistant
  answers; not detectable, and harmless, which is why this is proactive.
- **Confidence:** medium.
- **Impact inputs:** `blocking = false`; `breadth = "site"`;
  `content_importance = "secondary"`.
- **Status:** proactive
- **Symptom tags:** misrepresented
- **Remediation:** what: ask a fixed panel of questions of the assistants that
  matter, on a schedule, and record each answer against the expected value.
  Where: outside the site, in a sheet or scheduled script owned by whoever owns
  the brand's facts. Why: the effect of a fix is only visible where answers are
  produced. How: the report lists the exact prompts and expected values; record
  date, assistant, answer and match, and re-run after each fix. Mechanism
  improved: the audit's fixes become measurable.
- **Success criteria:** a dated record of answers per assistant exists, each marked
  as matching or not matching the site's stated value.
- **Effort:** low

### PRO-003 — Anchor the organization's identity to its profiles elsewhere

- **Mechanism:** when several things share a name, a machine resolves which one a
  page means from what distinguishes it, and the most direct statement a site can
  make is a `sameAs` link from its organization markup to the same entity
  described elsewhere: an encyclopedia entry, a registry record, official
  profiles. schema.org defines each such link as a URL that "unambiguously
  indicates the item's identity", and Google names `sameAs` among the properties
  it uses to disambiguate an organization. This site already describes itself as
  an organization, so the recommendation is to finish the statement it started,
  not to add markup it lacks.
- **Signal:** a 2xx `home` or `about` page carries a JSON-LD node of an
  organization type, and no JSON-LD node on any sampled page declares
  `sameAs`.
- **Evidence read:** `pages[].url`, `pages[].status`, `pages[].page_type`,
  `pages[].jsonld[].type`, `pages[].jsonld[].fields_present`,
  `canonical_claims[].kind`, `canonical_claims[].entity_ambiguity`,
  `pages[].fetched_at`, `pages[].provenance.layer`, `pages[].provenance.method`.
- **Threshold:** one qualifying organization node. Justification: whether an
  entity declares identity links is a property of its markup, not of a sample;
  one node is the whole statement.
- **Minimum evidence:** a 2xx `home` or `about` page with an organization node.
  With none, `not_assessed`: a site with no organization markup is IDM-001's
  finding, not this recommendation.
- **False-positive controls:** any JSON-LD node declaring `sameAs`, even with
  empty values, silences this recommendation: a declared but empty `sameAs` is
  IDM-002's defect and is reported there, and a site that anchors its identity
  on another node, such as its WebSite, has already made the statement asked
  for; the organization types are the same list identity-and-markup uses; only
  home and about pages are considered, where Google recommends the markup sit.
- **Legitimate exceptions:** an organization with no profile anywhere to point
  to; not detectable, harmless as a recommendation, and why this is proactive.
- **Confidence:** medium, raised to high when the organization's name was scored
  as ambiguous, because a name that collides with other entities is exactly the
  case identity links resolve.
- **Impact inputs:** `blocking = false`; `breadth = "site"`;
  `content_importance = "secondary"`.
- **Status:** proactive
- **Symptom tags:** misrepresented
- **Remediation:** what: add a `sameAs` array to the organization markup listing
  the absolute URLs of its entries elsewhere. Where: the organization JSON-LD on
  the page cited. Why: identity links let a machine tie this site to the same
  entity in the sources it already trusts. How: list the organization's Wikidata
  item and Wikipedia article if they exist, then its official profiles (LinkedIn,
  Crunchbase, the main social accounts), only ones the organization controls or
  that describe it, never a directory of unrelated listings. Mechanism improved:
  entity disambiguation.
- **Success criteria:** the organization node in the server response carries a
  `sameAs` array of absolute URLs that each describe this organization.
- **Effort:** low

### PRO-004 — Give the dates articles show a machine-readable form

- **Mechanism:** a machine judging whether an article is current reads its date
  from several signals, and a visible date is the weakest of them: a page often
  shows several dates at once, of related stories, comments or the footer, and a
  date written as 03/04 means different days in different countries. Google
  documents that it combines signals and recommends pairing a visible date with
  `datePublished` or `dateModified` in Article-type structured data, which states
  unambiguously which date belongs to this article. These articles already show
  a date, so the recommendation completes a signal the site is already giving.
- **Signal:** 2xx pages classified `article` with `page_type_confidence` at least
  0.8, in English or with no declared `lang`, show a visible date and carry
  neither `datePublished` nor `dateModified`.
- **Evidence read:** `pages[].url`, `pages[].status`, `pages[].page_type`,
  `pages[].page_type_confidence`, `pages[].lang`, `pages[].dates.visible_dates`,
  `pages[].dates.schema_date_published`, `pages[].dates.schema_date_modified`,
  `pages[].fetched_at`, `pages[].provenance.layer`, `pages[].provenance.method`.
- **Threshold:** at least 2 such pages, making up at least 50% of the qualifying
  articles that show a visible date. Justification: date markup is emitted by a
  template, so a template that omits it does so on most of its articles, while a
  single page is more likely an older article from before the template changed.
- **Minimum evidence:** at least 2 qualifying articles showing a visible date.
  Fewer is `not_assessed`.
- **False-positive controls:** articles with no visible date at all are left to
  FRC-001, which reports that as a defect, so the two never describe one page;
  the 0.8 classifier floor keeps listing pages out.
- **Legitimate exceptions:** a visible date that belongs to something else on the
  page rather than the article; not separable from the evidence, which is why the
  recommendation asks for the article's own date rather than asserting which
  visible date that is.
- **Confidence:** medium.
- **Impact inputs:** `blocking = false`; `breadth = "section"` (the article
  template); `content_importance = "secondary"`.
- **Status:** proactive
- **Symptom tags:** misrepresented
- **Remediation:** what: emit the article's publication and update dates in its
  structured data. Where: the article template behind the URLs cited. Why: a
  structured date states which date is the article's and in an unambiguous
  format. How: add `datePublished` and `dateModified` in ISO 8601 to the
  `Article`, `NewsArticle` or `BlogPosting` JSON-LD, generated from the same
  fields that render the visible date. Mechanism improved: recency read rather
  than inferred.
- **Success criteria:** every cited article carries `datePublished` or
  `dateModified` in its server response JSON-LD, matching the date it shows.
- **Effort:** low
