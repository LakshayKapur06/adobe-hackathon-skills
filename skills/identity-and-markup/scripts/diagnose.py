"""identity-and-markup: the four rules in ../references/rules.md, as code.

Reads evidence/evidence.json and nothing else, and writes one findings file
holding ``findings``, ``not_assessed`` and ``checks_passed``. Promotion of claim
candidates is a separate step, in promote.py, which runs earlier in the
pipeline; nothing here writes to the bundle.

Each function implements the rule block of the same id; the block holds the
reasons. ``severity`` and ``suggested_action.priority`` are never set; the
orchestrator derives them.

Standard library only. No imports from any other skill.
"""

import argparse
import json
import os
import re
import urllib.parse

SKILL = "identity-and-markup"
SUPPORTED_SCHEMA_MAJOR = "1"

# schema.org Organization and the subtypes a site is likely to use for itself.
# Not exhaustive by design: any node carrying logo or sameAs also counts as a
# self-description, so a subtype missing here cannot make a site read as bare.
ORG_TYPES = frozenset("""
Organization Corporation NGO GovernmentOrganization EducationalOrganization CollegeOrUniversity School
MedicalOrganization Hospital Clinic Pharmacy NewsMediaOrganization SportsOrganization SportsTeam PerformingGroup
ResearchOrganization Airline Consortium LibrarySystem PoliticalParty WorkersUnion FundingScheme Project
OnlineBusiness OnlineStore LocalBusiness Store AutoDealer BookStore ClothingStore ComputerStore ElectronicsStore
Florist FurnitureStore GroceryStore HardwareStore HobbyShop HomeGoodsStore JewelryStore MobilePhoneStore
OfficeEquipmentStore PetStore ShoeStore SportingGoodsStore ToyStore Restaurant FoodEstablishment Bakery CafeOrCoffeeShop
BarOrPub ProfessionalService LegalService Attorney FinancialService BankOrCreditUnion InsuranceAgency AccountingService
RealEstateAgent TravelAgency LodgingBusiness Hotel HealthAndBeautyBusiness MedicalBusiness Dentist Physician
AutomotiveBusiness HomeAndConstructionBusiness EntertainmentBusiness EmploymentAgency SelfStorage ChildCare
""".split())
URL = re.compile(r"^https?://\S+$", re.I)
# A schema.org type name. Types are quoted in evidence, and a site can put any
# string in @type, so only names of this shape are quoted; others are counted.
TYPE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,63}$")


def is_2xx(status):
    return isinstance(status, int) and 200 <= status <= 299


def ok_pages(evidence):
    return [p for p in evidence["pages"] if is_2xx(p["status"])]


def is_org_node(node):
    if node["type"] in ORG_TYPES:
        return True
    if any(f in ("logo", "sameAs") for f in node["fields_present"]):
        return True
    return any(key.endswith(".@type") and value in ORG_TYPES for key, value in node["values"].items())


def ref(page, observation):
    return {"url": page["url"], "observation": observation, "layer": page["provenance"]["layer"],
            "method": page["provenance"]["method"], "retrieved_at": page["fetched_at"]}


def plural(n, word, many=None):
    return "%d %s" % (n, word if n == 1 else (many or word + "s"))


def finding(rule_id, title, evidence, action, *, confidence, impact, scope, refs, controls, exceptions):
    return {"id": "F-001", "title": title, "evidence": evidence, "suggested_action": action, "skill": SKILL,
            "rule_id": rule_id, "status": "found", "category": "discoverability", "symptom": ["misrepresented"],
            "confidence": confidence, "impact": impact, "scope": scope, "evidence_refs": refs,
            "false_positive_controls_applied": list(controls), "exceptions_checked": list(exceptions)}


def action(summary, what, where, why, how, mechanism, success, effort):
    return {"summary": summary, "what": what, "where": where, "why": why, "how": how,
            "mechanism": mechanism, "success_criteria": success, "effort": effort}


def breadth_by_share(affected, total):
    if affected * 2 >= total:
        return "site"
    return "section" if affected >= 2 else "page"


