"""Step 3: the fixture archetypes, run through the real pipeline end to end.

Each archetype in tests/fixtures/archetypes/ is a small site that stands for a
class of real website, served locally by a server that can also behave the way
real sites do (answer every path with one shell, refuse a named crawler, fail
its robots.txt, answer slowly). The whole audit runs against it exactly as it
would against a live site: collector, promotion, second pass, six diagnostics,
arbitration, report.

What each variant asserts, from its ``archetype.json``:

- ``findings``: every listed finding must be in the report, with the stated
  status, severity, confidence or conditional_on where given. A missing one is a
  false negative.
- ``exact_findings``: no finding outside that list may appear. An unexpected
  finding is a false positive, and every archetype carries legitimate patterns
  placed there to tempt one.
- ``passed``: these rules must be assessed and pass. A rule that returned
  not_assessed where it should have run would otherwise hide a false negative.
- ``not_assessed``: these rules must say they could not run.
- ``evidence``: literal values in the bundle, so a finding is only accepted when
  the observation underneath it is also right.
- ``requests_only``: every path the server was asked for, for the archetypes
  that test robots compliance.

Every variant also requires a schema-valid report in which every rule defined in
the marketplace reaches exactly one outcome.

Variants that need a browser are skipped, with the reason, where none exists.
The allow-list test at the end reuses every bundle these runs produce.
"""

import copy
import http.server
import importlib.util
import json
import pathlib
import re
import sys
import tempfile
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ARCHETYPES = ROOT / "tests" / "fixtures" / "archetypes"
sys.path.insert(0, str(ROOT / "skills" / "audit-orchestrator" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "site-evidence-collector" / "scripts"))

import render  # noqa: E402
import run as pipeline  # noqa: E402
from jsonschema_lite import Validator  # noqa: E402

REGISTRY = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "schemas").glob("*.schema.json")}
REPORT_SCHEMA = Validator(REGISTRY["report.schema.json"], REGISTRY)
EVIDENCE_SCHEMA = Validator(REGISTRY["evidence.schema.json"], REGISTRY)
FIXTURE_ORIGIN = b"http://localhost:8000"
BROWSER = render.find_browser()[0]

# Bundles produced by the runs, reused by the allow-list test: (label, workdir).
BUNDLES = []


def defined_rule_ids():
    specs = list((ROOT / "skills").glob("*/references/rules.md"))
    specs.append(ROOT / "skills" / "audit-orchestrator" / "references" / "proactive.md")
    return sorted(re.findall(r"^### ([A-Z]{3}-\d{3}) ", "".join(p.read_text(encoding="utf-8") for p in specs), re.M))


class ArchetypeServer:
    """Serves one archetype's site/ directory with the behaviour its spec declares."""

    TYPES = {".html": "text/html; charset=utf-8", ".xml": "application/xml", ".txt": "text/plain; charset=utf-8"}

    def __init__(self, name, server_spec):
        self.site = ARCHETYPES / name / "site"
        self.spec = server_spec
        self.requests = []
        archetype = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                agent = self.headers.get("User-Agent", "")
                path = self.path.split("?", 1)[0]
                archetype.requests.append((path, agent))
                status, content_type, body = archetype.respond(path, agent)
                delay = archetype.spec.get("delay_ms")
                if (delay and status == 200 and content_type.startswith("text/html")
                        and archetype.spec.get("delay_agent", "") in agent):
                    time.sleep(delay / 1000.0)
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                for prefix, headers in archetype.spec.get("headers", {}).items():
                    if path.startswith(prefix):
                        for key, value in headers.items():
                            self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def respond(self, path, agent):
        for token, status in self.spec.get("refuse_agents", {}).items():
            if token in agent:
                return status, "text/html; charset=utf-8", b"<html><body><h1>Access denied</h1></body></html>"
        if path in self.spec.get("status", {}):
            return self.spec["status"][path], "text/plain", b"Service Unavailable"
        if self.spec.get("shell"):
            target = self.site / self.spec["shell"]
        else:
            name = "index.html" if path == "/" else path.strip("/")
            target = self.site / name
            if not target.suffix:
                target = self.site / (name + ".html")
        if not target.is_file():
            return 404, "text/html; charset=utf-8", b"<html><body><h1>Not found</h1></body></html>"
        body = target.read_bytes().replace(FIXTURE_ORIGIN, self.base.encode())
        return 200, self.TYPES.get(target.suffix, "application/octet-stream"), body

    def __enter__(self):
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


