"""Truth-table tests for the severity and priority derivation.

The table is exhaustive: every combination of blocking x breadth x
content_importance x confidence x effort x status, 2*3*2*3*3*3 = 324 cases.

The expectations are written as literal tables rather than by calling the
implementation a second time, so that a change to the implementation cannot
quietly change what the test asserts.
"""

import importlib.util
import itertools
import pathlib
import unittest

_SEV_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "skills" / "audit-orchestrator" / "scripts" / "severity.py"
)
_spec = importlib.util.spec_from_file_location("severity_under_test", _SEV_PATH)
sev_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sev_mod)

BLOCKING = (True, False)
BREADTH = ("site", "section", "page")
IMPORTANCE = ("primary", "secondary")
CONFIDENCE = ("high", "medium", "low")
EFFORT = ("low", "medium", "high")
STATUS = ("found", "risk", "proactive")

# Uncapped severity for every (blocking, breadth, content_importance) triple,
# written out by hand from the branch ladder in docs/CONTRACTS.md section 3.
EXPECTED_BASE = {
    (True, "site", "primary"): "critical",
    (True, "site", "secondary"): "high",
    (True, "section", "primary"): "high",
    (True, "section", "secondary"): "high",
    (True, "page", "primary"): "low",
    (True, "page", "secondary"): "low",
    (False, "site", "primary"): "high",
    (False, "site", "secondary"): "medium",
    (False, "section", "primary"): "medium",
    (False, "section", "secondary"): "medium",
    (False, "page", "primary"): "low",
    (False, "page", "secondary"): "low",
}

# The most severe rating each confidence level permits.
EXPECTED_CAP = {"high": "critical", "medium": "high", "low": "medium"}

RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def cap_to(base, cap):
    """The less severe of base and cap."""
    return base if RANK[base] >= RANK[cap] else cap


def cases():
    return itertools.product(BLOCKING, BREADTH, IMPORTANCE, CONFIDENCE, EFFORT, STATUS)


class TestSeverityTruthTable(unittest.TestCase):
    def test_table_is_exhaustive(self):
        self.assertEqual(len(list(cases())), 324)
        self.assertEqual(len(EXPECTED_BASE), len(BLOCKING) * len(BREADTH) * len(IMPORTANCE))

    def test_every_combination(self):
        for blocking, breadth, importance, confidence, _effort, _status in cases():
            with self.subTest(blocking=blocking, breadth=breadth, importance=importance,
                              confidence=confidence):
                impact = {
                    "blocking": blocking,
                    "breadth": breadth,
                    "content_importance": importance,
                }
                expected = cap_to(
                    EXPECTED_BASE[(blocking, breadth, importance)],
                    EXPECTED_CAP[confidence],
                )
                self.assertEqual(sev_mod.severity(impact, confidence), expected)

    def test_only_high_confidence_can_be_critical(self):
        for blocking, breadth, importance, confidence, _e, _s in cases():
            impact = {"blocking": blocking, "breadth": breadth, "content_importance": importance}
            if sev_mod.severity(impact, confidence) == "critical":
                self.assertEqual(confidence, "high")

    def test_confidence_cap_binds_everywhere(self):
        """Lowering confidence never makes a finding more severe."""
        for blocking, breadth, importance, _c, _e, _s in cases():
            impact = {"blocking": blocking, "breadth": breadth, "content_importance": importance}
            ranks = [RANK[sev_mod.severity(impact, c)] for c in ("high", "medium", "low")]
            self.assertEqual(ranks, sorted(ranks), (impact, ranks))

    def test_rejects_unknown_values(self):
        good = {"blocking": True, "breadth": "site", "content_importance": "primary"}
        with self.assertRaises(ValueError):
            sev_mod.severity(good, "very-high")
        with self.assertRaises(ValueError):
            sev_mod.severity({**good, "breadth": "everything"}, "high")
        with self.assertRaises(ValueError):
            sev_mod.severity({**good, "content_importance": "tertiary"}, "high")
        with self.assertRaises(ValueError):
            sev_mod.severity({**good, "blocking": "yes"}, "high")


class TestSeverityIsMonotonic(unittest.TestCase):
    """Severity must never move backwards when an impact input gets worse.

    A ladder written as a branch cascade is easy to get subtly wrong: an earlier
    branch can capture a case a later one was meant to widen, and the result is
    an inversion that looks fine in any single row of the truth table. These
    three properties are what catch that, and they hold across every confidence
    level because the confidence cap is itself monotonic.
    """

    @staticmethod
    def sev(blocking, breadth, importance, confidence):
        return RANK[sev_mod.severity(
            {"blocking": blocking, "breadth": breadth, "content_importance": importance},
            confidence,
        )]

    def test_widening_breadth_never_lowers_severity(self):
        for blocking in BLOCKING:
            for importance in IMPORTANCE:
                for confidence in CONFIDENCE:
                    with self.subTest(blocking=blocking, importance=importance,
                                      confidence=confidence):
                        ranks = [self.sev(blocking, b, importance, confidence)
                                 for b in ("page", "section", "site")]
                        # RANK counts down in severity, so widening breadth must
                        # produce a non-increasing sequence of ranks.
                        self.assertEqual(
                            ranks, sorted(ranks, reverse=True),
                            "page/section/site ranks %s are not monotonic" % (ranks,),
                        )

    def test_blocking_is_never_less_severe_than_non_blocking(self):
        for breadth in BREADTH:
            for importance in IMPORTANCE:
                for confidence in CONFIDENCE:
                    with self.subTest(breadth=breadth, importance=importance,
                                      confidence=confidence):
                        self.assertLessEqual(
                            self.sev(True, breadth, importance, confidence),
                            self.sev(False, breadth, importance, confidence),
                        )

    def test_primary_is_never_less_severe_than_secondary(self):
        for blocking in BLOCKING:
            for breadth in BREADTH:
                for confidence in CONFIDENCE:
                    with self.subTest(blocking=blocking, breadth=breadth,
                                      confidence=confidence):
                        self.assertLessEqual(
                            self.sev(blocking, breadth, "primary", confidence),
                            self.sev(blocking, breadth, "secondary", confidence),
                        )