def idm_001(evidence, out):
    pages = ok_pages(evidence)
    homes = [p for p in pages if p["page_type"] == "home"]
    if not homes:
        out["not_assessed"].append({"rule_id": "IDM-001", "reason": "no 2xx home page was observed",
                                    "enable_hint": "the home page must answer this client with 2xx"})
        return
    home = homes[0]
    if home["microdata_or_rdfa"]:
        out["not_assessed"].append({"rule_id": "IDM-001", "reason":
                                    "the home page carries microdata or RDFa, which may state the organization and "
                                    "is not parsed by the collector",
                                    "enable_hint": "express organization identity as JSON-LD to make it assessable"})
        return
    if any(is_org_node(n) for n in home["jsonld"]):
        out["passed"].append({"rule_id": "IDM-001", "summary":
                              "The home page's JSON-LD states an organization identity"})
        return
    about = [p for p in pages if p["page_type"] == "about" and any(is_org_node(n) for n in p["jsonld"])]
    if about:
        out["passed"].append({"rule_id": "IDM-001", "summary":
                              "Organization identity is stated in JSON-LD on the about page %s" % about[0]["url"]})
        return
    if any(n["type"] == "Person" for n in home["jsonld"]):
        out["passed"].append({"rule_id": "IDM-001", "summary":
                              "The home page describes a Person, so organization markup does not apply"})
        return
    host = (evidence["site"]["resolved_origin"] or "").split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower()
    parent = (evidence["site"]["registrable_domain"] or "").lower()
    if parent and host not in (parent, "www." + parent):
        # A subdomain such as docs. or help. is part of an organization whose
        # identity belongs on its main domain's home page, which this audit did
        # not fetch. Absence here says nothing about the organization.
        out["not_assessed"].append({"rule_id": "IDM-001", "reason":
                                    "%s is a subdomain of %s; organization identity is normally stated on the main "
                                    "domain's home page, which this audit did not fetch" % (host, parent),
                                    "enable_hint": "check https://%s/ for Organization JSON-LD, or audit %s directly"
                                                   % (parent, parent)})
        return
    types = sorted({n["type"] for n in home["jsonld"] if n["type"] and TYPE_NAME.match(n["type"])})
    unnamed = len({n["type"] for n in home["jsonld"] if n["type"] and not TYPE_NAME.match(n["type"])})
    out["findings"].append(finding(
        "IDM-001", "The home page carries no machine-readable organization identity",
        "The home page's server response has %s and none describes an organization%s; no 2xx about page carries one "
        "either, and no microdata or RDFa is present."
        % (plural(len(home["jsonld"]), "JSON-LD node"),
           (" (types: %s%s)" % (", ".join(types), ", and %s not quoted" % plural(unnamed, "non-schema.org type value")
                                if unnamed else "")) if types or unnamed else ""),
        action("Add Organization JSON-LD with name, url, logo and sameAs to the home page.",
               "Add an Organization JSON-LD block, or the most specific subtype that applies, to the home page.",
               "The home page template's <head>, in the server response (%s)." % home["url"],
               "It states the entity behind the site explicitly instead of leaving it to be inferred from a name.",
               "Emit @type, name, url, logo and sameAs with the organization's profile URLs on other sites, plus "
               "legalName and address where they apply, generated server-side.",
               "Entity disambiguation.",
               "The home page's server response contains a JSON-LD node of an Organization type with at least name "
               "and url.", "low"),
        confidence="high",
        impact={"blocking": False, "breadth": "site", "content_importance": "secondary"},
        scope={"pages_affected": 1, "pages_examined": 1, "page_types": ["home"]},
        refs=[ref(home, "JSON-LD types on the home page: %s" % (", ".join(types) or "none"))],
        controls=["2xx pages only", "organization subtypes and nested publisher organizations count",
                  "any node with logo or sameAs counts", "microdata or RDFa stops the rule"],
        exceptions=["identity on the about page instead: no 2xx about page carries it",
                    "a person's site: no Person node on the home page"]))


def sameas_entries(node):
    raw = node["values"].get("sameAs")
    if raw is None:
        return None
    return [part.strip() for part in raw.split(" | ")]


# The social accounts of the platforms sites are built on. Themes ship with them
# as default social links, and a merchant who never replaces them publishes, in
# sameAs, that the organization *is* the platform. Exact handles only: a handle
# merely containing a vendor's name is a different account.
PLATFORM_HANDLES = frozenset(("shopify", "wix", "squarespace", "wordpress", "bigcommerce", "woocommerce",
                              "webflow", "godaddy", "weebly", "hubspot"))
PLATFORM_NAMES = {"wordpress": "WordPress", "bigcommerce": "BigCommerce", "woocommerce": "WooCommerce",
                  "godaddy": "GoDaddy", "hubspot": "HubSpot"}
