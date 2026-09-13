"""Regenerate samples/: three complete audits of fictional fixture sites.

    python scripts/build_samples.py

Each sample is a real run of the whole marketplace against one of the archetype
sites in tests/fixtures/archetypes/, served locally, so nothing about a real
brand is published. Together they show the capability matrix rather than claim
it:

- storefront-full: browser and network available. The richest report.
- spa-shell-browser: a client-rendered site with a browser, where the empty
  server response is the critical finding and the markup finding beneath it is
  marked conditional.
- spa-shell-no-browser: the same site with neither a browser nor network, where
  the audit still finds the empty server response and says plainly what it could
  not check.

Each sample directory holds report.md, report.json and the evidence bundle the
findings were drawn from. Local ports and timestamps differ between runs; the
findings do not.
"""

import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "skills", "audit-orchestrator", "scripts"))

import run as pipeline  # noqa: E402
from test_archetypes import ArchetypeServer, ARCHETYPES  # noqa: E402

SAMPLES = (
    ("storefront-full", "storefront-defects", {"render": True, "egress": True}),
    ("spa-shell-browser", "spa-shell", {"render": True, "egress": False}),
    ("spa-shell-no-browser", "spa-shell", {"render": False, "egress": False}),
)


def build(out_root):
    for sample, archetype, capability in SAMPLES:
        spec = json.load(open(os.path.join(str(ARCHETYPES), archetype, "archetype.json"), encoding="utf-8"))
        with tempfile.TemporaryDirectory() as work, ArchetypeServer(archetype, spec.get("server", {})) as server:
            status = pipeline.run(server.base, work, no_render=not capability["render"],
                                  no_egress=not capability["egress"])
            if status != 0:
                raise SystemExit("sample %s failed" % sample)
            target = os.path.join(out_root, sample)
            if os.path.isdir(target):
                shutil.rmtree(target)
            os.makedirs(target)
            for name in ("report.md", "report.json"):
                shutil.copy(os.path.join(work, name), os.path.join(target, name))
            shutil.copytree(os.path.join(work, "evidence"), os.path.join(target, "evidence"))
            with open(os.path.join(work, "report.json"), encoding="utf-8") as handle:
                summary = json.load(handle)["summary"]
            print("%-22s %s" % (sample, summary))


if __name__ == "__main__":
    build(os.path.join(ROOT, "samples"))
