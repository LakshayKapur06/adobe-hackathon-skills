"""The build gate. One command, twelve checks, no dependencies.

Run it as ``scripts/check.sh``, ``make check``, or ``python scripts/check.py``.

Each check is a function returning a list of failure strings; an empty list is a
pass. Checks are independent, so a run reports everything that is wrong rather
than only the first thing.

The two checks that matter most are neither of the obvious ones. ``rules``
enforces that every rule block carries all fourteen fields from
docs/RULE_FORMAT.md, including its false-positive controls and its legitimate
exceptions, because a rule without those is exactly the rule that produces the
confidently wrong finding this rubric punishes. ``evidence_fields`` resolves
every field path a rule claims to read against the evidence schema, which makes
fabricated evidence a build failure rather than a plausible-looking sentence.

Standard library only.
"""

import argparse
import ast
import json
import os
import re
import http.server
import subprocess
import sys
import tempfile
import threading

# Subprocesses never write bytecode into the tree. A stale __pycache__ entry
# whose source was edited within the same filesystem timestamp tick and kept the
# same byte length is not invalidated, which would let the gate pass against code
# that is no longer on disk. CI must never be able to validate a ghost.
CHILD_ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

# The orchestrator owns schema validation at runtime, so it owns the validator;
# the build gate reuses the same module rather than keeping a second copy.
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "skills", "audit-orchestrator",
                               "scripts"))
from jsonschema_lite import Validator, resolve_field_path  # noqa: E402
import severity as sev_mod  # noqa: E402

SKILLS_DIR = os.path.join(ROOT, "skills")
SCHEMAS_DIR = os.path.join(ROOT, "schemas")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")

ENTRYPOINT = "audit-orchestrator"
COLLECTOR = "site-evidence-collector"
DIAGNOSTICS = (
    "access-and-indexability",
    "render-and-extraction",
    "identity-and-markup",
    "answerability",
    "freshness-and-corroboration",
    "arrival-and-engagement",
)

# The fourteen fields of the canonical rule block, in docs/RULE_FORMAT.md order.
RULE_FIELDS = [
    "Mechanism",
    "Signal",
    "Evidence read",
    "Threshold",
    "Minimum evidence",
    "False-positive controls",
    "Legitimate exceptions",
    "Confidence",
    "Impact inputs",
    "Status",
    "Symptom tags",
    "Remediation",
    "Success criteria",
    "Effort",
]

MAX_RULES_PER_SKILL = 12

# Every diagnostic emits findings, finding.schema.json requires at least one
# evidence_ref, and an evidence_ref carries a layer, a method and a retrieved_at.
# A diagnostic whose allow-list omits their sources cannot construct a valid
# finding at all, so this is a structural requirement rather than a preference.
# schema_version is read by step 1 of every diagnostic's Procedure.
REQUIRED_ALLOW_LIST = (
    "schema_version",
    "pages[].url",
    "pages[].fetched_at",
    "pages[].provenance.layer",
    "pages[].provenance.method",
)

REQUIRED_FRONTMATTER = ("name", "description", "license", "allowed-tools")
REQUIRED_SECTIONS = ("## When to use", "## Inputs", "## Procedure", "## Output")

SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
RULE_ID_RE = re.compile(r"^[A-Z]{3}-[0-9]{3}$")
TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def read_json(path):
    return json.loads(read(path))


def rel(path):
    return os.path.relpath(path, ROOT).replace("\\", "/")


def walk_files(base, suffixes=None):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in sorted(dirnames) if d not in (".git", "__pycache__")]
        for name in sorted(filenames):
            if suffixes and not name.endswith(suffixes):
                continue
            yield os.path.join(dirpath, name)


