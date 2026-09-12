---
name: site-evidence-collector
description: >-
  The single observation layer for a website audit. Performs the robots.txt
  gate, a polite stratified first-party crawl, stdlib HTML extraction, optional
  JS rendering, deterministic claim-candidate extraction and a keyless off-site
  corroboration probe, then writes one shared evidence bundle that every
  diagnostic skill reads. Use when an audit needs observed facts about a site;
  never use it to draw conclusions. It detects nothing and judges nothing.
license: Apache-2.0
allowed-tools: Read, Write, Bash
---

# Site Evidence Collector

The only skill in this marketplace permitted to touch the network. Everything
else reads what this skill wrote.

## When to use

Use when an audit needs observed facts about a site. Invoked by
`audit-orchestrator`, once per run, before any diagnostic runs.

Do not use it to decide anything. If a statement requires a threshold, a
comparison against a norm, or the word "should", it belongs in a diagnostic
skill, not here. The separation exists so that two skills can never disagree
about the same page — the worst failure mode available to an auditor.

## Inputs

| Input | Required | Notes |
|---|---|---|
| `site` | yes | URL or bare domain. |
| `workdir` | yes | All output is written here and nowhere else. |
| `budgets` | no | Per-stage seconds. Defaults in `references/budgets.md`. |

## Procedure

1. **Resolve the origin.** Follow redirects from the input to a final origin,
   recording the chain. Derive the registrable domain. Record both, because a
   site reachable at two hosts is an observation a diagnostic will need.

2. **Gate on robots.txt, before anything else.** Fetch `/robots.txt`, parse
   every group, and record the directive that applies to each named AI crawler
   as `allowed`, `disallowed` or `unspecified`. `unspecified` is a distinct
   state from `allowed` and must never be collapsed into it. Honour the
   directives that apply to us and honour `crawl-delay`. If we are disallowed,
   record that and stop; do not fetch the page anyway to "check".

3. **Probe capabilities.** Determine whether a JS renderer is available and
   whether third-party egress is possible. Write the result into
   `run_context.capabilities`. Capability is a matrix, not a ladder: JS
   rendering and egress are independent, and the audit is designed to be useful
   with neither.

4. **Discover and sample.** Build a frontier from sitemaps, navigation and the
   link graph. Classify URLs into page types by URL pattern and on-page shape,
   then sample stratified across types rather than breadth-first, so that a
   50,000-page catalogue does not spend the whole budget on one template.
   Record `discovered`, `fetched`, `blocked_by_robots` and the strata, because
   every downstream finding must be able to state its denominator.

5. **Extract with the standard library only.** Parse with `html.parser`. Record
   raw text metrics, headings, in-page anchor targets, links, images, tables,
   iframes, forms, JSON-LD with the values it asserts, meta robots, canonical,
   hreflang, dates, obstructions and timings, exactly as the schema declares
   them. Write the extracted text itself to `evidence/pages/<sha256>.txt` and
   record the path, rather than inlining page text into the bundle. Third-party
   parsers may only ever be an optional performance path producing
   byte-identical output; a dependency must never change extraction semantics.

6. **Render only where it changes the answer.** If a renderer is available,
   render a bounded subset and record the raw-versus-rendered delta. If not,
   record the degradation with its impact so the orchestrator can mark the
   affected rules `not_assessed` rather than silently passing them.

7. **Probe user-agent-conditional serving, twice and no more.** Request the
   home page and one deep page under each named AI crawler's user agent and
   record the status and extracted-text length each one receives. This is the
   only observation that varies the request identity, so it is bounded hard at
   two URLs: repeating it across a sample would be indistinguishable from
   probing the site. Never probe a URL robots.txt disallows us from, under any
   user agent.

8. **Record the agent-facing discovery files, present or not.** Request
   `/llms.txt`, `/agents.md` and `/.well-known/ucp` at the resolved origin, once
   each, within 5s in total, skipping any path robots.txt disallows. Record the
   status, whether a non-empty 2xx body came back, and the content type — never
   the contents. Absence is an observation to record, not an error to report.

9. **Extract claim candidates, do not interpret them.** Emit candidate strings
   with kind, normalised value, source URL, locator and extraction method.
   Promotion of a candidate to a canonical claim is a judgement and belongs to
   `identity-and-markup`, which writes back before the second pass.

10. **Probe off-site, keylessly, with a disclosed coverage bound.** Using the
   canonical claims, query the keyless providers listed in
   `references/providers.md` and write `external.hits` in one schema regardless
   of which provider answered. Respect each third-party domain's own robots.txt.
   Record `frontier_size` and `truncated`. We do not have open-web recall and
   the evidence bundle must never imply that we do.

11. **Write the bundle.** `workdir/evidence/evidence.json`, conforming to
    `../../schemas/evidence.schema.json`, plus the text sidecars under
    `workdir/evidence/pages/`. Validate before returning.

## Output

`workdir/evidence/evidence.json`, plus the extracted-text sidecars it points
at under `workdir/evidence/pages/`. One schema, one writer.

Scope, non-goals and the two-pass ordering are in `references/scope.md`; stage
budgets and overrun behaviour in `references/budgets.md`; the corroboration
provider set and its coverage bound in `references/providers.md`.

## Guardrails

Read-only GET requests only. Never submit a form, never traverse a login, never
click, never retry aggressively. Respect robots.txt for the audited domain and
for every third-party domain fetched. Identify honestly in the User-Agent.