SOCIAL_HOSTS = frozenset(("facebook.com", "instagram.com", "twitter.com", "x.com", "tiktok.com", "youtube.com",
                          "pinterest.com", "linkedin.com", "vimeo.com", "snapchat.com", "threads.net"))


def platform_account(entry):
    """The platform an entry's social profile belongs to, or None."""
    if not URL.match(entry):
        return None
    parts = urllib.parse.urlsplit(entry)
    host = parts.netloc.lower().split(":")[0]
    for prefix in ("www.", "m.", "mobile."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    if host not in SOCIAL_HOSTS:
        return None
    segments = [s.lstrip("@").lower() for s in parts.path.split("/") if s][:3]
    return next((s for s in segments if s in PLATFORM_HANDLES), None)


def idm_002(evidence, out):
    assessable, broken, borrowed = [], [], []
    own_site = (evidence["site"]["registrable_domain"] or "").lower().split(".")[0]
    for page in ok_pages(evidence):
        for node in page["jsonld"]:
            # Strictly an organization type here: the broader self-description
            # test in is_org_node counts any node with sameAs, which would let an
            # unrelated node's empty sameAs fire this rule.
            if node["type"] not in ORG_TYPES or "sameAs" not in node["fields_present"]:
                continue
            entries = sameas_entries(node)
            if entries is None:
                continue
            assessable.append(page)
            if not any(URL.match(e) for e in entries):
                broken.append((page, node, entries))
                continue
            accounts = [e for e in entries if platform_account(e) and platform_account(e) != own_site]
            if accounts:
                borrowed.append((page, node, entries, accounts))
    if not assessable:
        out["not_assessed"].append({"rule_id": "IDM-002", "reason":
                                    "no organization node on a 2xx page declares sameAs with its value recorded",
                                    "enable_hint": "applies only to organization markup that declares sameAs"})
        return
    if not broken and not borrowed:
        out["passed"].append({"rule_id": "IDM-002", "summary":
                              "Every declared organization sameAs holds at least one absolute URL, and none names a "
                              "site platform's own account (%s)" % plural(len(assessable), "declaration")})
        return
    if not broken:
        idm_002_borrowed(evidence, out, borrowed)
        return
    pages = []
    for page, _, _ in broken:
        if page not in pages:
            pages.append(page)
    total = len(ok_pages(evidence))
    home_hit = any(p["page_type"] == "home" for p in pages)
    sample_page, sample_node, sample_entries = broken[0]
    out["findings"].append(finding(
        "IDM-002", "Organization markup declares sameAs links that identify nothing",
        "%s of %s carry an organization node (%s) whose sameAs is declared with %s and not one absolute URL: %s."
        % (len(pages), plural(total, "2xx page"), sample_node["type"] or "untyped",
           plural(len(sample_entries), "entry", "entries"), json.dumps(sample_entries[:6])),
        action("Fill sameAs with the organization's real profile URLs, or remove the property until there are some.",
               "Fill sameAs with the organization's real profile URLs, or remove the property.",
               "The theme or template setting that populates the organization markup's sameAs, usually the "
               "social-links configuration.",
               "An empty identity link is noise a consumer has to discard.",
               "Enter the absolute URLs of the organization's official profiles in the theme's social settings, or "
               "edit the template to omit empty entries.",
               "Identity anchoring to external descriptions of the same entity.",
               "Every organization node's sameAs in the server response contains only absolute http or https URLs, "
               "or the property is absent.", "low"),
        confidence="high",
        impact={"blocking": False, "breadth": "site" if home_hit or len(pages) * 2 >= total else "page",
                "content_importance": "secondary"},
        scope={"pages_affected": len(pages), "pages_examined": total,
               "page_types": sorted({p["page_type"] for p in pages})},
        refs=[ref(p, "sameAs declared with no absolute URL") for p in pages[:10]],
        controls=["sameAs truncated from values excluded, never read as empty",
                  "one absolute http(s) URL makes a node pass", "only organization nodes counted"],
        exceptions=["organization with no external profiles: it would not declare sameAs at all"]))


def idm_002_borrowed(evidence, out, borrowed):
    """sameAs names the platform's own social accounts as this organization."""
    pages = []
    for page, _, _, _ in borrowed:
        if page not in pages:
            pages.append(page)
    total = len(ok_pages(evidence))
    home_hit = any(p["page_type"] == "home" for p in pages)
    _, sample_node, sample_entries, accounts = borrowed[0]
    handle = platform_account(accounts[0])
    platform = PLATFORM_NAMES.get(handle, handle.capitalize())
    empty = sum(1 for e in sample_entries if not e.strip())
    out["findings"].append(finding(
        "IDM-002", "Organization sameAs declares the site platform's own profiles as this organization",
        "%s of %s carry an organization node (%s) whose sameAs lists %s: %s. sameAs states that each listed profile "
        "is this same organization, so the markup identifies it with its platform's accounts.%s"
        % (len(pages), plural(total, "2xx page"), sample_node["type"] or "untyped",
           "a profile belonging to the %s platform" % platform if len(accounts) == 1
           else "%d profiles belonging to the %s platform" % (len(accounts), platform),
           ", ".join(accounts[:5]),
           (" The same list also holds %s." % plural(empty, "empty entry", "empty entries")) if empty else ""),
        action("Replace the platform's default social profiles in sameAs with the organization's own.",
               "Remove the platform's profiles from sameAs and list only profiles of this organization.",
               "The theme or template setting that populates the organization markup's sameAs, usually the "
               "social-links configuration, where theme defaults were never replaced.",
               "sameAs asserts identity, so a platform's account listed there tells a machine this organization is "
               "the platform.",
               "In the theme's social-links settings, replace every default profile URL with the organization's "
               "own profile, and clear the fields for networks it does not use so no empty or default entry is "
               "emitted.",
               "Identity anchoring to external descriptions of the same entity.",
               "No sameAs entry in the server response names a platform's own account, and every entry is an "
               "absolute URL of a profile of this organization.", "low"),
        confidence="high",
        impact={"blocking": False, "breadth": "site" if home_hit or len(pages) * 2 >= total else "page",
                "content_importance": "secondary"},
        scope={"pages_affected": len(pages), "pages_examined": total,
               "page_types": sorted({p["page_type"] for p in pages})},
        refs=[ref(p, "sameAs names %s's own profiles" % platform) for p in pages[:10]],
        controls=["only exact platform handles on known social networks count",
                  "the platform's own site is never flagged for its own accounts",
                  "only organization nodes counted", "sameAs truncated from values excluded"],
        exceptions=["a site operated by the platform itself: detected by its registrable domain"]))


def is_parse_failure(node):
    return not node["valid"] and not node["type"] and not node["fields_present"]


def idm_003(evidence, out):
    pages = ok_pages(evidence)
    with_jsonld = [p for p in pages if p["jsonld"]]
    if not with_jsonld:
        out["not_assessed"].append({"rule_id": "IDM-003", "reason": "no 2xx page carries any JSON-LD to parse",
                                    "enable_hint": "applies only to pages that emit JSON-LD"})
        return
    failing = [p for p in with_jsonld if any(is_parse_failure(n) for n in p["jsonld"])]
    if not failing:
        out["passed"].append({"rule_id": "IDM-003", "summary":
                              "Every JSON-LD block parsed on %s" % plural(len(with_jsonld), "page carrying JSON-LD", "pages carrying JSON-LD")})
        return
    count = sum(1 for p in failing for n in p["jsonld"] if is_parse_failure(n))
    out["findings"].append(finding(
        "IDM-003", "JSON-LD blocks that no parser can read",
        "%s on %s of %s carrying JSON-LD failed to parse as JSON, so every statement in them is discarded: %s."
        % (plural(count, "block"), len(failing), plural(len(with_jsonld), "2xx page"),
           ", ".join(p["url"] for p in failing[:5])),
        action("Generate JSON-LD with a JSON serializer so the blocks parse.",
               "Fix the JSON syntax of the failing blocks.",
               "The template or plugin emitting the application/ld+json block on the URLs cited.",
               "One syntax error discards every statement in the block.",
               "Generate the block with a JSON serializer rather than string concatenation, and validate the output "
               "of each cited URL with a JSON parser.",
               "The markup the site already wrote becomes readable.",
               "Every JSON-LD block on the cited URLs parses as JSON.", "low"),
        confidence="high",
        impact={"blocking": False, "breadth": breadth_by_share(len(failing), len(pages)),
                "content_importance": "secondary"},
        scope={"pages_affected": len(failing), "pages_examined": len(with_jsonld),
               "page_types": sorted({p["page_type"] for p in failing})},
        refs=[ref(p, "%s failed to parse" % plural(sum(1 for n in p["jsonld"] if is_parse_failure(n)), "JSON-LD block"))
              for p in failing],
        controls=["parse failures identified by structure, not error text",
                  "untyped nodes that parsed are not counted", "comment wrappers stripped before parsing"],
        exceptions=["lenient consumers tolerating the error: not relied upon"]))


COMMERCE_TYPES = ("Product", "ProductGroup", "IndividualProduct", "Offer", "AggregateOffer")


def marked_price(node):
    """The positive price a commerce node states, or None."""
    if node["type"] not in COMMERCE_TYPES:
        return None
    raw = node["values"].get("offers.price") or node["values"].get("price") or ""
    try:
        value = float(raw.replace(",", ""))
    except ValueError:
        return None
    return value if value > 0 else None


def states_price(node):
    return marked_price(node) is not None


def idm_004(evidence, out):
    priced = [p for p in ok_pages(evidence) if any(states_price(n) for n in p["jsonld"])]
    if not priced:
        out["not_assessed"].append({"rule_id": "IDM-004", "reason": "no 2xx page carries a commerce node (Product or Offer) stating a price above zero",
                                    "enable_hint": "applies only to pages with Offer or price markup"})
        return
    hit = [p for p in priced if any(states_price(n) and n["contradicts_visible_text"] for n in p["jsonld"])]
    if not hit:
        out["passed"].append({"rule_id": "IDM-004", "summary":
                              "No marked-up price contradicts the visible prices (%s with price markup)"
                              % plural(len(priced), "page")})
        return

    def marked(page):
        node = [n for n in page["jsonld"] if states_price(n) and n["contradicts_visible_text"]][0]
        return node["values"].get("offers.price") or node["values"].get("price")

    out["findings"].append(finding(
        "IDM-004", "Structured price contradicts the prices shown on the page",
        "On %d of %s with price markup, the page shows currency amounts and none equals the marked-up price: %s."
        % (len(hit), plural(len(priced), "2xx page"),
           "; ".join("%s (markup %s)" % (p["url"], marked(p)) for p in hit[:5])),
        action("Generate offers.price from the same value that renders the visible price.",
               "Make the marked-up price equal the price the page shows.",
               "The product template's Offer markup on the URLs cited, and the data source it reads the price from.",
               "Markup is taken as the authoritative statement, so a stale or base price there is repeated as fact.",
               "Generate offers.price from the same variable that renders the visible price, including sale and "
               "selected-variant logic, rather than from a separate field.",
               "The structured statement of price matches what a buyer sees.",
               "On every cited URL, the offers.price value in the server response equals a price shown in the page's "
               "visible text.", "medium"),
        confidence="high" if len(hit) >= 2 else "medium",
        impact={"blocking": False, "breadth": "section" if len(hit) >= 2 else "page",
                "content_importance": "primary"},
        scope={"pages_affected": len(hit), "pages_examined": len(priced),
               "page_types": sorted({p["page_type"] for p in hit})},
        refs=[ref(p, "markup price %s is not among the prices shown" % marked(p)) for p in hit],
        controls=["commerce nodes only, and a price of zero never counts",
                  "a price absent from visible text is never a contradiction",
                  "a page showing the marked-up price among others matches", "2xx pages only"],
        exceptions=["server-side currency conversion or a different default variant: undetectable, medium confidence "
                    "on a single page"]))


RULES = (idm_001, idm_002, idm_003, idm_004)


def diagnose(evidence):
    version = str(evidence.get("schema_version", ""))
    if version.split(".")[0] != SUPPORTED_SCHEMA_MAJOR:
        raise ValueError("unsupported evidence schema_version %r; this skill reads %s.x"
                         % (version, SUPPORTED_SCHEMA_MAJOR))
    out = {"findings": [], "not_assessed": [], "passed": []}
    for rule in RULES:
        rule(evidence, out)
    for index, item in enumerate(out["findings"], start=1):
        item["id"] = "F-%03d" % index
    return {"findings": out["findings"], "not_assessed": out["not_assessed"], "checks_passed": out["passed"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the identity-and-markup rules over an evidence bundle.")
    parser.add_argument("--evidence", required=True, help="path to evidence/evidence.json")
    parser.add_argument("--out", required=True, help="path to write findings/identity-and-markup.json")
    args = parser.parse_args(argv)
    with open(args.evidence, encoding="utf-8") as handle:
        result = diagnose(json.load(handle))
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