def parse_frontmatter(text):
    """Parse the YAML frontmatter subset a SKILL.md is allowed to use.

    Top-level ``key: value`` pairs, plus folded scalars introduced by ``>-`` or
    ``|`` whose continuation lines are indented. That is the whole of what the
    agentskills.io format needs, and parsing exactly that keeps the build free
    of a YAML dependency.
    """
    if not text.startswith("---"):
        raise ValueError("no YAML frontmatter: file does not begin with ---")
    end = text.find("\n---", 3)
    if end == -1:
        raise ValueError("unterminated YAML frontmatter")
    body = text[text.find("\n", 3) + 1:end]

    data = {}
    key = None
    for line in body.split("\n"):
        if not line.strip():
            continue
        if line[0] not in " \t" and ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            data[key] = "" if value in (">-", ">", "|", "|-") else value
        elif key is not None:
            data[key] = (data[key] + " " + line.strip()).strip()
        else:
            raise ValueError("frontmatter line is not a key and has no key to continue: %r" % line)
    return data


def parse_rule_blocks(text):
    """Return [(rule_id, name, {field: value})] for every block in a rules.md."""
    blocks = []
    heading = re.compile(r"^###\s+([A-Za-z0-9-]+)\s+[-—]+\s+(.+?)\s*$", re.M)
    matches = list(heading.finditer(text))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end]
        fields = {}
        bullet = re.compile(r"^-\s+\*\*(.+?):\*\*(.*?)(?=^-\s+\*\*|\Z)", re.M | re.S)
        for field in bullet.finditer(body):
            fields[field.group(1).strip()] = field.group(2).strip()
        blocks.append((match.group(1), match.group(2), fields))
    return blocks


def backticked(text):
    return re.findall(r"`([^`]+)`", text)


def schema_registry():
    registry = {}
    for name in ("evidence.schema.json", "finding.schema.json", "report.schema.json"):
        registry[name] = read_json(os.path.join(SCHEMAS_DIR, name))
    return registry


def declared_rule_count(text):
    match = re.search(r"Rules defined:\s*(\d+)\s*of a maximum\s*(\d+)", text)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------

def check_manifest():
    """marketplace.json is well-formed, every path exists, exactly one entrypoint."""
    problems = []
    path = os.path.join(ROOT, "marketplace.json")
    if not os.path.isfile(path):
        return ["marketplace.json is missing from the marketplace root"]
    try:
        manifest = read_json(path)
    except ValueError as exc:
        return ["marketplace.json does not parse: %s" % exc]

    for key in ("name", "version", "skills"):
        if key not in manifest:
            problems.append("marketplace.json has no %r" % key)
    if problems:
        return problems

    entrypoints = [s for s in manifest["skills"] if s.get("entrypoint") is True]
    if len(entrypoints) != 1:
        problems.append(
            "marketplace.json must mark exactly one skill as the entrypoint, found %d"
            % len(entrypoints)
        )
    elif entrypoints[0]["id"] != ENTRYPOINT:
        problems.append(
            "the entrypoint must be %r, found %r" % (ENTRYPOINT, entrypoints[0]["id"])
        )

    listed = []
    for entry in manifest["skills"]:
        sid, spath = entry.get("id"), entry.get("path")
        if not sid or not spath:
            problems.append("a skills[] entry is missing id or path: %r" % (entry,))
            continue
        listed.append(sid)
        if os.path.basename(spath.rstrip("/")) != sid:
            problems.append("skill %r has path %r; the folder name must equal the id" % (sid, spath))
        folder = os.path.join(ROOT, spath)
        if not os.path.isdir(folder):
            problems.append("skill %r: path %s does not exist" % (sid, spath))
        elif not os.path.isfile(os.path.join(folder, "SKILL.md")):
            problems.append("skill %r: %s/SKILL.md does not exist" % (sid, spath))

    if len(set(listed)) != len(listed):
        problems.append("marketplace.json lists a duplicate skill id")

    expected = {ENTRYPOINT, COLLECTOR, *DIAGNOSTICS}
    if set(listed) != expected:
        missing = sorted(expected - set(listed))
        extra = sorted(set(listed) - expected)
        if missing:
            problems.append("marketplace.json is missing skills: %s" % ", ".join(missing))
        if extra:
            problems.append(
                "marketplace.json lists skills not in the frozen roster: %s" % ", ".join(extra)
            )

    on_disk = {d for d in os.listdir(SKILLS_DIR) if os.path.isdir(os.path.join(SKILLS_DIR, d))}
    for orphan in sorted(on_disk - set(listed)):
        problems.append("skills/%s exists on disk but is not listed in marketplace.json" % orphan)

    return problems


