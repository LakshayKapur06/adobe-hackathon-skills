# Answerability — rule set

Every rule below is written in the canonical block defined in
`docs/RULE_FORMAT.md`. One engineering vocabulary across all six diagnostics,
not six voices. CI validates that each block has all fourteen fields present and
non-empty, that every field path named under **Evidence read** exists in
`schemas/evidence.schema.json`, and that the rule count declared below matches
the number of blocks in this file.

## Mechanism owned

Is the content shaped so a retrieval system can locate and quote an answer?
Assistants build answers from passages they can isolate; substance diluted
across boilerplate or buried in one undifferentiated block gives a retriever
nothing to lift. The one rule here recommends section structure for long
articles and documentation. Boilerplate dominance, passage length, heading
counts and query-intent coverage were measured and cut; the section below says
why, because the reasons define what this evidence can honestly support.

## Not owned by this skill

Crawler admission (`access-and-indexability`). Whether the text is present in
the response at all (`render-and-extraction`). Whether a fact is current or
corroborated (`freshness-and-corroboration`).

## Evidence this skill may read

This skill reads `evidence/evidence.json` and nothing else. It never touches the
network. Every field path a rule consumes must appear in this list, and every
path in this list must exist in the evidence schema — CI enforces both
directions, which is what makes fabricated evidence impossible.

- `pages[].status`
- `pages[].url`
- `pages[].text.word_count`
- `pages[].text.boilerplate_ratio`
- `pages[].text.longest_block_words`
- `pages[].text.heading_density_per_1k`
- `pages[].text.visible_excerpt`
- `pages[].raw.headings`
- `pages[].raw.text_path`
- `pages[].raw.anchors`
- `pages[].raw.headings[].level`
- `pages[].raw.headings[].text`
- `pages[].page_type`
- `pages[].page_type_confidence`
- `pages[].jsonld[].fields_present`
- `pages[].jsonld[].type`
- `crawl.sampling`
- `crawl.sampling.strata`
- `schema_version`
- `pages[].fetched_at`
- `pages[].provenance.layer`
- `pages[].provenance.method`

## Rule budget

Rules defined: 1 of a maximum 12.

The cap is deliberate. A thirteenth rule means something must be cut or merged.
Rule-count inflation reads as padding under this rubric, and a false positive
costs more than a miss.

## What the text evidence can and cannot support

Most of this skill's planned rules were cut after measuring the collector's text
metrics on the G2 sites, and the reasons are the most useful thing a reader of
this file can take from it:

- `text.boilerplate_ratio` counts only text inside `nav`, `aside`, landmark
  roles and page-level `header`/`footer`. Across healthy sites it ranged from
  0.0 to 0.93: an open-source foundation's category listings sit at 0.8 to 0.93 and full
  700-word news articles at 0.69. A threshold on it would describe template
  markup habits, not whether a passage can be quoted.
- `text.longest_block_words` measures the longest line of extracted text, and
  the extractor treats `<br>` as a space. A policy page whose paragraphs are
  separated by line breaks read as one 3,036-word block. A "wall of text" rule
  on it would misread formatting as structure.
- Several `h1` elements on one page are valid HTML and common (13 on one
  page of the same site), so a heading-count rule would test conformity, not defect.
- Query-intent coverage is the softest check in the design (W1) and the first
  rule in `docs/PLAN.md`'s cut list. The evidence gate it needs, a structured
  attribute with no page answering by it, has no observable counterpart in the
  bundle.

What survives is one recommendation whose inputs are robust to all of the above:
a page's word count and its heading count, on long-form page types only.

**How a finding cites its evidence.** The rule is page-level: each
`evidence_ref` cites `pages[].url`, `pages[].provenance.layer`,
`pages[].provenance.method` and `pages[].fetched_at`. It is implemented in
`scripts/diagnose.py`.

## Rules

### ANS-001 — Long articles and documentation carry almost no section headings

- **Mechanism:** an assistant quotes a passage, not a page. Section headings
  are the page's own statement of what each passage is about, and a system that
  splits a page along its structure uses them as the boundaries and the labels
  of the pieces it retrieves. A long page with no headings can only be divided
  at arbitrary lengths, so a retrieved piece may begin mid-argument and carry
  nothing that says what it answers. This is a strengthening recommendation,
  not a defect: an unheaded page is still readable, and no operator documents a
  penalty for it.
- **Signal:** 2xx pages of type `article` or `doc` with at least 1,500 words of
  text and fewer than 3 headings of any level.
- **Evidence read:** `pages[].url`, `pages[].status`, `pages[].page_type`,
  `pages[].text.word_count`, `pages[].raw.headings`, `pages[].jsonld[].type`.
- **Threshold:** at least 2 such pages, making up at least 50% of the sampled
  2xx pages of that type with at least 1,500 words. Justification: 1,500 words
  is several screens of reading, long enough that no single passage stands for
  the page; below 3 headings, counting the page title heading, most of that
  length sits under at most one section label. The 50% share and the 2-page
  floor make this a statement about how the template or authoring practice
  treats long pages, not about one long page.
- **Minimum evidence:** at least 2 eligible long pages (2xx, `article` or `doc`,
  at least 1,500 words, not news; see controls). Fewer is `not_assessed`: a site
  with no long-form pages has nothing this recommendation applies to.
- **False-positive controls:** only 2xx pages; only `article` and `doc` types, the
  long-form types where sectioning is expected, so a product page or a listing
  never counts; pages whose JSON-LD type is `NewsArticle`,
  `ReportageNewsArticle` or `LiveBlogPosting` are excluded, because news stories
  are conventionally written without subheadings and a recommendation to change
  a newsroom's house style would be noise; the heading count includes every
  heading on the page, including sidebar and footer headings, so boilerplate
  can only make the rule fire less, never more.
- **Legitimate exceptions:** news reporting, excluded as above. Narrative essays
  or fiction written deliberately as continuous prose; not detectable from the
  bundle, which is why the rule is `proactive` and never a defect.
- **Confidence:** medium. Word and heading counts are literal, but whether a
  given long page reads better sectioned is a judgement the evidence cannot make.
- **Impact inputs:** `blocking = false` (the text is present and readable).
  `breadth = "section"` (one long-form page type). `content_importance =
  "secondary"` (structure around the content, not the content).
- **Status:** proactive
- **Symptom tags:** invisible
- **Remediation:** what: divide the long pages of this type into sections, each
  under a heading that names what the section answers. Where: the article or
  documentation template and the authoring guidelines behind the URLs cited.
  Why: each heading becomes the label and the boundary of a retrievable
  passage. How: add `h2` headings every few hundred words at real topic
  changes, phrased as the question or claim the section addresses rather than
  as a generic label such as "Overview", and give each an `id` so it can be
  linked to directly. Mechanism improved: passages that can be isolated and
  identified.
- **Success criteria:** on each cited URL, the page's headings divide its text so
  that no section exceeds roughly 500 words, verifiable from the heading count
  against the word count.
- **Effort:** medium