class TestPriorityTruthTable(unittest.TestCase):
    # Priority for (severity, effort) when status is found or risk, written out
    # by hand from the branch ladder in docs/CONTRACTS.md section 3.
    EXPECTED_DEFECT = {
        ("critical", "low"): "P0", ("critical", "medium"): "P0", ("critical", "high"): "P0",
        ("high", "low"): "P1", ("high", "medium"): "P1", ("high", "high"): "P2",
        ("medium", "low"): "P2", ("medium", "medium"): "P2", ("medium", "high"): "P2",
        ("low", "low"): "P3", ("low", "medium"): "P3", ("low", "high"): "P3",
    }
    EXPECTED_PROACTIVE = {"low": "P2", "medium": "P2", "high": "P3"}

    def test_every_combination(self):
        for sev in sev_mod.ORDER:
            for effort in EFFORT:
                for status in STATUS:
                    with self.subTest(sev=sev, effort=effort, status=status):
                        got = sev_mod.priority(sev, effort, status)
                        if status == "proactive":
                            self.assertEqual(got, self.EXPECTED_PROACTIVE[effort])
                        else:
                            self.assertEqual(got, self.EXPECTED_DEFECT[(sev, effort)])

    def test_proactive_never_outranks_a_defect(self):
        for sev in sev_mod.ORDER:
            for effort in EFFORT:
                self.assertIn(sev_mod.priority(sev, effort, "proactive"), ("P2", "P3"))

    def test_rejects_unknown_values(self):
        with self.assertRaises(ValueError):
            sev_mod.priority("catastrophic", "low", "found")
        with self.assertRaises(ValueError):
            sev_mod.priority("high", "trivial", "found")
        with self.assertRaises(ValueError):
            sev_mod.priority("high", "low", "maybe")


class TestStatusSemantics(unittest.TestCase):
    def test_risk_may_never_be_critical(self):
        problems = sev_mod.status_violations("critical", "P0", "risk")
        self.assertTrue(problems)
        self.assertFalse(sev_mod.status_violations("high", "P1", "risk"))

    def test_proactive_capped_at_medium_and_p2_p3(self):
        self.assertTrue(sev_mod.status_violations("high", "P2", "proactive"))
        self.assertTrue(sev_mod.status_violations("critical", "P2", "proactive"))
        self.assertFalse(sev_mod.status_violations("medium", "P2", "proactive"))
        self.assertFalse(sev_mod.status_violations("low", "P3", "proactive"))

    def test_found_is_unconstrained(self):
        for sev in sev_mod.ORDER:
            for effort in EFFORT:
                prio = sev_mod.priority(sev, effort, "found")
                self.assertFalse(sev_mod.status_violations(sev, prio, "found"))


class TestDerive(unittest.TestCase):
    @staticmethod
    def finding(blocking, breadth, importance, confidence, effort, status):
        return {
            "id": "F-001",
            "rule_id": "ACC-001",
            "status": status,
            "confidence": confidence,
            "impact": {
                "blocking": blocking,
                "breadth": breadth,
                "content_importance": importance,
            },
            "suggested_action": {"effort": effort},
        }

    def test_fills_both_derived_fields_across_the_whole_table(self):
        filled = 0
        rejected = 0
        for combo in cases():
            f = self.finding(*combo)
            try:
                sev_mod.derive(f)
            except ValueError:
                # A combination the status semantics forbid. Failing loudly is
                # the point: it is an authoring error in the rule, not a report.
                rejected += 1
                continue
            filled += 1
            self.assertIn(f["severity"], sev_mod.ORDER)
            self.assertIn(f["suggested_action"]["priority"], sev_mod.PRIORITIES)
        self.assertEqual(filled + rejected, 324)
        self.assertGreater(rejected, 0, "the status invariants should reject something")

    def test_sort_key_orders_worst_and_cheapest_first(self):
        a = self.finding(True, "site", "primary", "high", "low", "found")
        b = self.finding(False, "page", "secondary", "low", "high", "found")
        b["id"] = "F-002"
        sev_mod.derive(a)
        sev_mod.derive(b)
        self.assertEqual(
            [f["id"] for f in sorted([b, a], key=sev_mod.sort_key)], ["F-001", "F-002"]
        )


if __name__ == "__main__":
    unittest.main()