def dotted(document, path):
    node = document
    for part in path.split("."):
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def run_variant(name, variant):
    spec = json.loads((ARCHETYPES / name / "archetype.json").read_text(encoding="utf-8"))
    workdir = tempfile.mkdtemp(prefix="archetype-%s-" % name)
    server_spec = dict(spec.get("server", {}), **variant.get("server", {}))
    with ArchetypeServer(name, server_spec) as server:
        status = pipeline.run(server.base, workdir, no_render=not variant.get("render", False), no_egress=True)
    report_path = pathlib.Path(workdir) / "report.json"
    evidence_path = pathlib.Path(workdir) / "evidence" / "evidence.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else None
    evidence = json.loads(evidence_path.read_text(encoding="utf-8")) if evidence_path.exists() else None
    return status, report, evidence, server, workdir


class ArchetypeCase(unittest.TestCase):
    maxDiff = None

    def check_variant(self, name, variant_name):
        spec = json.loads((ARCHETYPES / name / "archetype.json").read_text(encoding="utf-8"))
        variant = [v for v in spec["variants"] if v["name"] == variant_name][0]
        if variant.get("render") and not BROWSER:
            self.skipTest("no Chromium-family browser on this machine; the rendered variant needs one")
        status, report, evidence, server, workdir = run_variant(name, variant)
        self.assertEqual(status, 0, "the pipeline failed for %s/%s" % (name, variant_name))
        if variant.get("render") and not evidence["run_context"]["capabilities"]["js_render"]:
            self.skipTest("a browser exists but failed its render probe")
        BUNDLES.append(("%s/%s" % (name, variant_name), workdir))
        self.assertEqual(EVIDENCE_SCHEMA.errors(evidence), [])
        self.assertEqual(REPORT_SCHEMA.errors(report), [])

        outcomes = ([f["rule_id"] for f in report["findings"]] + [n["rule_id"] for n in report["not_assessed"]]
                    + [c["rule_id"] for c in report["checks_passed"]])
        self.assertEqual(sorted(outcomes), defined_rule_ids(), "every rule must reach exactly one outcome")

        by_rule = {}
        for finding in report["findings"]:
            by_rule.setdefault(finding["rule_id"], []).append(finding)
        for expected in variant.get("findings", []):
            rule = expected["rule_id"]
            self.assertIn(rule, by_rule, "false negative: %s did not fire on %s/%s" % (rule, name, variant_name))
            got = by_rule[rule][0]
            for key in ("status", "severity", "confidence"):
                if key in expected:
                    self.assertEqual(got[key], expected[key], "%s %s on %s/%s" % (rule, key, name, variant_name))
            if "breadth" in expected:
                self.assertEqual(got["impact"]["breadth"], expected["breadth"], "%s breadth" % rule)
            if "conditional_on" in expected:
                self.assertEqual(sorted(c["rule_id"] for c in got.get("conditional_on", [])),
                                 sorted(expected["conditional_on"]), "%s conditional_on" % rule)
        if variant.get("exact_findings", True):
            unexpected = sorted(set(by_rule) - {e["rule_id"] for e in variant.get("findings", [])})
            self.assertEqual(unexpected, [], "false positive: unexpected findings on %s/%s: %s" % (
                name, variant_name, [(r, by_rule[r][0]["evidence"][:160]) for r in unexpected]))
        passed = {c["rule_id"] for c in report["checks_passed"]}
        for rule in variant.get("passed", []):
            self.assertIn(rule, passed, "%s should have been assessed and passed on %s/%s" % (rule, name, variant_name))
        not_assessed = {n["rule_id"] for n in report["not_assessed"]}
        for rule in variant.get("not_assessed", []):
            self.assertIn(rule, not_assessed, "%s should be not_assessed on %s/%s" % (rule, name, variant_name))
        for path, value in variant.get("evidence", {}).items():
            self.assertEqual(dotted(evidence, path), value, "evidence %s on %s/%s" % (path, name, variant_name))
        if "requests_only" in variant:
            requested = sorted({p for p, _ in server.requests})
            self.assertEqual(requested, sorted(variant["requests_only"]),
                             "robots compliance: paths requested on %s/%s" % (name, variant_name))
        return report, evidence


