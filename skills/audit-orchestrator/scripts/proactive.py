"""Proactive recommendations: strengthening actions the evidence warrants.

Step 8 of ../SKILL.md. The two recommendations are specified as rule blocks in
../references/proactive.md, where their reasoning lives. Neither describes a
defect: both are ``status: proactive``, so severity is capped at medium and
priority held at P2 or P3 by severity.py, and neither can outrank a finding.

Each fires only on evidence. A recommendation that would appear identically in
every report would be the padding this project refuses.

Every claim value that enters a prompt is observed content, and CLAUDE.md
forbids relaying observed content as a recommendation. So the panel uses only
claim kinds whose values are short facts (a name, a year, an address), never a
tagline or a product string, and each value must be short and made only of the
characters such facts are written in. A value that fails is left out, and so is
the panel if the name fails.

Standard library only.
"""

import re

SKILL = "audit-orchestrator"
SAFE_VALUE = re.compile(r"^[\w .,&'()/-]{1,80}$", re.UNICODE)


def _ref(url, observation, retrieved_at):
    return {"url": url, "observation": observation, "layer": "first_party", "method": "fetch",
            "retrieved_at": retrieved_at}


def pro_001(evidence, out):
    """/llms.txt was probed, answered, and is not present."""
    entry = [w for w in evidence["well_known"] if w["path"] == "/llms.txt"]
    if not entry or entry[0]["status"] is None:
        out["not_assessed"].append({"rule_id": "PRO-001", "reason": "/llms.txt was not probed or did not answer",
                                    "enable_hint": "the probe runs only where robots.txt allows the path"})
        return
    if entry[0]["present"]:
        out["passed"].append({"rule_id": "PRO-001", "summary": "/llms.txt is present; nothing to recommend"})
        return
    origin = (evidence["site"]["resolved_origin"] or evidence["site"]["input"]).rstrip("/")
    out["findings"].append({
        "id": "F-001",
        "title": "Optional and speculative: publish /llms.txt",
        "evidence": "/llms.txt at %s answered HTTP %s and is not present. No major assistant is documented to read this "
                    "file, so this is listed only as a low-cost hedge, not as a gap." % (origin, entry[0]["status"]),
        "suggested_action": {
            "summary": "If it costs little, publish a short /llms.txt; do not expect it to change how assistants see "
                       "the site.",
            "what": "Publish a plain-text /llms.txt summarising what the site is and linking its key pages.",
            "where": "%s/llms.txt" % origin,
            "why": "It is a proposed convention some tools read; no major assistant documents consuming it, which is "
                   "why this is proactive and never a finding.",
            "how": "Write a short markdown file: one paragraph describing the organization, then links to the pages "
                   "that answer the questions people ask about it. Keep it consistent with those pages.",
            "mechanism": "A possible, undocumented discovery channel for tools that adopt the convention.",
            "success_criteria": "/llms.txt answers 200 with content that is not the site's soft-404 page.",
            "effort": "low",
        },
        "skill": SKILL, "rule_id": "PRO-001", "status": "proactive", "category": "discoverability",
        "symptom": ["invisible"], "confidence": "low",
        "impact": {"blocking": False, "breadth": "page", "content_importance": "secondary"},
        "scope": {"pages_affected": 0, "pages_examined": 0, "page_types": []},
        "evidence_refs": [_ref(origin + "/llms.txt", "HTTP %s, not present" % entry[0]["status"],
                               evidence["run_context"]["started_at"])],
        "false_positive_controls_applied": [], "exceptions_checked": [],
    })


QUESTIONS = {
    "legal_name": "What is {name}, and what does it do?",
    "founded_year": "When was {name} founded?",
    "address": "Where is {name} based?",
}


def pro_002(evidence, out):
    """A monitoring prompt panel, seeded from the claims this audit promoted."""
    claims = [c for c in evidence["canonical_claims"]
              if c["first_party_confidence"] in ("high", "medium") and c["kind"] in QUESTIONS
              and SAFE_VALUE.match(c["value_normalized"] or "")]
    names = [c for c in claims if c["kind"] == "legal_name"]
    if not names:
        out["not_assessed"].append({"rule_id": "PRO-002", "reason":
                                    "no organization name was promoted with at least medium confidence and a plain "
                                    "short value, so there is nothing safe to build a prompt panel around",
                                    "enable_hint": "state the organization's name in Organization JSON-LD"})
        return
    name = names[0]["value_normalized"]
    panel = []
    for claim in claims:
        question = QUESTIONS.get(claim["kind"])
        if question:
            panel.append("%s (expected: %s)" % (question.format(name=name, value=claim["value_normalized"]),
                                                claim["value_normalized"]))
    ambiguous = names[0]["entity_ambiguity"] == "high"
    origin = (evidence["site"]["resolved_origin"] or evidence["site"]["input"]).rstrip("/")
    out["findings"].append({
        "id": "F-001",
        "title": "Monitor how assistants describe %s with a fixed prompt panel" % name,
        "evidence": "This audit observes the site, not assistants' answers, by design. %d claims were promoted with at "
                    "least medium first-party confidence, which gives a panel whose expected answers are known: %s.%s"
                    % (len(claims), "; ".join(panel[:6]),
                       " The name was scored ambiguous, so answers may describe a different entity; add the domain to "
                       "each prompt." if ambiguous else ""),
        "suggested_action": {
            "summary": "Ask the same questions of the main assistants monthly and record whether each answer matches "
                       "the site.",
            "what": "Run a fixed panel of questions about %s against the assistants that matter to the site, on a "
                    "schedule, and record each answer against the expected value." % name,
            "where": "Outside the site: a shared sheet or a scheduled script owned by whoever owns the brand's facts.",
            "why": "Whether a fix changes what assistants say is not observable from the site, so it has to be "
                   "measured where it happens.",
            "how": "Use exactly these prompts each time, record date, assistant, answer and whether it matches: %s. "
                   "Re-run after each fix from this report to see whether it moved anything." % " | ".join(panel),
            "mechanism": "Turns the audit's fixes into something whose effect can be seen.",
            "success_criteria": "A dated record of answers per assistant exists, and each answer is marked as "
                                "matching or not matching the site's stated value.",
            "effort": "low",
        },
        "skill": SKILL, "rule_id": "PRO-002", "status": "proactive", "category": "discoverability",
        "symptom": ["misrepresented"], "confidence": "medium",
        "impact": {"blocking": False, "breadth": "site", "content_importance": "secondary"},
        "scope": {"pages_affected": 0, "pages_examined": 0, "page_types": []},
        "evidence_refs": [_ref(origin + "/", "claims promoted from first-party evidence: %d" % len(claims),
                               evidence["run_context"]["started_at"])],
        "false_positive_controls_applied": [], "exceptions_checked": [],
    })


RECOMMENDATIONS = (pro_001, pro_002)


def recommend(evidence):
    """Findings, not_assessed and checks_passed for every proactive recommendation."""
    out = {"findings": [], "not_assessed": [], "passed": []}
    for build in RECOMMENDATIONS:
        build(evidence, out)
    return out["findings"], out["not_assessed"], out["passed"]
