# Real-site adjudication

The audit was run on six real websites that neither the rules nor the fixtures
were written against. A person then checked every finding against the live
sites. This page records what they found, what was wrong, and what changed
because of it. Verdicts per finding are in `tests/adjudication.csv`.

Sites are described by type, not named: this repository publishes no audit of a
named third party (D11 in `docs/DECISIONS.md`).

## Method

Six sites, one per archetype in `docs/HUMAN_PLAYBOOK.md`, chosen by the person
adjudicating rather than by the agent that built the audit, because an agent
picks sites that flatter its own tool:

| Id | Site type |
|---|---|
| S1 | well-built minimal marketing site |
| S2 | small storefront the adjudicator knows well |
| S3 | large e-commerce retailer |
| S4 | documentation subdomain of a large company |
| S5 | non-English (Hindi) news publisher |
| S6 | university |

Each site was audited alone, in 73 to 178 seconds of wall time. For every finding, the adjudicator asked three questions in order:

1. Is the recorded observation literally true?
2. Does the conclusion follow from it?
3. Is there a legitimate reason the site is fine that the rule missed?

Observations were verified against files the adjudicator saved from their own
browser: page source from `view-source:`, the rendered DOM copied from developer
tools, robots.txt files and HTTP statuses. The agent compared those files with
what the audit recorded, using a parser that shares no code with the collector,
and the curl checks were re-run with a different HTTP client. Conclusions and
exceptions were the adjudicator's call.

## Result

**Every observation was true.** No finding rested on something the collector
saw wrongly.

**Two conclusions were wrong**, out of 11 findings (18%); among the 5 findings
reported as problems rather than proactive suggestions, 2 of 5:

| Site | Finding | Verdict | Why the conclusion was wrong |
|---|---|---|---|
| S3 | ACC-006, AI crawlers refused where robots.txt admits them (medium risk) | FP-INT | A Googlebot user-agent was refused too, in the audit's own probe and in an independent curl check. That is an edge refusing every declared crawler it cannot verify by address, which admits the real crawlers from their published ranges, not a block on AI crawlers |
| S4 | IDM-001, no machine-readable organization identity (medium) | FP-EXC | The subdomain has none, but the company's main domain carries complete Organization markup, which is where Google places it. The audit never looks at the parent domain |

**One true positive had a misleading label.** On S4, RND-001 (high) correctly
found pages that send about 2% of their text without JavaScript (1,155 of 67,950
characters), but called them "doc pages". They were one client-side application
under a single path, which the URL-based page-type guess had spread across three
types.

**One suggestion exposed a latent pattern.** The adjudicator asked the prompt
panel's questions (PRO-002) of a real assistant for S2. The expected founding
year was right for S2, but it had been read from a sentence about the parent
company. Re-reading all saved runs found the same extractor taking "since 2024"
from a news headline on another publisher and promoting it at medium confidence.

## What changed

Each problem was fixed at its pattern, not for the site, with a test that
reproduces the pattern on fictional data:

| Decision | Change | Test |
|---|---|---|
| D30 | ACC-006 reports not assessed when Googlebot is refused on the same URLs; a site refusing AI crawlers while admitting Googlebot still fires | `test_access_rules.TestACC006.test_googlebot_refused_too_reads_as_verification_not_a_block`; archetype `storefront-defects / bot-verification-edge` |
| D30 | IDM-001 reports not assessed on a subdomain other than `www`, naming the main domain to check | `test_identity_rules.TestIDM001.test_a_subdomain_defers_to_its_main_domain` |
| D30 | RND-001 names the path a section's JavaScript-dependent pages share | `test_render_rules.TestRND001.test_a_shared_path_names_the_application_not_the_guessed_type` |
| D31 | A founding year is promoted above low confidence only from organization markup, never from prose | `test_corroboration.TestPromotion.test_a_founding_year_from_prose_has_no_subject_to_assert` |
| D31 | The prompt panel names the domain for medium-ambiguity names too | `test_orchestrator.TestProactive.test_ambiguous_name_is_flagged_in_the_panel` |

## Second pass

S3, S4 and S1 (unchanged, as a control) were audited again after the D30 fixes:

| Site | Before | After |
|---|---|---|
| S3 | ACC-006, IDM-001, PRO-001 | IDM-001, PRO-001; ACC-006 not assessed, with the verification reason |
| S4 | RND-001 (high), IDM-001 | RND-001 (high), titled for the shared path; IDM-001 not assessed, naming the main domain |
| S1 | IDM-001, PRO-001 | identical |

On the same six sites, the findings after the fixes contain no false positive:
9 findings, 3 of them problems.

**What this does and does not show.** The second pass confirms the fixes remove
the false positives and break no true positive. It is not an independent
measure of accuracy on unseen sites, because the fixes were made after looking
at these sites. The evidence for generalization is that each fix targets a
pattern that recurs across the web (bot management, documentation subdomains,
single-page applications under one path, prose dates), that each is tested on
fictional data, and the archetype suite in `tests/fixtures/archetypes/`.
