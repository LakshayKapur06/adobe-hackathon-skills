---
name: answerability
description: >-
  Diagnoses whether content is shaped so a retrieval system can locate and quote
  an answer: passage and chunk hostility, boilerplate dominance, heading
  architecture, whether a claim survives summarisation intact, and
  evidence-gated coverage of the query intents the site's own structured data
  implies. Use as part of a website AI-readiness audit when a site is reachable
  and readable but still never quoted. Reads a shared evidence bundle; never
  fetches anything and never judges crawlability or freshness.
license: Apache-2.0
allowed-tools: Read, Write
---

# Answerability

**Mechanism owned:** is the content shaped so a retrieval system can locate and
quote an answer? This is the third gate. Assistants build answers from passages
they can isolate and quote; a page whose substance is diluted across boilerplate
or buried in one undifferentiated block gives a retriever nothing to lift, even
when the fact is technically present.

## When to use

Use when a site passes the reachability and readability gates but is still not
cited: the content exists, in text, and is still not quotable.

Do not use it to judge whether the crawler was let in (`access-and-indexability`)
or whether the text is present at all (`render-and-extraction`). Do not use it
to judge whether a fact is current or corroborated; that is
`freshness-and-corroboration`.

## Inputs

`evidence/evidence.json`, produced by `site-evidence-collector`. Nothing else,
and never the network.

Principally: `pages[].text.word_count`, `pages[].text.boilerplate_ratio`,
`pages[].text.longest_block_words`, `pages[].text.heading_density_per_1k`,
`pages[].raw.headings`, `pages[].page_type`, `pages[].page_type_confidence`,
`pages[].jsonld[].fields_present`, `crawl.sampling`.

## Procedure

1. Load `evidence/evidence.json` and confirm `schema_version` is compatible.
2. Establish the page-type denominators from `crawl.sampling.strata`. Text-shape
   norms differ sharply by page type: a documentation page and a product page
   have legitimately different heading densities, and a rule that ignores this
   measures conformity rather than defect.
3. For each rule in `references/rules.md`, check minimum evidence, then apply
   false-positive controls and legitimate-exception checks before firing.
4. Query-intent rules are **evidence-gated**: flag a gap only when a structured
   attribute the site itself publishes has no page that answers by it. If the
   gap cannot be tied to an attribute we observed, emit nothing. Without this
   gate the check degrades into generic SEO advice.
5. Emit findings with observed impact inputs, confidence, status, effort, scope
   denominators and `evidence_refs`. Never assign `severity`.
6. Emit `checks_passed` for rules that ran and did not fire.

## Output

`findings/answerability.json`: `findings`, `not_assessed` and `checks_passed`
arrays, each finding conforming to `../../schemas/finding.schema.json` minus the
orchestrator-derived fields.


The rule set, the ownership boundary, the evidence this skill is permitted to
read and the rule budget are all in `references/rules.md`.
