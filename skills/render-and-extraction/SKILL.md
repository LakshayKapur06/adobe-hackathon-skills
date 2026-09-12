---
name: render-and-extraction
description: >-
  Diagnoses whether a page's substance is actually present as machine-readable
  text once the page is reached: pages whose text exists only after JavaScript
  runs, sites whose server response carries no text at all, and product prices
  that appear only after rendering. Use as part of a website
  AI-readiness audit when a fact a human plainly sees may be absent from what a
  fetcher receives. Reads a shared evidence bundle; never fetches anything.
license: Apache-2.0
allowed-tools: Read, Write
---

# Render and Extraction

**Mechanism owned:** once reached, is the substance present as machine-readable
text? This is the second gate. A fact that exists only after client-side
hydration cannot be extracted by a fetcher, so it cannot be quoted in an
assistant's answer even though a human sees it plainly.

## When to use

Use when auditing whether the fetched response actually contains the facts the
page appears to show: render gaps, non-textual content, interaction-gated
substance.

Do not use it to evaluate markup semantics — whether a fact is expressed as
valid `Product` or `Offer` JSON-LD is `identity-and-markup`. Do not use it to
judge whether the surrounding prose is quotable; that is `answerability`.

## Inputs

`evidence/evidence.json`, produced by `site-evidence-collector`. Nothing else,
and never the network.

Principally: `pages[].status`, `pages[].content_type`, `pages[].page_type`,
`pages[].page_type_confidence`, `pages[].raw.text_len`, `pages[].raw.text_path`,
`pages[].rendered.available`, `pages[].rendered.text_len`,
`pages[].rendered.text_path`, `pages[].rendered.delta_ratio`,
`pages[].jsonld[].fields_present`, `discovery.soft_404`,
`run_context.capabilities.js_render`. The extracted-text sidecars that
`raw.text_path` and `rendered.text_path` name are part of the bundle.

## Procedure

The steps below are implemented, one function per rule, in
`scripts/diagnose.py`:

    python scripts/diagnose.py --evidence evidence/evidence.json --out findings/render-and-extraction.json

It needs only a Python 3 standard library. A host that cannot run scripts
follows the same steps by hand against `references/rules.md`, which is the
specification the script implements.

1. Load `evidence/evidence.json` and confirm `schema_version` is compatible.
2. Establish whether rendering was available at all. If
   `run_context.capabilities.js_render` is false, every render-delta rule is
   `not_assessed` with its enabling hint — never "no render gap found". That
   distinction is the difference between an honest audit and a flattering one.
3. For each rule in `references/rules.md`, check minimum evidence, then apply
   false-positive controls and legitimate-exception checks before firing.
4. Emit findings with observed impact inputs, confidence, status, effort, scope
   denominators and `evidence_refs`. Never assign `severity`.
5. Emit `checks_passed` for rules that ran and did not fire.

## Output

`findings/render-and-extraction.json`: `findings`, `not_assessed` and
`checks_passed` arrays, each finding conforming to
`../../schemas/finding.schema.json` minus the orchestrator-derived fields.


The rule set, the ownership boundary, the evidence this skill is permitted to
read and the rule budget are all in `references/rules.md`.