def check_skills():
    """Every skill folder independently satisfies the agentskills.io format."""
    problems = []
    for sid in sorted(os.listdir(SKILLS_DIR)):
        folder = os.path.join(SKILLS_DIR, sid)
        if not os.path.isdir(folder):
            continue
        skill_md = os.path.join(folder, "SKILL.md")
        if not os.path.isfile(skill_md):
            problems.append("skills/%s has no SKILL.md" % sid)
            continue
        text = read(skill_md)
        try:
            fm = parse_frontmatter(text)
        except ValueError as exc:
            problems.append("skills/%s/SKILL.md: %s" % (sid, exc))
            continue

        for key in REQUIRED_FRONTMATTER:
            if not fm.get(key):
                problems.append("skills/%s/SKILL.md: frontmatter %r is missing or empty" % (sid, key))

        name = fm.get("name", "")
        if name and not SKILL_NAME_RE.match(name):
            problems.append(
                "skills/%s/SKILL.md: name %r must be lowercase alphanumerics separated by hyphens"
                % (sid, name)
            )
        if name and name != sid:
            problems.append(
                "skills/%s/SKILL.md: name %r must equal the folder name" % (sid, name)
            )
        if len(name) > 64:
            problems.append("skills/%s/SKILL.md: name is longer than 64 characters" % sid)
        description = fm.get("description", "")
        if len(description) > 1024:
            problems.append(
                "skills/%s/SKILL.md: description is %d characters, over the 1024 limit"
                % (sid, len(description))
            )

        for section in REQUIRED_SECTIONS:
            if section not in text:
                problems.append("skills/%s/SKILL.md: missing section %r" % (sid, section))

    if os.path.isdir(SKILLS_DIR):
        exe = None
        for candidate in ("skills-ref", "skills-ref.cmd", "skills-ref.exe"):
            for directory in os.environ.get("PATH", "").split(os.pathsep):
                if directory and os.path.isfile(os.path.join(directory, candidate)):
                    exe = os.path.join(directory, candidate)
                    break
            if exe:
                break
        if exe:
            for sid in sorted(os.listdir(SKILLS_DIR)):
                folder = os.path.join(SKILLS_DIR, sid)
                if not os.path.isdir(folder):
                    continue
                run = subprocess.run([exe, "validate", folder], capture_output=True,
                                     text=True, env=CHILD_ENV)
                if run.returncode != 0:
                    problems.append(
                        "skills-ref validate skills/%s failed: %s"
                        % (sid, (run.stdout + run.stderr).strip()[:400])
                    )
    return problems


def check_references():
    """Every repository path a SKILL.md points at actually exists.

    Scoped to the three prefixes that name files in this repository, so that
    runtime artefacts such as ``evidence/evidence.json`` and
    ``findings/<skill>.json`` are not mistaken for missing files.
    """
    problems = []
    prefixes = ("references/", "scripts/", "../../schemas/", "docs/")
    for sid in sorted(os.listdir(SKILLS_DIR)):
        folder = os.path.join(SKILLS_DIR, sid)
        if not os.path.isdir(folder):
            continue
        for path in walk_files(folder, (".md",)):
            for token in backticked(read(path)):
                # A command in backticks names its script first: that word is the path.
                words = token.split()
                token = words[0] if words else ""
                if not token.startswith(prefixes):
                    continue
                base = ROOT if token.startswith("docs/") else folder
                if not os.path.exists(os.path.join(base, token)):
                    problems.append("%s references %s, which does not exist" % (rel(path), token))
    return problems


