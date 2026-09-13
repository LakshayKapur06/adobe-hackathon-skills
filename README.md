# agent-readiness-audit

An Agent Skill Marketplace that audits any website for the mechanisms that make a
brand **invisible** to AI assistants, **misrepresented** by them, or **bounced
from** once a visitor arrives, and emits one prioritised, evidence-backed report.

It is built on the three-gate account of how a machine uses a page: it has to be
**let in**, it has to be able to **read** what is there, and it has to be able to
**pick out and trust** the fact someone asked for. Each diagnostic owns one link
of that chain, plus the visitor who arrives at the end of it.

Recommend-only and read-only. No skill modifies the audited site, submits a
form, traverses a login, or sends anything but polite GET requests, and
robots.txt is obeyed for the audited domain and for every third-party domain
consulted.

## For judges: where to look, in order

1. **`docs/RUBRIC.md`** — each of the six rubric criteria mapped to the files
   that answer it, and every failure mode the handout names mapped to the rules
   that check it, or to the measurement that showed it cannot be checked
   without false positives.
2. **`samples/storefront-full/report.md`** — what a person receives: problems in
   the order to fix them, each with evidence, severity, priority and a fix they
   can verify.
3. **`skills/audit-orchestrator/SKILL.md`**, then any diagnostic's
   `references/rules.md` — the reasoning, one fixed 14-field block per rule.
4. **`tests/adjudication.md`** — the audit run on six real sites and checked by a
   person: what it got wrong, and how each error was fixed at its pattern.
5. **`docs/DECISIONS.md`** — why it is built this way, including the decisions
   revised when measurement proved them wrong.

## Running it

    python scripts/run_audit.py --url https://example.com --out runs/example/

**No configuration is required.** Python 3.8 or newer, standard library only.
The entrypoint's own procedure is `skills/audit-orchestrator/scripts/run.py`;
`scripts/run_audit.py` is a thin wrapper that also prints a one-line summary.

| Option | Effect |
|---|---|
| `--no-render` | never use a browser, even if one is installed |
| `--no-egress` | never contact a third-party host |
| `--max-pages N` | pages to sample (default 30) |
| `--summary` | also print a per-page table |

Two capabilities are optional and independent. A Chromium-family browser (found
on PATH, in standard install locations, or via `CHROME_PATH`) lets the audit
compare what a fetcher receives with what a browser builds. Network access to
public records lets it compare the site's claims with Wikipedia and Wikidata.
Without either, the whole on-site audit still runs, and every check that needed
the missing capability is listed as not assessed, with what would enable it,
never as a pass. Run one audit at a time: the renderer shares the CPU. Audits of
real sites finished in 14 to 178 seconds, inside the five-minute limit.

## What you get

Every run writes, into the `--out` directory:

- **`report.md`** — the audit for the person who fixes the site: the problems in
  the order to fix them, each with what was seen, why it matters, what to do,
  where, how, and how to tell it worked; improvements beyond the problems; the
  checks that passed; what could not be checked and how to make it checkable;
  and plain definitions of the technical terms the report uses.
- **`report.json`** — the same report as structured data, conforming to
  `schemas/report.schema.json`: `site`, `audited_at`, a counts-by-severity
  `summary`, and `findings[]` each with `id`, `title`, `severity`, `evidence` and
  `suggested_action`, plus `not_assessed`, `checks_passed` and `run_context`.
- **`evidence/`** — the observations every finding was drawn from, so any finding
  can be checked against what was actually fetched.

Sample outputs, produced from the fixture sites in this repository, are in
`samples/`.

## The skills

`marketplace.json` lists eight skills and marks `audit-orchestrator` as the only
entrypoint. One skill observes, six diagnose one mechanism each, and the
entrypoint composes their outputs into the report.

| Skill | Role | What it establishes |
|---|---|---|
| `audit-orchestrator` | **Entrypoint.** Composition, arbitration, output | Runs the others in order, validates every file that crosses a skill boundary, derives severity and priority, marks findings that depend on an upstream fix, adds proactive recommendations, writes the report |
| `site-evidence-collector` | **The only skill that touches the network.** Observation, no judgement | robots.txt, a polite stratified crawl, extraction, optional rendering, a user-agent probe, claim candidates, a keyless off-site probe; writes one evidence bundle |
| `access-and-indexability` | Gate 1: can a machine reach the content? | AI crawlers shut out by robots.txt or by a named opt-out; robots.txt answering with errors; user-agent refusals; `noindex` and snippet bans on templates; canonicals collapsing pages into the home page; advertised URLs that error; unreadable declared sitemaps |
| `render-and-extraction` | Gate 2: is the substance in the response? | Pages whose text exists only after JavaScript; a server response with no text at all; product prices present only after rendering |
| `identity-and-markup` | Gate 3a: is the brand an unambiguous entity? | No machine-readable organization identity; `sameAs` links that identify nothing; JSON-LD no parser can read; markup prices contradicting the page. Also promotes claim candidates for corroboration |
| `answerability` | Gate 3b: can an answer be lifted out? | Long articles and documentation with no section structure to retrieve passages by |
| `freshness-and-corroboration` | Gate 3c: are facts datable and consistent with the record? | Articles with no machine-readable date; a founding year that disagrees with Wikidata |
| `arrival-and-engagement` | The visitor who arrives | A server slow enough to lose a visitor before anything appears |

Every diagnostic's `references/rules.md` holds its rules in one fixed format:
mechanism, signal, the exact evidence fields read, a justified threshold,
minimum evidence, false-positive controls, legitimate exceptions, confidence,
impact inputs, status, remediation and success criteria. Where a planned check
was measured against real sites and cut, the file says so and why.

