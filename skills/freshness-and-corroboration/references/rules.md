# Freshness and Corroboration — rule set

Every rule below is written in the canonical block defined in
`docs/RULE_FORMAT.md`. One engineering vocabulary across all six diagnostics,
not six voices. CI validates that each block has all fourteen fields present and
non-empty, that every field path named under **Evidence read** exists in
`schemas/evidence.schema.json`, and that the rule count declared below matches
the number of blocks in this file.

## Mechanism owned

Are the current facts datable, internally consistent and independently
supported? Machines treat a fact as more trustworthy when many independent
places say the same thing, and a claim contradicted between a brand's own pages
gives a retrieval system a reason to prefer somebody else's version. The rules
here cover articles that state no machine-readable date, and a founding year
that disagrees with the site's Wikidata record. External breadth, agreement
rate and an unsupported-claim inventory were considered and cut; the section
below records why, from what the off-site evidence actually contains.

## Not owned by this skill

On-site structure and markup validity (`identity-and-markup`,
`answerability`). Deciding what the brand claims: this skill consumes the
canonical claims that `identity-and-markup` promoted.

## Evidence this skill may read

This skill reads `evidence/evidence.json` and nothing else. It never touches the
network. Every field path a rule consumes must appear in this list, and every
path in this list must exist in the evidence schema — CI enforces both
directions, which is what makes fabricated evidence impossible.

- `pages[].status`
- `pages[].page_type`
- `pages[].page_type_confidence`
- `pages[].lang`
- `canonical_claims[].id`
- `external.hits[].retrieved_at`
- `canonical_claims`
- `pages[].jsonld[].values`
- `canonical_claims[].value_normalized`
- `canonical_claims[].kind`
- `canonical_claims[].first_party_confidence`
- `canonical_claims[].entity_ambiguity`
- `claim_candidates`
- `external.attempted`
- `external.method`
- `external.frontier_size`
- `external.truncated`
- `external.origins`
- `external.origins[].registrable_domain`
- `external.origins[].source_type`
- `external.origins[].syndication_cluster`
- `external.origins[].brand_owned`
- `external.hits`
- `external.hits[].claim_id`
- `external.hits[].asserted_value`
- `external.hits[].matches_current`
- `external.hits[].origin`
- `pages[].dates`
- `pages[].dates.visible_dates`
- `pages[].dates.schema_date_modified`
- `pages[].dates.schema_date_published`
- `pages[].dates.http_last_modified`
- `pages[].headers.last_modified`
- `sitemaps[].lastmod_present_ratio`
- `run_context.capabilities.egress`
- `run_context.corroboration`
- `schema_version`
- `pages[].fetched_at`
- `pages[].provenance.layer`
- `pages[].provenance.method`
- `pages[].url`
- `sitemaps[].url`
- `external.hits[].url`
- `external.origins[].urls`

## Rule budget

Rules defined: 2 of a maximum 12.

The cap is deliberate. A thirteenth rule means something must be cut or merged.
Rule-count inflation reads as padding under this rubric, and a false positive
costs more than a miss.

## What the off-site evidence can and cannot support

Corroboration was designed as external breadth, agreement rate and a
contradiction inventory. Reading how `external.hits` is produced, and what real
runs contain, cut most of that, and the reasons matter more than the count:

- `matches_current: false` does not mean a source disagrees. A Wayback hit for a
  founding year records "first archived snapshot 1997", which never contains a
  founding word, so it is `false` for every founding claim while bounding the
  claim from one side only. A Wikidata label ("The Indian Express") is a common
  name and legitimately differs from a legal name ("Indian Express Limited").
  A declared `sameAs` profile on a social network is routinely refused to
  automated clients, which records `false` without anyone asserting anything.
- Breadth and agreement rate would be computed over an enumerable frontier that
  was one Wayback snapshot on the only real run that reached pass 2. Absence of
  a hit within a frontier that small says nothing about the open web, and a
  finding worded on it would imply recall we do not have.
- Unsupported claims: the same problem. A claim with no hit is unchecked, not
  unsupported.

What survives is one comparison that is like-for-like by construction: the
founding year the site states, against the inception date in Wikidata's
structured record, reached only after Wikidata's official-website property has
matched the audited domain. On the freshness side, one rule on whether articles
state a date at all.

**How a finding cites its evidence.** FRC-001 is page-level and cites
`pages[].url`, `pages[].provenance.layer`, `pages[].provenance.method` and
`pages[].fetched_at`. FRC-002 cites the external record as a `third_party`
observation at `external.hits[].url`, retrieved at `external.hits[].retrieved_at`.
Both are implemented in `scripts/diagnose.py`.

## Rules

### FRC-001 — Articles state no date a machine can read

- **Mechanism:** whether a fact is current is decided from when it was written.
  An assistant weighing two articles, or deciding whether a statement is still
  true, can only prefer the recent one if it can tell which that is. Google
  documents that it estimates a page's date from several signals and recommends
  both a visible, labelled date and `datePublished` or `dateModified` in
  Article-type structured data. An article with neither leaves its age to be
  guessed from indirect signals.
- **Signal:** 2xx pages classified `article` with `page_type_confidence` of at
  least 0.8 whose `dates.schema_date_published`, `dates.schema_date_modified`
  are both null and whose `dates.visible_dates` is empty, among those whose
  `lang` is English or undeclared.
- **Evidence read:** `pages[].url`, `pages[].status`, `pages[].page_type`,
  `pages[].page_type_confidence`, `pages[].lang`, `pages[].dates.visible_dates`,
  `pages[].dates.schema_date_modified`, `pages[].dates.schema_date_published`.
