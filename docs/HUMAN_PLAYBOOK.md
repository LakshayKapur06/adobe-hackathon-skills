# HUMAN_PLAYBOOK.md — what only you can do

> **Status:** every gate below was run. G2 is recorded in
> `tests/g2-evidence-check.md`, G3 in `tests/rule-review.md`, and G4 in
> `tests/adjudication.md`, which used 6 sites, one per archetype, rather than 8-10.

The agent builds. You verify. This file is the verification procedure.

---

## Checkpoint gates

Do not let the build move past a gate until it passes. Say "gate not passed,
here is what is wrong" rather than accepting and fixing later.

| Gate | When | What you check |
|---|---|---|
| G1 Contracts frozen | End of Day 1 | Read `CONTRACTS.md` end to end. Every field you can imagine a rule needing exists. Once you approve it, the agent may not change it without asking |
| G2 Evidence is true | End of Day 2 | Run against 3 real sites. Open the same pages in your browser. Does the recorded evidence match reality? A wrong evidence bundle makes every downstream finding wrong |
| G3 Rules are justified | End of Days 3 and 4 | Every rule block complete, every threshold justified, every false-positive control real. Reject any rule you could paste into an unrelated case study |
| G4 Adjudication | Day 5 | The procedure below |
| G5 Judge read-through | Day 6 | Read only `SKILL.md` and `references/` files, as a skeptical judge |

---

## G4: the adjudication pass (the one that decides the score)

### Step 1 — pick 8-10 sites yourself

Do not let the agent pick them; it will pick sites that make the tool look good.
Choose by these criteria, one site each:

- a small local business (5-15 pages)
- a heavy SPA storefront
- a large e-commerce catalogue
- a documentation or developer site
- a news or publisher site
- a multilingual site
- a university or government site (unusual but valid architecture)
- a very well-built, minimal marketing site
- one site in a language you read that is not English
- one site you personally know well, so you can spot wrong claims instantly

Pick sites you have no relationship with, and remember the audit is read-only.

### Step 2 — adjudicate every finding

For each finding, in this order:

1. **Verify the observation, not the conclusion.** Open the URL. Is the recorded
   fact literally true? (Is the price actually missing from the server HTML? Use
   view-source or fetch with JS disabled.)
2. **Then judge the interpretation.** Given that the observation is true, is the
   conclusion warranted?
3. **Then check the exceptions.** Is there a legitimate reason this site is fine?

Record a verdict in `tests/adjudication.csv`:

| Verdict | Meaning | What it triggers |
|---|---|---|
| `TP` | Observation true, conclusion warranted | Nothing |
| `FP-OBS` | The recorded observation is factually wrong | **Collector bug. Highest priority.** One of these means the evidence layer is unreliable and other findings are suspect |
| `FP-INT` | Observation true, conclusion wrong | Tighten the threshold or add a false-positive control |
| `FP-EXC` | Legitimate exception the rule failed to detect | Add the exception to the rule and make it detectable |
| `MISS` | You can see a real problem the audit did not flag | Note it; only fix if cheap |

Columns: `site, rule_id, finding_id, verdict, note, fixture_created`.

### Step 3 — apply the rule-health thresholds

Across your 8-10 sites:

- **Any FP at `critical` or `high`** -> fix before anything else. A confidently
  wrong high-severity finding is the single most damaging output we can produce.
- **A rule with >= 2 FPs** -> tighten the threshold, add a control, or gate it
  behind stronger minimum evidence.
- **A rule with >= 4 FPs** -> cut the rule. Do not try to save it on Day 5.
- **Overall FP rate must be < 10%.** If it is not, cut the worst rules until it is.
  A tool with 15 reliable rules beats one with 40 noisy ones under this rubric.
- **The well-built minimal site should produce almost no findings.** If it
  produces many, the rules are measuring conformity rather than defects. This is
  the single most informative test in the set.

### Step 4 — every FP becomes a fixture

Save the offending page (or a recorded response) into `tests/fixtures/` with a
test asserting the rule now does **not** fire. This is what stops a later change
from reintroducing it.

---

## G5: the Day 6 judge read-through

Read only what a judge would read, in this order, without running anything:
`README.md`, `marketplace.json`, `skills/audit-orchestrator/SKILL.md`, then each
diagnostic's `SKILL.md` and `references/rules.md`.

Ask, honestly:

1. Can I tell what each skill does and why it exists, in one read?
2. Does the decomposition look like genuine separation of concerns, or padding?
   Could I merge any two skills without losing anything?
3. Is any check just generic SEO wearing a mechanism costume?
4. Where could this fabricate or overstate evidence?
5. What happens on a 5-page site? A 50,000-page site? A site that blocks us?
   Can I find the answer in the files?
6. Which recommendation would embarrass us in front of a real brand?
7. What here looks like padding to a tired reader at 11pm?

Anything you cannot answer from the files alone is a documentation gap, and
documentation is a graded surface here.

---

## Things to say to the agent when it drifts

- "That threshold has no justification. Add one or cut the rule."
- "This rule has no false-positive control. It does not ship."
- "You changed `CONTRACTS.md`. Revert it and tell me why you wanted to."
- "That is symptom-shaped, not mechanism-shaped. Which existing skill owns it?"
- "You are at 12 rules for this skill. What are you cutting?"
- "Show me the evidence field path this reads. Is it in the schema?"
- "That recommendation would paste into any unrelated case study. Make it
  specific to what we observed."
