---
name: answerability
description: >-
  Diagnoses whether content is shaped so a retrieval system can locate and quote
  an answer, recommending section structure for long articles and documentation
  that carry almost no headings. Use as part of a website AI-readiness audit when a site is reachable
  and readable but still never quoted. Reads a shared evidence bundle; never
  fetches anything and never judges crawlability or freshness.
license: Apache-2.0
allowed-tools: Read, Write, Bash
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

Principally: `pages[].status`, `pages[].page_type`, `pages[].text.word_count`,
`pages[].raw.headings`, `pages[].jsonld[].type`.

## Procedure

The steps below are implemented in `scripts/diagnose.py`:

    python scripts/diagnose.py --evidence evidence/evidence.json --out findings/answerability.json

It needs only a Python 3 standard library. A host that cannot run scripts
follows the same steps by hand against `references/rules.md`.

1. Load `evidence/evidence.json` and confirm `schema_version` is compatible.
2. Judge text shape per page type, never across types: a documentation page and
   a product page legitimately differ, and a rule that ignores this measures
   conformity rather than defect.
3. For each rule in `references/rules.md`, check minimum evidence, then apply
   false-positive controls and legitimate-exception checks before firing.
4. Do not add a rule on a text metric without first measuring its spread on real
   sites. `references/rules.md` records the metrics that failed that test.
5. Emit findings with observed impact inputs, confidence, status, effort, scope
   denominators and `evidence_refs`. Never assign `severity`.
6. Emit `checks_passed` for rules that ran and did not fire.

## Output

`findings/answerability.json`: `findings`, `not_assessed` and `checks_passed`
arrays, each finding conforming to `../../schemas/finding.schema.json` minus the
orchestrator-derived fields.


The rule set, the ownership boundary, the evidence this skill is permitted to
read and the rule budget are all in `references/rules.md`.
