# Rule review log

Static review of every rule block before it ever runs against a real site.
Five tests, in order. Each is a hard stop: fail one, reject, stop reading.

| Test | What it asks | Reject when |
|---|---|---|
| 1 Mechanism | Does it explain *causally* why this affects a machine reaching, reading, retrieving or quoting — or a visitor orienting? | "Best practice", "industry standard", "Google recommends", "improves SEO", "signals quality", "users expect". Convention is not mechanism |
| 2 Threshold | Is there a number, and does the justification explain *why that number*, referencing how real sites vary? | Circular justification ("three is a reasonable minimum"). If you cannot tell what would change were the number doubled, it is not justified |
| 3 Minimum evidence | What happens when data is thin? Exactly three legal outcomes: fire, `checks_passed`, `not_assessed` | The rule treats "we did not observe it" as "it is fine". That is a clean bill of health for an unexamined site |
| 4 False positives | Name a real site where the signal is present and the site is fine. Would the listed controls stop it firing? | The exception you thought of is missing, or is listed but not *detectable from evidence*. Undetectable exceptions are decoration |
| 5 Remediation | Read only what/where/why/how/mechanism/success_criteria | It would paste into an unrelated case study, or `success_criteria` names nothing observable |

Cross-cutting, checked per skill once its rules are complete:

- **Impact inputs derived, not asserted.** The block must say *how* `breadth` is computed from evidence, not simply declare it.
- **`severity` appears nowhere in the block.** It is derived by the orchestrator. A rule assigning it is a contract violation.
- **Overlap.** Does any rule reach the same conclusion from the same evidence fields as a rule in another skill? Two rules on one root cause is the duplication a judge calls padding. One becomes evidence on the other.

---

## Log

| rule_id | skill | test failed | what I said | outcome |
|---|---|---|---|---|
| | | | | tightened / cut / accepted |

## Accepted without change

| rule_id | skill | note |
|---|---|---|
