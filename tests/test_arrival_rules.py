"""arrival-and-engagement: ARR-001's latency risk, the samples it must not judge,
and its not-assessed path. Every emitted finding is derived and validated."""

import copy
import importlib.util
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "audit-orchestrator" / "scripts"))

import severity as sev_mod  # noqa: E402
from jsonschema_lite import Validator  # noqa: E402

# Loaded by path under a unique name: every diagnostic's script is called
# diagnose.py, and one test process imports several of them.
_spec = importlib.util.spec_from_file_location(
    "arrival_diagnose", ROOT / "skills" / "arrival-and-engagement" / "scripts" / "diagnose.py")
diagnose = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(diagnose)

BASE = json.loads((ROOT / "tests" / "fixtures" / "evidence" / "minimal.evidence.json").read_text(encoding="utf-8"))
SCHEMAS = {name: json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
           for name in ("evidence.schema.json", "finding.schema.json", "report.schema.json")}


def page(path, ttfb, status=200, connect=None):
    p = copy.deepcopy(BASE["pages"][1])
    url = "http://localhost:8000" + path
    p.update({"url": url, "final_url": url, "status": status})
    p["timing"] = {"ttfb_ms": ttfb, "connect_ms": connect,
                   "fetch_ms": ttfb + 50 if ttfb is not None else None, "render_ms": None}
    return p


class TestARR001(unittest.TestCase):
    def outcome(self, pages):
        e = copy.deepcopy(BASE)
        e["pages"] = pages
        self.assertFalse(Validator(SCHEMAS["evidence.schema.json"], SCHEMAS).errors(e))
        result = diagnose.diagnose(e)
        for f in result["findings"]:
            derived = sev_mod.derive(copy.deepcopy(f))
            self.assertFalse(Validator(SCHEMAS["finding.schema.json"], SCHEMAS).errors(derived))
            self.assertEqual((derived["severity"], derived["category"]), ("medium", "engagement"))
        if result["findings"]:
            return "fired", result["findings"][0]
        if result["not_assessed"]:
            return "not_assessed", None
        return "passed", None

    def test_slow_site_is_a_low_confidence_risk(self):
        got, f = self.outcome([page("/p%d" % i, 2200 + i * 10) for i in range(6)])
        self.assertEqual((got, f["status"], f["confidence"]), ("fired", "risk", "low"))
        self.assertIn("minus DNS, TCP and TLS setup", f["evidence"])

    def test_a_client_network_stall_is_not_a_slow_server(self):
        # G2 live run: every page took about 10.2 s, almost all of it before the
        # server could answer, and minutes later the same site answered in 60 ms.
        pages = [page("/p%d" % i, 10219 + i, connect=10100) for i in range(6)]
        self.assertEqual(self.outcome(pages)[0], "passed")

    def test_one_slow_page_does_not_move_the_median(self):
        self.assertEqual(self.outcome([page("/p%d" % i, 300) for i in range(5)] + [page("/slow", 9000)])[0],
                         "passed")

    def test_refused_pages_are_not_timed(self):
        pages = [page("/p%d" % i, 300) for i in range(3)] + [page("/r%d" % i, 5000, status=403) for i in range(4)]
        self.assertEqual(self.outcome(pages)[0], "not_assessed")

    def test_small_sample_is_not_assessed(self):
        self.assertEqual(self.outcome([page("/p%d" % i, 4000) for i in range(4)])[0], "not_assessed")


if __name__ == "__main__":
    unittest.main()