def _add_tests():
    for spec_path in sorted(ARCHETYPES.glob("*/archetype.json")):
        name = spec_path.parent.name
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        for variant in spec["variants"]:
            method = "test_%s__%s" % (name.replace("-", "_"), variant["name"].replace("-", "_"))

            def test(self, name=name, variant_name=variant["name"]):
                self.check_variant(name, variant_name)
            test.__doc__ = "%s / %s: %s" % (name, variant["name"], spec["claim"])
            setattr(ArchetypeCase, method, test)


_add_tests()


class _Recorder:
    """Wraps evidence so that every field a script actually reads is logged.

    Paths use the contract's notation: ``pages[].raw.text_len``. Free-form maps
    (``jsonld[].values``, ``robots.ai_agents``) are logged at the map itself, and a
    list of scalars at the list, because that is the granularity allow-lists use.
    """

    FREE_MAPS = ("values", "ai_agents")

    def __init__(self):
        self.read = set()
        self._cache = {}

    def wrap(self, path, value):
        if isinstance(value, (dict, list)):
            key = (id(value), path)
            if key not in self._cache:
                self._cache[key] = (_RDict if isinstance(value, dict) else _RList)(self, path, value)
            return self._cache[key]
        self.log(path)
        return value

    def log(self, path):
        parts = path.split(".")
        for i, part in enumerate(parts):
            if part.rstrip("[]") in self.FREE_MAPS:
                parts = parts[:i + 1]
                parts[-1] = parts[-1].rstrip("[]")
                break
        normalised = ".".join(parts)
        while normalised.endswith("[]"):
            normalised = normalised[:-2]
        self.read.add(normalised)


class _RDict:
    def __init__(self, recorder, path, data):
        self._r, self._path, self._data = recorder, path, data

    def _child(self, key):
        return ("%s.%s" % (self._path, key)) if self._path else key

    def __getitem__(self, key):
        return self._r.wrap(self._child(key), self._data[key])

    def get(self, key, default=None):
        return self[key] if key in self._data else default

    def __contains__(self, key):
        return key in self._data

    def keys(self):
        return self._data.keys()

    def items(self):
        return [(k, self[k]) for k in self._data]

    def values(self):
        return [self[k] for k in self._data]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)


class _RList:
    def __init__(self, recorder, path, data):
        self._r, self._path, self._data = recorder, path + "[]", data

    def __iter__(self):
        return iter([self._r.wrap(self._path, item) for item in self._data])

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self._r.wrap(self._path, item) for item in self._data[index]]
        return self._r.wrap(self._path, self._data[index])

    def __contains__(self, item):
        return any(x == item for x in self)

    def __len__(self):
        return len(self._data)

    def __bool__(self):
        return bool(self._data)


def _allow_list(path):
    text = path.read_text(encoding="utf-8")
    section = re.search(r"^## Evidence this skill may read\s*$(.*?)(?=^## |\Z)", text, re.M | re.S).group(1)
    return {token for line in section.splitlines() if line.strip().startswith("- ")
            for token in re.findall(r"`([^`]+)`", line)}