def check_schemas():
    """The schemas are well-formed, and they accept and reject what they must."""
    problems = []
    registry = schema_registry()
    validators = {}
    for name, schema in registry.items():
        try:
            validators[name] = Validator(schema, registry)
        except Exception as exc:
            problems.append("schemas/%s is not usable: %s" % (name, exc))
    if problems:
        return problems

    evidence_path = os.path.join(FIXTURES, "evidence", "minimal.evidence.json")
    errors = validators["evidence.schema.json"].errors(read_json(evidence_path))
    problems += ["%s: %s" % (rel(evidence_path), e) for e in errors]

    report = assemble_fixture_report()
    problems += ["assembled report: %s" % e for e in validators["report.schema.json"].errors(report)]

    for kind, folder in (("valid", "valid"), ("invalid", "invalid")):
        base = os.path.join(FIXTURES, "schema", folder)
        if not os.path.isdir(base):
            continue
        for path in sorted(os.listdir(base)):
            if not path.endswith(".json"):
                continue
            target = path.split("__", 1)[0] + ".schema.json"
            if target not in validators:
                problems.append(
                    "%s: filename must start with a schema name followed by __" % rel(os.path.join(base, path))
                )
                continue
            errors = validators[target].errors(read_json(os.path.join(base, path)))
            if kind == "valid" and errors:
                problems.append(
                    "%s should validate but does not: %s" % (rel(os.path.join(base, path)), errors[0])
                )
            if kind == "invalid" and not errors:
                problems.append(
                    "%s should be rejected by %s and was accepted; the schema is not "
                    "enforcing what its filename claims" % (rel(os.path.join(base, path)), target)
                )
    return problems


def check_rules():
    """Every rule block carries all fourteen fields, non-empty, within budget."""
    problems = []
    seen_ids = {}
    for sid in DIAGNOSTICS:
        path = os.path.join(SKILLS_DIR, sid, "references", "rules.md")
        if not os.path.isfile(path):
            problems.append("skills/%s has no references/rules.md" % sid)
            continue
        text = read(path)
        blocks = parse_rule_blocks(text)

        declared, maximum = declared_rule_count(text)
        if declared is None:
            problems.append(
                "%s: no 'Rules defined: N of a maximum M' line, so the budget is unverifiable"
                % rel(path)
            )
        else:
            if declared != len(blocks):
                problems.append(
                    "%s declares %d rules but contains %d blocks" % (rel(path), declared, len(blocks))
                )
            if maximum != MAX_RULES_PER_SKILL:
                problems.append(
                    "%s declares a maximum of %d; the budget is %d per diagnostic skill"
                    % (rel(path), maximum, MAX_RULES_PER_SKILL)
                )
        if len(blocks) > MAX_RULES_PER_SKILL:
            problems.append(
                "%s has %d rules, over the budget of %d. Cut or merge one."
                % (rel(path), len(blocks), MAX_RULES_PER_SKILL)
            )

        for rule_id, name, fields in blocks:
            where = "%s %s" % (rel(path), rule_id)
            if not RULE_ID_RE.match(rule_id):
                problems.append("%s: rule id must match AAA-000" % where)
            if rule_id in seen_ids:
                problems.append("%s: rule id already used in %s" % (where, seen_ids[rule_id]))
            seen_ids[rule_id] = rel(path)
            if not name.strip():
                problems.append("%s: rule has no one-line name" % where)
            for field in RULE_FIELDS:
                if field not in fields:
                    problems.append("%s: missing field '%s'" % (where, field))
                elif not fields[field].strip():
                    problems.append("%s: field '%s' is present but empty" % (where, field))
    return problems


def check_evidence_fields():
    """Every field path a rule claims to read exists in the evidence schema.

    This is the anti-hallucination guard. Both directions are enforced: a rule
    may not name a field the collector never produces, and it may not read
    outside the allow-list its own skill declares.
    """
    problems = []
    registry = schema_registry()
    evidence = registry["evidence.schema.json"]

    for sid in DIAGNOSTICS:
        path = os.path.join(SKILLS_DIR, sid, "references", "rules.md")
        if not os.path.isfile(path):
            continue
        text = read(path)

        allow = set()
        section = re.search(
            r"^## Evidence this skill may read\s*$(.*?)(?=^## |\Z)", text, re.M | re.S
        )
        if not section:
            problems.append(
                "%s has no '## Evidence this skill may read' section, so its reads are ungoverned"
                % rel(path)
            )
        else:
            for line in section.group(1).splitlines():
                line = line.strip()
                if line.startswith("- "):
                    for token in backticked(line):
                        allow.add(token.strip())
            for field_path in sorted(allow):
                try:
                    resolve_field_path(evidence, field_path, registry)
                except KeyError as exc:
                    problems.append(
                        "%s allow-list: %s -> %s" % (rel(path), field_path, exc.args[0])
                    )
            for field_path in REQUIRED_ALLOW_LIST:
                if field_path not in allow:
                    problems.append(
                        "%s allow-list omits %s, so this skill cannot build a valid "
                        "evidence_ref or check the bundle version" % (rel(path), field_path)
                    )

        for rule_id, _name, fields in parse_rule_blocks(text):
            for field_path in backticked(fields.get("Evidence read", "")):
                field_path = field_path.strip()
                try:
                    resolve_field_path(evidence, field_path, registry)
                except KeyError as exc:
                    problems.append(
                        "%s %s Evidence read: %s -> %s"
                        % (rel(path), rule_id, field_path, exc.args[0])
                    )
                    continue
                if allow and field_path not in allow:
                    problems.append(
                        "%s %s reads %s, which is not in this skill's declared allow-list"
                        % (rel(path), rule_id, field_path)
                    )
    return problems


