# CLAUDE.md — standing rules for this repository

You are building `agent-readiness-audit`, an Agent Skill Marketplace for the
Adobe University Hackathon 2026 Round 3. Read `docs/DECISIONS.md`,
`docs/CONTRACTS.md`, `docs/RULE_FORMAT.md` and `docs/PLAN.md` before writing
anything. The authoritative challenge specification is the PDF in
`docs/handout/`.

## Non-negotiable constraints (from the handout)

- **Recommend-only.** No skill ever modifies the audited site. Writes go only to
  the local working directory.
- **No destructive, authenticated, or rate-abusing actions.** Never submit a
  form, never traverse a login, never click.
- **Respect robots.txt** — for the audited domain *and* for every third-party
  domain we fetch. This is easy to forget and we are graded on it.
- **Provider-neutral.** Never depend on a host-specific tool. Capability lives in
  `scripts/`; the contract between skills is a file, not a tool.
- **Exactly one entrypoint** in `marketplace.json`: `audit-orchestrator`.
- **Submission zip <= 50 MB.** Never bundle a browser or model weights.
- **Typical audit runtime < 5 minutes**, enforced by a global deadline.

## Engineering rules

1. **`docs/CONTRACTS.md` is frozen.** Do not modify the evidence schema, the
   finding schema, or the severity function. If you believe a change is needed,
   stop and ask. Silent contract drift is the top build risk.
2. **`marketplace.json`'s skill list is frozen** after Day 1. Do not add,
   remove, or rename a skill without explicit approval.
3. **Parsing is stdlib-only, always.** `html.parser`, `urllib`, `json`, `re`,
   `concurrent.futures`. Third-party libraries may only be optional performance
   paths that produce byte-identical extraction output, proven by a conformance
   test. Never let a dependency change extraction *semantics*.
4. **Diagnostic skills never touch the network.** They read `evidence.json` and
   emit findings. All fetching happens in `site-evidence-collector`.
5. **No cross-skill imports.** Every skill folder must remain independently
   valid and portable if lifted out on its own.
6. **Every rule reads declared evidence fields.** A rule that references a field
   not present in the schema is a build failure, not a warning. CI enforces this.
   This is our anti-hallucination guard: it makes invented evidence impossible.
7. **No placeholders.** No `TODO`, `FIXME`, `pass  # stub`, or rules whose
   thresholds are unexplained. CI greps for these.
8. **Rule budget: maximum 12 rules per diagnostic skill.** If you want a 13th,
   something must be cut or merged. This forces prioritisation and prevents
   rule-count inflation, which the rubric explicitly penalises as padding.
9. **Every rule block must have all fields in `docs/RULE_FORMAT.md` filled and
   non-empty**, including false-positive controls and legitimate exceptions.
   CI validates this structurally.
10. **Determinism.** Running twice against the same fixture must produce
    identical output except timestamps. There is a test for this.
11. **Commit per skill, never a mega-commit.** Small reviewable diffs.
12. **No new dependencies without approval.**

## Scope discipline

- Do **not** infer additional handout requirements. If a requirement is not in
  `docs/DECISIONS.md` or the PDF in `docs/handout/`, ask before implementing.
- Do **not** re-litigate settled decisions. `docs/DECISIONS.md` records what was
  decided and why, including deliberate exclusions. If you think one is wrong,
  say so explicitly and wait, do not silently work around it.
- Prefer cutting a weak rule over shipping it. Under this rubric a false
  positive costs more than a miss.
