"""Claim candidates: strings the site asserts about itself, with provenance.

This module extracts *candidates*, never claims. The distinction is D9 and W5 in
``docs/DECISIONS.md`` and it is the reason the collector and the identity skill
are separate: deciding that "Built to Fly" is a brand's tagline rather than a
headline is interpretation, and interpretation belongs to a diagnostic that can
be argued with. What happens here is observation — a string appeared at this
URL, at this locator, by this method, this many times — and nothing else.

So the bar for candidacy is deliberately low and the extraction deliberately
mechanical. A candidate that turns out to be noise costs one row that identity
declines to promote. A missed candidate costs a claim that corroboration can
never check, because pass 2 is seeded from the promoted set.

Everything here is deterministic: the same bundle twice produces the same rows
in the same order with the same ids, which CLAUDE.md rule 10 requires.

Standard library only.
"""

import re

MAX_VALUE_CHARS = 200
MAX_CANDIDATES = 200          # bundles stay bounded; overflow is logged, never silent

# schema.org types that decide what a bare "name" means.
ORG_TYPES = frozenset({
    "Organization", "Corporation", "LocalBusiness", "OnlineStore", "Store", "Brand",
    "NewsMediaOrganization", "EducationalOrganization", "NGO", "GovernmentOrganization",
    "Restaurant", "Hotel", "SportsOrganization", "MedicalOrganization",
})
PRODUCT_TYPES = frozenset({"Product", "ProductGroup", "IndividualProduct", "Vehicle"})
ADDRESS_PARTS = ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry")

# Visible-text patterns. Each is anchored on a word that makes the number a
# claim rather than a coincidence: a bare "1998" on a page means nothing, and
# "founded in 1998" means something.
_YEAR = re.compile(r"\b(?:since|established|est\.|founded(?:\s+in)?|serving\s+since)\s+"
                   r"((?:1[89]|20)\d{2})\b", re.I)
_PRICE = re.compile(r"(?:₹|Rs\.?|INR|US\$|\$|USD|€|EUR|£|GBP|¥|JPY)\s?"
                    r"\d[\d,]*(?:\.\d{1,2})?\b")
_COUNT = re.compile(r"\b\d[\d,]*(?:\.\d+)?\s*(?:\+|plus|million|billion|k|lakh|crore)?\s+"
                    r"(?:customers|users|clients|downloads|installs|products|items|stores|outlets|"
                    r"branches|countries|cities|projects|reviews|ratings|members|partners|"
                    r"employees|years\s+of\s+experience)\b", re.I)
_YEAR_IN = re.compile(r"((?:1[89]|20)\d{2})")
_SPACE = re.compile(r"\s+")


def normalise(value):
    """Casefold, collapse whitespace, drop surrounding punctuation.

    Comparison is done on this, so two pages writing "Built to Fly" and
    "built to fly." are one candidate observed twice rather than two.
    """
    return _SPACE.sub(" ", value).strip().strip(".,;:!–—-–— ").casefold()


def _add(out, kind, raw, url, locator, method):
    raw = _SPACE.sub(" ", raw).strip()
    if not raw or len(raw) > MAX_VALUE_CHARS:
        return
    value = normalise(raw)
    if not value:
        return
    out.append({"kind": kind, "value_raw": raw, "value_normalized": value,
                "source_url": url, "locator": locator, "extraction_method": method})


