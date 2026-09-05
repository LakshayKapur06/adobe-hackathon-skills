# Kickoff prompt for Claude Code

Copy everything in the fenced block below as your first message in Claude Code,
after you have (1) created the repo, (2) dropped in `CLAUDE.md` and the `docs/`
files, and (3) copied the Round 3 handout PDF into `docs/handout/`.

```
Read CLAUDE.md, docs/DECISIONS.md, docs/CONTRACTS.md, docs/RULE_FORMAT.md and
docs/PLAN.md in full before writing anything. Also read the handout PDF in
docs/handout/ — it is the authoritative specification.

We are building an Agent Skill Marketplace for the Adobe University Hackathon
2026 Round 3. The architecture, the skill roster, the data contracts and the
deliberate exclusions are already decided and recorded in those files. Do not
re-derive them and do not work around them. If you think one is wrong, say so
explicitly and wait for my answer.

Today is Day 1. Build only the Day 1 scope from docs/PLAN.md:

1. Repo skeleton: marketplace.json (exactly one entrypoint: audit-orchestrator)
   and all 8 skill folders, each with a valid agentskills.io SKILL.md containing
   name, description, license, allowed-tools, and the sections When to use /
   Inputs / Procedure / Output. Keep each SKILL.md lean; detail goes to
   references/.
2. JSON Schemas for evidence.json and the finding object, generated strictly
   from docs/CONTRACTS.md. Do not add, rename or drop a field.
3. The severity() and priority() functions exactly as specified in
   docs/CONTRACTS.md, with unit tests covering the full truth table of
   blocking x breadth x content_importance x confidence x effort x status.
4. The CI harness, as a single `make check` (or scripts/check.sh):
   - agentskills.io validation of every skill folder
   - marketplace.json shape: every path exists, exactly one entrypoint
   - JSON Schema conformance for evidence and findings
   - rule-block completeness: every rule in every references/rules.md has all 14
     fields from docs/RULE_FORMAT.md, non-empty
   - evidence-field existence: every field path named under "Evidence read" in
     any rule must exist in the evidence schema. Fail the build if not.
   - grep for TODO, FIXME, stub, placeholder — fail if found
   - determinism: same fixture twice, identical output except timestamps
   - stdlib-only check for the six diagnostic skills
5. An empty-but-valid fixture site under tests/fixtures/ so CI has something to
   run against.

Constraints for today: no detection rules yet, no crawling yet. Contracts and
scaffolding only. End the day with `make check` green and one commit per logical
unit.

When you are done, show me: the tree, the marketplace.json, one representative
SKILL.md, and the check output. Then stop and wait.
```

## Subsequent days

Start each day with:

```
Read CLAUDE.md and docs/PLAN.md. We are on Day N. Build only the Day N scope.
Before you start, tell me in five lines what you are about to build and what you
expect to be hard. Then stop and wait for my go.
```

That "tell me first, then wait" step is cheap and catches misunderstandings
before they become a day of work in the wrong direction.
