"""Arbitration: which findings are conditional on an upstream one.

This is rule 3 of the arbitration section in ../references/composition.md, as a
table. A diagnostic reports what it observed and cannot know what another skill
found, so only the orchestrator can say "fix that first". It never deletes a
finding and never changes a severity: it adds ``conditional_on`` and nothing
else.

The table is deliberately small. Every entry is a case where the upstream
finding explains the downstream one's observation, not merely a case where both
are bad. Two things are left out on purpose, and composition.md says why:
crawler exclusions (ACC-001, ACC-008), which remove some assistants but not all,
so content fixes still matter for the rest; and merging, because the rules
already exclude each other's cases (ACC-003/ACC-004, RND-001/RND-002/RND-003),
so no two findings share one root cause.

Standard library only, no imports: liftable like severity.py.
"""

# Findings that conclude something is absent from the server response. When the
# server response itself is empty or JavaScript-assembled, that absence is
# already explained upstream.
ABSENCE_IN_SERVER_RESPONSE = ("IDM-001", "ANS-001", "FRC-001")

# Skills whose findings are about content that only matters once it is indexed.
CONTENT_SKILLS = ("render-and-extraction", "identity-and-markup", "answerability", "freshness-and-corroboration")


def _types(finding):
    return set(finding.get("scope", {}).get("page_types", []))


def _add(finding, rule_id, reason):
    entries = finding.setdefault("conditional_on", [])
    if not any(e["rule_id"] == rule_id for e in entries):
        entries.append({"rule_id": rule_id, "reason": reason})


def arbitrate(findings):
    """Mark conditional findings in place and return the list."""
    empty_site = [f for f in findings if f["rule_id"] == "RND-002"
                  or (f["rule_id"] == "RND-001" and f["impact"]["breadth"] == "site")]
    template_js = [f for f in findings if f["rule_id"] == "RND-001" and f["impact"]["breadth"] != "site"]
    noindex_site = [f for f in findings if f["rule_id"] == "ACC-003" and f["impact"]["breadth"] == "site"]

    for finding in findings:
        rule = finding["rule_id"]
        if rule in ABSENCE_IN_SERVER_RESPONSE:
            for upstream in empty_site:
                _add(finding, upstream["rule_id"],
                     "the server response carries little or no page text, so this absence may disappear once the "
                     "content is server-rendered; re-assess after that fix")
            for upstream in template_js:
                if _types(finding) & _types(upstream):
                    _add(finding, upstream["rule_id"],
                         "the %s template assembles its text in the browser, so this absence may disappear once it "
                         "is server-rendered" % ", ".join(sorted(_types(upstream))))
        if finding["skill"] in CONTENT_SKILLS and finding["category"] == "discoverability":
            for upstream in noindex_site:
                _add(finding, upstream["rule_id"],
                     "the affected templates refuse indexing, so no content improvement reaches an index until "
                     "noindex is removed")
    return findings
