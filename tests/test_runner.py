"""The command-line runner, end to end against the fixture site served locally."""

import http.server
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "audit-orchestrator" / "scripts"))

from jsonschema_lite import Validator  # noqa: E402

RUNNER = ROOT / "scripts" / "run_audit.py"
SITE = ROOT / "tests" / "fixtures" / "site"
REGISTRY = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "schemas").glob("*.schema.json")}


class FixtureSite:
    def __enter__(self):
        site = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                name = self.path.split("?", 1)[0].lstrip("/") or "index.html"
                target = SITE / name
                if target.is_file():
                    body = target.read_bytes().replace(b"http://localhost:8000", site.base.encode())
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain" if name.endswith(".txt") else
                                     "application/xml" if name.endswith(".xml") else "text/html")
                else:
                    body = b"<html><body>Not found</body></html>"
                    self.send_response(404)
                    self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = "http://127.0.0.1:%d" % self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


def run_audit(*flags):
    with FixtureSite() as site, tempfile.TemporaryDirectory() as out:
        result = subprocess.run([sys.executable, "-B", str(RUNNER), "--url", site.base, "--out", out,
                                 "--no-render", "--no-egress", *flags],
                                capture_output=True, text=True, encoding="utf-8", timeout=180)
        report = pathlib.Path(out) / "report.json"
        evidence = pathlib.Path(out) / "evidence" / "evidence.json"
        return (result, json.loads(report.read_text(encoding="utf-8")) if report.exists() else None,
                json.loads(evidence.read_text(encoding="utf-8")) if evidence.exists() else None)


class TestRunner(unittest.TestCase):
    def test_full_run_writes_valid_evidence_and_report(self):
        result, report, evidence = run_audit("--summary")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Validator(REGISTRY["evidence.schema.json"], REGISTRY).errors(evidence), [])
        self.assertEqual(Validator(REGISTRY["report.schema.json"], REGISTRY).errors(report), [])
        # The fixture is a clean site: no defect and no risk. The orchestrator's
        # proactive recommendations may still appear, and nothing else may.
        self.assertEqual([f["rule_id"] for f in report["findings"] if f["status"] != "proactive"], [])
        # Every diagnostic now has rules, so no skill may be reported as
        # unevaluated, and every rule defined in any references/rules.md must
        # reach the report as exactly one outcome: a finding, a pass, or a
        # not-assessed entry. A rule that silently produced nothing would read
        # as a clean result for a check that never ran.
        self.assertNotIn("diagnosis", [d["what"] for d in report["run_context"]["degradations"]])
        specs = list((ROOT / "skills").glob("*/references/rules.md"))
        specs.append(ROOT / "skills" / "audit-orchestrator" / "references" / "proactive.md")
        defined = sorted(re.findall(r"^### ([A-Z]{3}-\d{3}) ", "".join(
            p.read_text(encoding="utf-8") for p in specs), re.M))
        outcomes = ([f["rule_id"] for f in report["findings"]] + [n["rule_id"] for n in report["not_assessed"]]
                    + [c["rule_id"] for c in report["checks_passed"]])
        self.assertEqual(sorted(outcomes), defined)

    def test_summary_line_and_table(self):
        result, _, evidence = run_audit("--summary")
        first = result.stdout.splitlines()[0]
        self.assertIn("%d/%d pages fetched/discovered" % (evidence["crawl"]["fetched"],
                                                          evidence["crawl"]["discovered"]), first)
        self.assertIn("js_render=no", first)
        self.assertIn("url  ", result.stdout)
        self.assertIn("page_type", result.stdout)
        self.assertIn("/about.html", result.stdout)

    def test_collect_only_stops_before_the_report(self):
        result, report, evidence = run_audit("--collect-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(report)
        self.assertIsNotNone(evidence)


if __name__ == "__main__":
    unittest.main()


class TestDiagnoseAnExistingBundle(unittest.TestCase):
    """The entrypoint can diagnose a bundle instead of observing a site.

    A host whose sandbox cannot reach the network, or an agent that already has a
    bundle from an earlier run, still gets the whole pipeline after observation:
    diagnosis, arbitration, derived severity, and both report files.
    """

    def test_a_bundle_alone_produces_the_whole_report(self):
        import shutil
        import run as run_mod
        with tempfile.TemporaryDirectory() as work:
            shutil.copytree(str(ROOT / "tests" / "fixtures" / "evidence"), str(pathlib.Path(work) / "evidence"))
            bundle = str(pathlib.Path(work) / "evidence" / "evidence.json")
            shutil.move(str(pathlib.Path(work) / "evidence" / "minimal.evidence.json"), bundle)
            self.assertEqual(run_mod.main(["--evidence", bundle]), 0)
            report = json.loads((pathlib.Path(work) / "report.json").read_text(encoding="utf-8"))
            self.assertFalse(Validator(REGISTRY["report.schema.json"], REGISTRY).errors(report))
            self.assertTrue((pathlib.Path(work) / "report.md").is_file())
            outcomes = {x["rule_id"] for key in ("findings", "not_assessed", "checks_passed") for x in report[key]}
            self.assertEqual(len(outcomes), 24, "every rule still reaches an outcome")

    def test_url_and_evidence_are_mutually_exclusive(self):
        import run as run_mod
        for argv in ([], ["--url", "https://example.com", "--evidence", "x.json"]):
            with self.assertRaises(SystemExit):
                run_mod.main(argv)
