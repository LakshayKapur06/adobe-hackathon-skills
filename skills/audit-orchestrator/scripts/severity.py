"""Severity and priority derivation for the audit report.

This is the single implementation of docs/CONTRACTS.md section 3. It lives with
the orchestrator because the orchestrator is the only component permitted to
derive these two fields: diagnostics declare what they observed
(``impact``, ``confidence``, ``status``, ``effort``) and this module turns those
observations into the two judgements a reader acts on. Keeping it in one place
is what makes the truth table testable and stops six diagnostic skills drifting
into six severity dialects.

Severity is defined on observables only. We can observe that a fact is absent
from a server response and that the affected template spans the whole site. We
cannot observe whether fixing it changes how often an assistant cites the brand,
so severity never encodes a predicted AI outcome.

Standard library only, and no imports at all: this module must stay liftable
into any skill folder without dragging a dependency behind it.
"""

# Most severe first. Order matters: it is the comparison key for both the
# confidence cap and the report ordering.
ORDER = ["critical", "high", "medium", "low"]

BREADTHS = ("site", "section", "page")
CONFIDENCES = ("high", "medium", "low")
EFFORTS = ("low", "medium", "high")
STATUSES = ("found", "risk", "proactive")
PRIORITIES = ("P0", "P1", "P2", "P3")

# The most severe rating a finding may carry at each confidence level.
# Only a high-confidence finding can ever be critical.
CONFIDENCE_CAP = {"high": "critical", "medium": "high", "low": "medium"}

# The most severe rating a proactive finding may carry (contracts-v3). A
# proactive finding describes a real, observed situation that is not a defect,
# such as a crawler the owner excluded by name. Its impact inputs must stay
# honest about what that situation costs, so the status caps the derived
# severity instead of forcing the rule to understate its impact. `risk` is
# deliberately not capped here: a risk finding claiming critical impact is an
# authoring error, and status_violations still rejects it loudly.
STATUS_CAP = {"proactive": "medium"}


def severity(impact, confidence):
    """Derive severity from observed impact, capped by confidence.

    ``impact`` is a mapping with ``blocking`` (bool), ``breadth``
    (``site``/``section``/``page``) and ``content_importance``
    (``primary``/``secondary``). ``confidence`` is ``high``/``medium``/``low``.

    The cap binds downward: a finding can only be as severe as the confidence in
    the diagnosis allows, so only a high-confidence finding can ever be
    ``critical``. The truth table in tests/test_severity.py asserts that in every
    one of the 324 combinations.
    """
    blocking = impact["blocking"]
    breadth = impact["breadth"]
    importance = impact["content_importance"]

    if not isinstance(blocking, bool):
        raise ValueError("impact.blocking must be a bool, got %r" % (blocking,))
    if breadth not in BREADTHS:
        raise ValueError("impact.breadth must be one of %s, got %r" % (BREADTHS, breadth))
    if importance not in ("primary", "secondary"):
        raise ValueError("impact.content_importance must be primary or secondary, got %r" % (importance,))
    if confidence not in CONFIDENCES:
        raise ValueError("confidence must be one of %s, got %r" % (CONFIDENCES, confidence))

    primary = importance == "primary"

    if blocking and breadth == "site" and primary:
        base = "critical"
    elif blocking and breadth in ("site", "section"):
        base = "high"
    elif not blocking and breadth == "site" and primary:
        base = "high"
    elif breadth in ("site", "section"):
        # Not `breadth == "section"`. The narrower form scored a non-blocking
        # site-wide secondary problem below the same problem confined to one
        # section, which inverts the ladder. Severity must be monotonic in every
        # impact input; tests/test_severity.py enforces all three directions.
        base = "medium"
    else:
        base = "low"

    cap = CONFIDENCE_CAP[confidence]
    # ORDER is most-severe-first, so a HIGHER index is LESS severe.
    # The cap must bind downward: take whichever is less severe.
    return base if ORDER.index(base) >= ORDER.index(cap) else cap


def priority(sev, effort, status):
    """Derive the action priority from severity, effort and status.

    Priority is what a reader acts on in order, so it is severity adjusted by
    how expensive the fix is. Proactive recommendations are held at P2/P3 by
    construction: a strengthening idea must never outrank an observed defect.
    """
    if sev not in ORDER:
        raise ValueError("severity must be one of %s, got %r" % (ORDER, sev))
    if effort not in EFFORTS:
        raise ValueError("effort must be one of %s, got %r" % (EFFORTS, effort))
    if status not in STATUSES:
        raise ValueError("status must be one of %s, got %r" % (STATUSES, status))

    if status == "proactive":
        return "P3" if effort == "high" else "P2"
    if sev == "critical":
        return "P0"
    if sev == "high":
        return "P2" if effort == "high" else "P1"
    if sev == "medium":
        return "P2"
    return "P3"


def status_violations(sev, prio, status):
    """Return the status-semantics violations in a derived finding.

    These are the invariants stated under "Status semantics" in
    docs/CONTRACTS.md. They are not enforced inside ``severity`` because
    severity's contract signature takes only impact and confidence; they are a
    property of the assembled finding, so the orchestrator checks them after
    derivation and CI checks them on every fixture.

    A violation here means a diagnostic declared an impossible combination --
    for example a ``risk`` finding whose evidence is suggestive but incomplete,
    claiming site-wide blocking impact at high confidence. That is an authoring
    error in the rule, and it should fail loudly rather than ship a confidently
    wrong critical finding, which is the single most damaging output we can
    produce.
    """
    problems = []
    if status == "risk" and sev == "critical":
        problems.append("status 'risk' may never be critical; evidence is by definition incomplete")
    if status == "proactive":
        if ORDER.index(sev) < ORDER.index("medium"):
            problems.append("status 'proactive' may never exceed medium severity, got %r" % (sev,))
        if prio not in ("P2", "P3"):
            problems.append("status 'proactive' must be P2 or P3, got %r" % (prio,))
    return problems


def derive(finding):
    """Fill in the two derived fields on a finding, in place, and return it.

    A proactive finding's severity is capped at medium by STATUS_CAP. Raises
    ValueError if the diagnostic declared a combination the status semantics
    still forbid, such as a risk finding deriving to critical, so that an
    authoring error cannot reach a report.
    """
    sev = severity(finding["impact"], finding["confidence"])
    cap = STATUS_CAP.get(finding["status"])
    if cap is not None and ORDER.index(sev) < ORDER.index(cap):
        sev = cap
    prio = priority(sev, finding["suggested_action"]["effort"], finding["status"])
    problems = status_violations(sev, prio, finding["status"])
    if problems:
        raise ValueError(
            "finding %s (rule %s): %s"
            % (finding.get("id", "<no id>"), finding.get("rule_id", "<no rule>"), "; ".join(problems))
        )
    finding["severity"] = sev
    finding["suggested_action"]["priority"] = prio
    return finding


def sort_key(finding):
    """Ordering for the report: worst and cheapest first, then stable by id.

    Readers act top-down, so the list is ordered by priority, then by severity
    within a priority, then by effort so the cheapest of two equal actions comes
    first, then by id so two runs over the same evidence order identically.
    """
    return (
        PRIORITIES.index(finding["suggested_action"]["priority"]),
        ORDER.index(finding["severity"]),
        EFFORTS.index(finding["suggested_action"]["effort"]),
        finding["id"],
    )