def from_jsonld(entries, url, out):
    """Structured self-description: the least interpretive source available.

    ``jsonld[].values`` is already a flat dotted-path map, so nothing is
    re-parsed here. The entry's own declared type decides what a bare ``name``
    means, because Product.name and Organization.name are different claims.
    """
    for entry in entries:
        declared = entry.get("type") or ""
        values = entry.get("values") or {}
        address = []
        for path, value in sorted(values.items()):
            leaf = path.rsplit(".", 1)[-1]
            if leaf == "legalName":
                _add(out, "legal_name", value, url, path, "jsonld")
            elif path == "brand.name":
                # A Product's brand is an organisation, not the product. Read as
                # a product name it turns every item in a catalogue into a claim
                # that the company is called after itself.
                _add(out, "legal_name", value, url, path, "jsonld")
            elif path == "name":
                # Top-level only. A nested name belongs to a nested entity --
                # brand.name, author.name, seller.name -- and the declared type
                # of the outer entry says nothing about any of them.
                if declared in ORG_TYPES:
                    _add(out, "legal_name", value, url, path, "jsonld")
                elif declared in PRODUCT_TYPES:
                    _add(out, "product_name", value, url, path, "jsonld")
            elif leaf == "slogan":
                _add(out, "tagline", value, url, path, "jsonld")
            elif leaf == "foundingDate":
                year = _YEAR_IN.search(value)
                if year:
                    _add(out, "founded_year", year.group(1), url, path, "jsonld")
            elif leaf == "price":
                _add(out, "price", value, url, path, "jsonld")
            elif leaf in ADDRESS_PARTS:
                address.append(value)
        if address:
            # One address, not five fragments: a postal code alone corroborates
            # nothing, and the parts are only a claim in combination.
            _add(out, "address", ", ".join(address), url, "address", "jsonld")


# The schema's third extraction_method, "meta", is deliberately unused. The one
# meta tag worth reading for a claim is og:site_name, and the page schema does
# not carry it; inventing a field to reach it would mean reopening a frozen
# contract for a source that JSON-LD's Organization.name already covers on every
# site that publishes either. If a rule ever needs it, that is the moment to ask.


def from_text(text, url, out):
    """Patterns whose surrounding words make the number a claim."""
    for match in _YEAR.finditer(text):
        _add(out, "founded_year", match.group(1), url, "text@%d" % match.start(), "visible_text")
    for match in _PRICE.finditer(text):
        _add(out, "price", match.group(0), url, "text@%d" % match.start(), "visible_text")
    for match in _COUNT.finditer(text):
        _add(out, "numeric_claim", match.group(0), url, "text@%d" % match.start(), "visible_text")


def from_headings(headings, page_type, url, out):
    """The first h1, read as what that kind of page's h1 usually asserts.

    A product page's h1 names the product; a home page's short h1 is a tagline
    candidate. Both are candidates precisely because neither is reliable, and
    the length bound is what keeps a paragraph-long h1 out of the tagline set.
    """
    first = next((h for h in headings if h.get("level") == 1 and h.get("text")), None)
    if first is None:
        return
    if page_type == "product":
        _add(out, "product_name", first["text"], url, "h1", "visible_text")
    elif page_type == "home" and len(first["text"]) <= 80:
        _add(out, "tagline", first["text"], url, "h1", "visible_text")


def aggregate(observations, cap=MAX_CANDIDATES):
    """Fold observations into candidates, counted, ordered and identified.

    One row per (kind, normalised value), carrying the first place it was seen
    and how often it was seen anywhere. ``observed_count`` is the signal that
    separates a tagline the site repeats on every page from a phrase that
    appeared once in a footer.

    Order is by kind, then descending count, then value, so two runs over one
    site assign the same CC- ids to the same strings.
    """
    grouped = {}
    for item in observations:
        key = (item["kind"], item["value_normalized"])
        found = grouped.get(key)
        if found is None:
            grouped[key] = dict(item, observed_count=1)
        else:
            found["observed_count"] += 1
    ordered = sorted(grouped.values(),
                     key=lambda c: (c["kind"], -c["observed_count"], c["value_normalized"]))
    kept, dropped = ordered[:cap], max(0, len(ordered) - cap)
    for index, candidate in enumerate(kept, start=1):
        candidate["id"] = "CC-%03d" % index
    return [{"id": c["id"], "kind": c["kind"], "value_raw": c["value_raw"],
             "value_normalized": c["value_normalized"], "source_url": c["source_url"],
             "locator": c["locator"], "extraction_method": c["extraction_method"],
             "observed_count": c["observed_count"]} for c in kept], dropped