def finding_invariant_problems(finding, where):
    """Invariants the schema deliberately does not encode.

    ``false_positive_controls_applied`` and ``exceptions_checked`` are required
    non-empty for an observed defect and optional otherwise. Encoding that in
    the schema would mean forcing every proactive recommendation to write "n/a"
    in two arrays, which is filler that reads as diligence and is not. Encoding
    it here keeps the requirement real exactly where it matters: a rule that
    fires on a live site and names no false-positive control is the rule that
    produces the confidently wrong finding.
    """
    problems = []
    status = finding.get("status")
    fid = finding.get("id", "<no id>")
    rule = finding.get("rule_id", "<no rule>")
    if status == "found":
        for field in ("false_positive_controls_applied", "exceptions_checked"):
            if not finding.get(field):
                problems.append(
                    "%s finding %s (rule %s) has status 'found' and an empty %s; an observed "
                    "defect must state what it ruled out before firing" % (where, fid, rule, field)
                )
    sev, prio = finding.get("severity"), finding.get("suggested_action", {}).get("priority")
    if sev and prio and status:
        for violation in sev_mod.status_violations(sev, prio, status):
            problems.append("%s finding %s (rule %s): %s" % (where, fid, rule, violation))
    return problems


def check_finding_invariants():
    """Findings satisfy the rules the schema cannot express."""
    problems = []
    findings_dir = os.path.join(FIXTURES, "findings")
    if os.path.isdir(findings_dir):
        for name in sorted(os.listdir(findings_dir)):
            if not name.endswith(".json"):
                continue
            doc = read_json(os.path.join(findings_dir, name))
            for finding in doc.get("findings", []):
                problems += finding_invariant_problems(finding, "tests/fixtures/findings/" + name)
    for finding in assemble_fixture_report().get("findings", []):
        problems += finding_invariant_problems(finding, "assembled report")
    return problems


def check_no_placeholders():
    """No unfinished work markers on any graded surface."""
    # Assembled from parts so that this check does not trip over its own source.
    tokens = ["TO" + "DO", "FIX" + "ME", "stu" + "b", "place" + "holder", "XX" + "X"]
    pattern = re.compile(r"\b(%s)\b" % "|".join(tokens), re.I)
    problems = []
    targets = [os.path.join(ROOT, d) for d in ("skills", "scripts", "tests", "schemas")]
    targets.append(os.path.join(ROOT, "marketplace.json"))
    for target in targets:
        paths = [target] if os.path.isfile(target) else list(walk_files(target))
        for path in paths:
            if os.path.abspath(path) == os.path.abspath(__file__):
                continue
            if path.endswith((".png", ".jpg", ".zip", ".pyc")):
                continue
            for number, line in enumerate(read(path).splitlines(), start=1):
                found = pattern.search(line)
                if found:
                    problems.append(
                        "%s:%d contains %r" % (rel(path), number, found.group(0))
                    )
    return problems


