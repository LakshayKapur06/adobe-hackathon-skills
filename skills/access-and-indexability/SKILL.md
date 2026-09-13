---
name: access-and-indexability
description: >-
  Diagnoses whether a machine can legally and technically reach a site's content
  at a stable address: AI-crawler policy in robots.txt, a robots.txt answering
  with errors, user-agent-conditional refusal, noindex and nosnippet directives
  in meta robots and X-Robots-Tag, canonicals collapsing pages into the home
  page, and advertised URLs returning errors. Use as part of a website AI-readiness
  audit when content that humans can see may be unreachable or unindexable by
  retrieval systems. Reads a shared evidence bundle; never fetches anything.
license: Apache-2.0
allowed-tools: Read, Write, Bash
---

# Access and Indexability

**Mechanism owned:** can a machine legally and technically reach the content at
a stable address? This is the first of the three gates in the retrieval chain —
be let in, be readable, be quotable. If this gate fails, nothing downstream can
succeed, which is why this skill runs first.

## When to use

Use when auditing why a site's content may be unreachable to AI crawlers and
retrieval systems: crawler policy, reachability, addressability.

Do not use it to judge whether the content is any good once reached. Text
quality is `answerability`; machine-readability of the response body is
`render-and-extraction`; entity identity is `identity-and-markup`.

## Inputs

`evidence/evidence.json`, produced by `site-evidence-collector`. This skill
reads nothing else and never touches the network.

Principally: `robots`, `pages[].status`, `pages[].headers.x_robots_tag`,
`pages[].meta_robots`, `pages[].canonical`, `pages[].canonical_self`,
`pages[].page_type`, `site.resolved_origin`, `site.registrable_domain`,
`ua_probe`.

## Procedure

The steps below are implemented, one function per rule, in
`scripts/diagnose.py`:

    python scripts/diagnose.py --evidence evidence/evidence.json --out findings/access-and-indexability.json

It needs only a Python 3 standard library. A host that cannot run scripts
follows the same steps by hand against `references/rules.md`, which is the
specification the script implements.

1. Load `evidence/evidence.json` and confirm `schema_version` is compatible.
2. For each rule in `references/rules.md`, check its **minimum evidence** clause
   first. If unmet, emit a `not_assessed` entry with the reason. Never convert
   an unmade observation into a clean bill of health.
3. Apply the rule's false-positive controls and legitimate-exception checks
   before firing. Under this rubric a false positive costs more than a miss.
4. For each rule that fires, emit a finding carrying its observed impact inputs
   (`blocking`, `breadth`, `content_importance`), `confidence`, `status`,
   `effort`, the scope denominator, and `evidence_refs` pointing at the exact
   observations. Do not assign `severity` — the orchestrator derives it.
5. For each rule that ran cleanly and did not fire, emit a `checks_passed`
   entry, so a clean site reads as verified rather than as unexamined.

## Output

`findings/access-and-indexability.json`: an object with `findings`,
`not_assessed` and `checks_passed` arrays. Every finding conforms to
`../../schemas/finding.schema.json` minus the derived `severity` and
`suggested_action.priority`, which the orchestrator fills in.


The rule set, the ownership boundary, the evidence this skill is permitted to
read and the rule budget are all in `references/rules.md`.