- **Threshold:** at least 2 such pages, making up at least 50% of the qualifying
  article pages. Justification: publishing systems apply date output per
  template, so a template that omits dates does so on nearly every article,
  while a single undated page is typically an evergreen page the classifier
  placed among articles; the share and the floor separate those.
- **Minimum evidence:** at least 2 qualifying article pages (2xx, `article`,
  confidence at least 0.8, `lang` English or undeclared). Fewer is
  `not_assessed`, and the reason counts the articles set aside for language.
- **False-positive controls:** only 2xx pages; only pages whose `lang` is
  English or undeclared, because the collector reads ISO, numeric and
  English-language dates and `<time datetime>` values, so "13 सितंबर 2026" or
  "13 septembre 2026" would read as no date at all; the 0.8 classifier floor keeps
  listing pages out, since on the G2 sites blog indexes classified as `article`
  scored 0.6 while real articles scored 0.9; any visible date counts as a date,
  including a sidebar date, so boilerplate can only stop the rule, never fire it;
  the HTTP `Last-Modified` header is deliberately not accepted as a date, because
  on a client-rendered site every URL returned the same header for the shared
  shell, and it describes the file rather than the article.
- **Legitimate exceptions:** evergreen reference writing that is intentionally
  undated; not detectable, which is why confidence is medium and the rule never
  fires on fewer than 2 pages.
- **Confidence:** medium. The absence of dates is literal, but the classifier
  can still place an undated evergreen page among articles.
- **Impact inputs:** `blocking = false` (the article is readable). `breadth =
  "section"` (the article template). `content_importance = "secondary"` (the
  date qualifies the content rather than being it).
- **Status:** found
- **Symptom tags:** misrepresented
- **Remediation:** what: show a labelled publication or update date on the
  article template and emit it as `datePublished` and `dateModified`. Where: the
  article template behind the URLs cited. Why: a machine can only judge
  recency from a date it can read. How: render "Published" and "Updated" dates
  near the headline, and emit an `Article` or `BlogPosting` JSON-LD node carrying
  `datePublished` and `dateModified` in ISO 8601, generated from the same
  fields. Mechanism improved: recency can be read rather than guessed.
- **Success criteria:** every cited URL shows a visible date and carries
  `datePublished` or `dateModified` in its server response JSON-LD.
- **Effort:** low

### FRC-002 — The site's founding year disagrees with its Wikidata record

- **Mechanism:** a founding year is exactly the kind of fact an assistant states
  without searching, and the source it is most likely to draw it from is a
  structured public record. When the site says one year and Wikidata's
  inception statement says another, one of the two is repeated as fact
  somewhere, and the site cannot know which. The comparison is between two
  structured values for the same property of the same entity, so unlike prose
  matching it cannot mistake a citation date for a claim.
- **Signal:** a canonical `founded_year` claim has an external hit from
  `wikidata.org` with `matches_current` false.
- **Evidence read:** `run_context.capabilities.egress`, `external.attempted`,
  `external.method`, `external.frontier_size`, `canonical_claims[].id`,
  `canonical_claims[].kind`, `canonical_claims[].value_normalized`,
  `canonical_claims[].first_party_confidence`,
  `canonical_claims[].entity_ambiguity`, `external.hits[].claim_id`,
  `external.hits[].origin`, `external.hits[].asserted_value`,
  `external.hits[].matches_current`, `external.hits[].url`,
  `external.hits[].retrieved_at`.
- **Threshold:** one disagreement. Justification: the comparison is one structured
  value against another, with nothing to sample; the uncertainty about which
  value is right, and whether both describe the same event, is carried by
  status and confidence.
- **Minimum evidence:** egress available, `external.attempted` true, and a
  `founded_year` canonical claim with `first_party_confidence` of medium or high
  and `entity_ambiguity` not high that has a `wikidata.org` hit. Wikidata is only
  queried once its official-website property matches the audited domain, so a
  hit implies identity was settled by the record. Without all of this the rule
  is `not_assessed`: an unchecked claim is not a supported one.
- **False-positive controls:** only `wikidata.org` hits count, so a Wayback
  first-snapshot year, a Wikipedia article that merely lacks the year, and a
  refused social profile can never read as a contradiction; low-confidence
  claims and ambiguous names are excluded, per D8, because a match on an
  ambiguous identity means little; identity is settled by Wikidata's
  official-website statement before any value is compared.
- **Legitimate exceptions:** the two years can describe different events, such
  as a publication first issued one year and its company incorporated the year
  before, which is a real case this module has met. The evidence cannot tell
  those apart, so the rule is `risk`, never `found`, and the remediation starts
  by establishing which event each source means.
- **Confidence:** medium when the claim's `first_party_confidence` is high;
  low otherwise.
- **Impact inputs:** `blocking = false`. `breadth = "site"` (a fact about the
  organization, not a page). `content_importance = "secondary"`.
- **Status:** risk
- **Symptom tags:** misrepresented
- **Remediation:** what: establish which year is correct for which event, then
  make the site and the public record say the same thing, or say explicitly what
  each year refers to. Where: the site's about page and organization markup, and
  the Wikidata item cited. Why: a structured public record is where a founding
  year is most likely to be taken from, and a disagreement means one version is
  being repeated somewhere. How: if the site is wrong, correct its pages and
  `foundingDate`; if Wikidata is wrong, propose a correction on the item with a
  reference to a primary source, following Wikidata's own editing process; if
  both are right about different events, label the site's year, for example
  "first published in". Mechanism improved: one consistent founding fact across
  the sources machines read.
- **Success criteria:** the founding year on the site and the inception year on
  the cited Wikidata item agree, or the site labels which event its year refers
  to.
- **Effort:** low