def assemble_fixture_report(out_path=None):
    """Run the orchestrator's assembly over the fixtures and return the report."""
    script = os.path.join(SKILLS_DIR, ENTRYPOINT, "scripts", "assemble_report.py")
    handle = out_path
    if handle is None:
        fd, handle = tempfile.mkstemp(suffix=".json")
        os.close(fd)
    run = subprocess.run(
        [sys.executable, script,
         "--evidence", os.path.join(FIXTURES, "evidence", "minimal.evidence.json"),
         "--findings", os.path.join(FIXTURES, "findings"),
         "--out", handle],
        capture_output=True, text=True, env=CHILD_ENV,
    )
    if run.returncode != 0:
        raise RuntimeError("assemble_report.py failed: %s" % (run.stdout + run.stderr).strip())
    return read_json(handle)


TIMING_RE = re.compile(r'"(ttfb_ms|fetch_ms|render_ms|elapsed_s)": [0-9.]+')
LOCAL_ORIGIN_RE = re.compile(r"http://127\.0\.0\.1:\d+")


def _normalised(text):
    """Blank out what legitimately varies between runs: clock readings and the local port."""
    text = TIMESTAMP_RE.sub("<timestamp>", text)
    text = TIMING_RE.sub(r'"\1": "<ms>"', text)
    return LOCAL_ORIGIN_RE.sub("<origin>", text)


class _FixtureSite:
    """tests/fixtures/site served on a local port, with its fixed localhost:8000 origin rewritten."""

    def __enter__(self):
        root = os.path.join(FIXTURES, "site")
        site = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                name = self.path.split("?", 1)[0].lstrip("/") or "index.html"
                target = os.path.normpath(os.path.join(root, name))
                if target.startswith(root) and os.path.isfile(target):
                    with open(target, "rb") as handle:
                        body = handle.read().replace(b"http://localhost:8000", site.base.encode())
                    kind = {"txt": "text/plain", "xml": "application/xml"}.get(name.rsplit(".", 1)[-1], "text/html")
                    self.send_response(200)
                else:
                    body, kind = b"<html><body>Not found</body></html>", "text/html"
                    self.send_response(404)
                self.send_header("Content-Type", kind)
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


def check_determinism():
    """The same fixture twice gives identical output, apart from clock readings.

    Two pipelines are checked: report assembly over the fixture bundle, and the
    real collector over the fixture site served locally, with rendering and
    egress off so that nothing outside this machine can vary the result.
    Timestamps, millisecond timings and the local port are the only values
    allowed to differ.
    """
    problems = []
    outputs = []
    with tempfile.TemporaryDirectory() as tmp:
        for run_index in range(2):
            path = os.path.join(tmp, "report-%d.json" % run_index)
            try:
                assemble_fixture_report(path)
            except RuntimeError as exc:
                return [str(exc)]
            outputs.append(_normalised(read(path)))
    if outputs[0] != outputs[1]:
        problems.append(
            "two report assemblies over the same fixture differ; "
            "something depends on ordering, the clock or iteration order"
        )

    collector = os.path.join(SKILLS_DIR, COLLECTOR, "scripts", "collect.py")
    bundles = []
    with _FixtureSite() as site, tempfile.TemporaryDirectory() as tmp:
        for run_index in range(2):
            workdir = os.path.join(tmp, "run-%d" % run_index)
            run = subprocess.run(
                [sys.executable, collector, "--url", site.base, "--workdir", workdir,
                 "--no-render", "--no-egress"],
                capture_output=True, text=True, env=CHILD_ENV, timeout=180,
            )
            if run.returncode != 0:
                return problems + ["the collector failed on the fixture site: %s"
                                   % (run.stdout + run.stderr).strip()[-1500:]]
            bundles.append(_normalised(read(os.path.join(workdir, "evidence", "evidence.json"))))
    if bundles[0] != bundles[1]:
        problems.append(
            "two collector runs over the fixture site produced different evidence "
            "beyond clock readings; something depends on ordering or iteration order"
        )
    return problems