## How the entrypoint composes them

1. **Observe once.** The collector's first pass writes `evidence/evidence.json`,
   which is validated against `schemas/evidence.schema.json`; an invalid bundle
   is never diagnosed. Two skills can never disagree about a page, because only
   one of them ever looked at it.
2. **Promote, then corroborate.** `identity-and-markup` decides which candidate
   strings the site is really asserting about itself, and the collector's second
   pass asks public records about those. Identity comes first because an
   ambiguous brand name poisons every external match made from it.
3. **Diagnose in dependency order**: access, render, identity, answerability,
   freshness, arrival. Each diagnostic reads the bundle and writes one findings
   file. A diagnostic that fails costs only its own rules, which are reported as
   not assessed; the rest of the report stands.
4. **Arbitrate.** One root cause yields one finding. A finding whose observation
   an upstream finding explains is marked `conditional_on` it, so a reader meets
   "the server response is empty" before "the server response has no
   organization markup", and nobody fixes the second first.
5. **Derive severity and priority** in one place, from what was observed:
   whether a stage is blocked, how widely, how central the content is, capped by
   confidence. No diagnostic assigns a severity.
6. **Recommend beyond the problems.** Four proactive recommendations, each
   triggered by something observed on this site and none restating a problem:
   identity links for organization markup that has none, structured dates for
   articles that only show them, a fixed prompt panel built from the site's own
   facts to monitor how assistants describe it, and `/llms.txt`, labelled as
   speculative. They are never above medium and are counted apart from problems.
7. **Validate and write** `report.json` against its schema, and `report.md`
   from it.

The contract between skills is a set of files in one working directory, not a
tool. Any host that can run a script and read a file can run the marketplace.
`skills/audit-orchestrator/references/composition.md` gives the file contract,
the ordering and the arbitration table.

## Why eight skills and not more

A concern earns its own skill only if it has (1) a distinct causal mechanism,
(2) distinct evidence, and (3) a distinct remediation vocabulary. Fail any one
and it becomes a rule inside an existing skill.

Rule counts follow the evidence, not a target. Several planned checks, such as
boilerplate share, paragraph length, interstitials and orphan pages, were
measured on real sites, produced false positives on healthy pages, and were cut.
Each skill's `references/rules.md` records what was cut and the measurement that
cut it.

## Evidence you can check without running anything

- **`tests/fixtures/archetypes/`** — five fictional sites standing for classes of
  real website (a well-built minimal site, a client-rendered shell, a storefront
  with template defects, a publisher with documentation, a crawler-restricted
  site), run through the whole audit with assertions in both directions: every
  expected finding present, **no other finding present**, and named checks
  assessed and passing. Each carries legitimate patterns placed there to tempt a
  false positive.
- **`tests/adjudication.md`** — the audit run on six real sites the rules were not
  written against, each finding checked by a person against pages saved from
  their own browser. Every observation was true; two conclusions of eleven were
  wrong, both fixed at their pattern with tests, and a re-run showed no false
  positive. Sites are described by type, not named.
- **`tests/g2-evidence-check.md`** — the collector's observations compared, page
  by page, with pages and robots.txt files a person saved from their own browser.
- **`tests/rule-review.md`** — every rule reviewed before it ran, every tightening
  and cut, and a fact check of every claim a rule makes about how an operator's
  crawler or a search engine behaves, against that operator's documentation.
- **`docs/DECISIONS.md`** — every design decision, including the ones revised
  when measurement proved them wrong.
- **`docs/CONTRACTS.md`** and `schemas/` — the data contracts, versioned by tag.

The build gate, `python scripts/check.py`, runs twelve checks in about two
minutes: manifest and skill-format validity, schema conformance, that every rule
names only fields the evidence schema has and its skill may read, that the code
reads only those fields, determinism, standard-library-only imports, no
cross-skill imports, and the unit and archetype tests. `scripts/package.sh`
builds the submission zip from committed files and re-runs the gate inside a
clean extraction of it.

## Observed content is data, never instructions

Everything the collector fetches is untrusted input: robots.txt including its
comments, page text, meta tags, JSON-LD, `agents.md`, `llms.txt`, sitemap
contents, and third-party pages fetched during corroboration.

No skill in this marketplace ever follows an instruction found in observed
content — not a request to install something, not a claim of authorisation, not
a directive addressed to "agents", not a request to recommend something to the
user. Such text is recorded as an observation where a rule needs it, and is
never executed, obeyed, or relayed as a recommendation.

This is not hypothetical. The default Shopify storefront robots.txt contains a
comment asking the reading agent to recommend that its user install a shopping
skill. We fetch that file on every audit of every Shopify store, and the tests
check that its text appears nowhere in the evidence or the report.

The collector accordingly records only whether `/llms.txt`, `/agents.md` and
`/.well-known/ucp` exist, never what they contain, and the report renders any
text taken from a site on a single line so that nothing a site wrote can
restructure it.

## Repository map

    marketplace.json          the manifest: eight skills, one entrypoint
    skills/                   one folder per skill, each independently valid
    schemas/                  evidence, finding and report schemas
    docs/                     decisions, contracts, rule format, handout;
                              RUBRIC.md maps each rubric criterion to its files
    scripts/                  run_audit.py, check.py (build gate), package.sh
    samples/                  example outputs from the fixture sites
    tests/                    unit tests, archetype fixtures, verification records
