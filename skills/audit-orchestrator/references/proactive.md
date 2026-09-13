# Proactive recommendations — the orchestrator's two

The orchestrator owns no detection rules. It does own step 8 of its procedure:
strengthening actions the evidence warrants even where nothing is wrong. They are
specified here in the same fourteen-field block the diagnostics use, so a reader
can hold them to the same standard, and implemented in `scripts/proactive.py`.

Both are `status: proactive`. Under `contracts-v3` that caps their severity at
`medium` and holds their priority at P2 or P3, so neither can ever outrank a
finding. Each fires only on evidence. PRO-002 is specific to the site by
construction, since its prompts are built from the site's own claims. PRO-001
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

## Rule budget

Rules defined: 2 of a maximum 12.

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
  name, founding year and address kinds; the value filter above; when the name
  was scored ambiguous, the recommendation says so and tells the reader to add
  the domain to each prompt.
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