def check_stdlib_only():
    """Every skill imports only the standard library and its own modules.

    Parsing and detection are stdlib-only so that the same site yields the same
    evidence on every machine: a third-party parser is a different parser, and
    a different parser is different evidence. A skill may import its own sibling
    scripts, and nothing from another skill.
    """
    problems = []
    for sid in sorted(os.listdir(SKILLS_DIR)):
        folder = os.path.join(SKILLS_DIR, sid)
        if not os.path.isdir(folder):
            continue
        own = {os.path.splitext(os.path.basename(p))[0] for p in walk_files(folder, (".py",))}
        for path in walk_files(folder, (".py",)):
            try:
                tree = ast.parse(read(path), filename=path)
            except SyntaxError as exc:
                problems.append("%s does not parse: %s" % (rel(path), exc))
                continue
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        continue
                    modules = [node.module or ""]
                for module in modules:
                    top = module.split(".")[0]
                    if top and top not in sys.stdlib_module_names and top not in own:
                        problems.append(
                            "%s imports %r, which is neither the standard library nor a "
                            "module of this skill" % (rel(path), module)
                        )
    return problems


def check_isolation():
    """No skill folder depends on another skill folder.

    The orchestrator is exempt: it composes the others and may name their paths.
    Every other skill must stay independently valid if lifted out on its own.
    """
    problems = []
    names = [ENTRYPOINT, COLLECTOR, *DIAGNOSTICS]
    for sid in sorted(os.listdir(SKILLS_DIR)):
        folder = os.path.join(SKILLS_DIR, sid)
        if not os.path.isdir(folder) or sid == ENTRYPOINT:
            continue
        for path in walk_files(folder, (".md", ".py")):
            text = read(path)
            for other in names:
                if other == sid:
                    continue
                if "skills/%s/" % other in text:
                    problems.append(
                        "%s references skills/%s/, breaking skill isolation" % (rel(path), other)
                    )
    return problems


def check_unit_tests():
    """The unit test suite passes."""
    run = subprocess.run(
        [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
        cwd=ROOT, capture_output=True, text=True, env=CHILD_ENV,
    )
    if run.returncode != 0:
        return [(run.stdout + run.stderr).strip()[-3000:]]
    tail = (run.stderr or run.stdout).strip().splitlines()
    return [] if tail else ["unittest produced no output, which means it ran nothing"]


CHECKS = [
    ("manifest", "marketplace.json shape, paths and single entrypoint", check_manifest),
    ("skills", "agentskills.io validity of every skill folder", check_skills),
    ("references", "every repository path a SKILL.md points at exists", check_references),
    ("schemas", "schema conformance, and the vectors they must reject", check_schemas),
    ("rules", "rule-block completeness and rule budget", check_rules),
    ("evidence-fields", "every field a rule reads exists in the evidence schema",
     check_evidence_fields),
    ("finding-invariants", "rules the finding schema deliberately cannot express",
     check_finding_invariants),
    ("no-placeholders", "no unfinished-work markers on a graded surface", check_no_placeholders),
    ("determinism", "same fixture twice, report and collector, identical but for clocks",
     check_determinism),
    ("stdlib-only", "every skill imports only the standard library", check_stdlib_only),
    ("isolation", "no cross-skill dependencies", check_isolation),
    ("unit", "unit tests, including the 324-case severity truth table", check_unit_tests),
]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the agent-readiness-audit build gate.")
    parser.add_argument("--only", action="append", default=None,
                        help="run only the named check; repeatable")
    parser.add_argument("--list", action="store_true", help="list the checks and exit")
    args = parser.parse_args(argv)

    if args.list:
        for name, description, _ in CHECKS:
            print("%-16s %s" % (name, description))
        return 0

    selected = [c for c in CHECKS if args.only is None or c[0] in args.only]
    if args.only:
        unknown = set(args.only) - {c[0] for c in CHECKS}
        if unknown:
            print("unknown check(s): %s" % ", ".join(sorted(unknown)))
            return 2

    width = max(len(name) for name, _, _ in selected)
    failures = 0
    print("agent-readiness-audit :: build gate")
    print("-" * 72)
    for name, description, func in selected:
        try:
            problems = func()
        except Exception as exc:  # a check that crashes is a failing check
            problems = ["check raised %s: %s" % (type(exc).__name__, exc)]
        status = "PASS" if not problems else "FAIL"
        print("%-4s  %-*s  %s" % (status, width, name, description))
        for problem in problems:
            failures += 1
            for line in str(problem).splitlines():
                print("        %s" % line)
    print("-" * 72)
    if failures:
        print("FAILED: %d problem(s) across %d check(s)" % (failures, len(selected)))
        return 1
    print("OK: %d checks passed" % len(selected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
