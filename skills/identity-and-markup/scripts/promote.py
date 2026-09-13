"""Promote claim candidates to canonical claims. Reads evidence, writes a sidecar.

This is the interpretive half of the split in D9. The collector observes that a
string appeared somewhere; this decides which of those strings the site is
actually asserting about itself, and with how much confidence. Keeping the two
apart is what lets the observation be trusted while the interpretation stays
arguable.

It runs between the collector's two passes, because pass 2 is seeded from what
comes out of here: corroborating "Rs. 799.00" against the open web would be
meaningless, and corroborating a legal name is the whole point.

Why a sidecar rather than writing into the bundle: the collector is the single
writer of ``evidence.json`` (D2), and two writers to one observed-facts file is
the failure this architecture exists to avoid. The contract between skills is a
file, so this writes ``evidence/canonical_claims.json`` and the collector merges
it in pass 2.

No network. Standard library only.
"""

import argparse
import json
import os
import sys

# Kinds worth asking the world about. A price changes weekly and a count on a
# marketing page is unfalsifiable from outside, so neither is promoted: an
# external source disagreeing about either would be noise, not a finding.
CORROBORABLE = ("legal_name", "tagline", "founded_year", "address", "product_name")
MAX_CLAIMS = 12               # pass 2 is bounded by what it is seeded with
REPEATED = 2                  # seen on this many pages, a string is site-wide
GENERIC_WORDS = frozenset({
    "home", "shop", "store", "online", "official", "site", "website", "company",
    "india", "usa", "uk", "group", "limited", "ltd", "inc", "llc", "pvt",
})


def _confidence(candidate):
    """How sure we are the *site* asserts this, before anyone else is asked.

    Structured self-description outranks prose: a name in JSON-LD was put there
    deliberately for machines, while the same string in a heading might be a
    headline. Repetition across pages outranks a single sighting either way.
    """
    structured = candidate["extraction_method"] == "jsonld"
    repeated = candidate["observed_count"] >= REPEATED
    if candidate["kind"] == "founded_year" and not structured:
        # "Founded in 2008" or "since 2024" in prose has no subject the audit
        # can check: the year may be a parent company's, a product line's or a
        # news story's. A foundingDate inside the site's own organization markup
        # is attached to that organization by structure. Only that is asserted;
        # a year from prose alone is never promoted above low (D31).
        return "low"
    if structured and repeated:
        return "high"
    if structured or repeated:
        return "medium"
    return "low"


def _ambiguity(kind, value):
    """How likely this string names something other than this brand.

    Measured on the string alone, because at this point nothing outside the site
    has been consulted. It gates corroboration confidence rather than deciding
    anything by itself: a common single word will collide with unrelated
    entities in any external source, and a match found for it means less than a
    match found for a distinctive multi-word name. D8 is this in one line --
    an ambiguous identity poisons external matching.
    """
    if kind != "legal_name":
        return "low"
    tokens = [t for t in value.split() if t]
    distinctive = [t for t in tokens if t not in GENERIC_WORDS]
    if not distinctive:
        return "high"
    if len(distinctive) == 1 and len(distinctive[0]) <= 5:
        return "high"
    if len(distinctive) == 1:
        return "medium"
    return "low"


def promote(evidence, limit=MAX_CLAIMS):
    """Candidates to claims, deterministically ordered and identified."""
    candidates = [c for c in evidence.get("claim_candidates") or []
                  if c["kind"] in CORROBORABLE]
    grouped = {}
    for candidate in candidates:
        key = (candidate["kind"], candidate["value_normalized"])
        grouped.setdefault(key, []).append(candidate)

    scored = []
    for (kind, value), group in grouped.items():
        best = max(group, key=lambda c: (c["extraction_method"] == "jsonld", c["observed_count"]))
        total = sum(c["observed_count"] for c in group)
        scored.append({
            "kind": kind,
            "value_normalized": value,
            "from_candidates": sorted(c["id"] for c in group),
            "first_party_confidence": _confidence(dict(best, observed_count=total)),
            "entity_ambiguity": _ambiguity(kind, value),
            "_rank": (0 if best["extraction_method"] == "jsonld" else 1, -total, kind, value),
        })

    # A legal name is what every other lookup is anchored on, so it is ranked
    # first regardless of how loudly the site repeats anything else.
    scored.sort(key=lambda c: (c["kind"] != "legal_name", c["_rank"]))
    claims = []
    for index, claim in enumerate(scored[:limit], start=1):
        claim.pop("_rank")
        claims.append(dict(claim, id="C-%03d" % index))
    return [{"id": c["id"], "from_candidates": c["from_candidates"], "kind": c["kind"],
             "value_normalized": c["value_normalized"],
             "first_party_confidence": c["first_party_confidence"],
             "entity_ambiguity": c["entity_ambiguity"]} for c in claims]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Promote claim candidates to canonical claims.")
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    with open(args.evidence, encoding="utf-8") as handle:
        evidence = json.load(handle)
    claims = promote(evidence)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(claims, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