def _covered(path, allowed):
    return any(path == entry or path.startswith(entry + ".") or path.startswith(entry + "[]") for entry in allowed)


def _load(module_name, path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestScriptsReadOnlyTheirAllowList(unittest.TestCase):
    """The code, not only the rule text, stays inside the declared evidence.

    check.py proves every field a rule block names is in its skill's allow-list.
    This proves the script implementing the block reads nothing else, over real
    bundles from the archetype runs, and that recording the reads does not change
    a single output.
    """

    SKILLS = ("access-and-indexability", "render-and-extraction", "identity-and-markup", "answerability",
              "freshness-and-corroboration", "arrival-and-engagement")

    def bundles(self):
        if not BUNDLES:
            for name, variant in (("healthy-minimal", "no-render"), ("spa-shell", "no-render"),
                                  ("storefront-defects", "no-render"), ("crawler-restricted", "allowlist")):
                spec = json.loads((ARCHETYPES / name / "archetype.json").read_text(encoding="utf-8"))
                chosen = [v for v in spec["variants"] if v["name"] == variant][0]
                BUNDLES.append(("%s/%s" % (name, variant), run_variant(name, chosen)[4]))
        return BUNDLES

    def test_every_field_read_is_declared(self):
        for label, workdir in self.bundles():
            evidence = json.loads((pathlib.Path(workdir) / "evidence" / "evidence.json").read_text(encoding="utf-8"))
            for skill in self.SKILLS:
                module = _load("allowlist_%s" % skill.replace("-", "_"),
                               ROOT / "skills" / skill / "scripts" / "diagnose.py")
                recorder = _Recorder()
                args = (workdir,) if skill == "render-and-extraction" else ()
                recorded = module.diagnose(recorder.wrap("", copy.deepcopy(evidence)), *args)
                plain = module.diagnose(copy.deepcopy(evidence), *args)
                with self.subTest(bundle=label, skill=skill):
                    self.assertEqual(json.dumps(recorded, sort_keys=True), json.dumps(plain, sort_keys=True),
                                     "recording reads must not change the output")
                    allowed = _allow_list(ROOT / "skills" / skill / "references" / "rules.md")
                    undeclared = sorted(p for p in recorder.read if not _covered(p, allowed))
                    self.assertEqual(undeclared, [], "%s read fields outside its allow-list" % skill)
            proactive = _load("allowlist_proactive", ROOT / "skills" / "audit-orchestrator" / "scripts" / "proactive.py")
            recorder = _Recorder()
            proactive.recommend(recorder.wrap("", copy.deepcopy(evidence)))
            with self.subTest(bundle=label, skill="audit-orchestrator proactive"):
                allowed = _allow_list(ROOT / "skills" / "audit-orchestrator" / "references" / "proactive.md")
                self.assertEqual(sorted(p for p in recorder.read if not _covered(p, allowed)), [])


class TestFixturesAreGenerated(unittest.TestCase):
    def test_committed_sites_match_the_generator(self):
        spec = importlib.util.spec_from_file_location("archetype_generate", ARCHETYPES / "generate.py")
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        with tempfile.TemporaryDirectory() as tmp:
            generator.generate(tmp)
            for name in generator.ARCHETYPES:
                committed = _tree(ARCHETYPES / name / "site")
                fresh = _tree(pathlib.Path(tmp) / name / "site")
                self.assertEqual(sorted(committed), sorted(fresh), "%s/site file list differs from generate.py" % name)
                changed = sorted(rel for rel in committed if committed[rel] != fresh[rel])
                self.assertEqual(changed, [], "%s/site content differs from generate.py" % name)


def _tree(root):
    """Relative path to content, line endings normalised so a CRLF checkout compares equal."""
    return {p.relative_to(root).as_posix(): p.read_bytes().replace(b"\r\n", b"\n")
            for p in root.rglob("*") if p.is_file()}


if __name__ == "__main__":
    unittest.main()
