"""Proactive recommendations: strengthening actions the evidence warrants.

Step 8 of ../SKILL.md. The recommendations are specified as rule blocks in
../references/proactive.md, where their reasoning lives. Neither describes a
defect: both are ``status: proactive``, so severity is capped at medium and
priority held at P2 or P3 by severity.py, and neither can outrank a finding.

Each fires only on evidence. PRO-002 is specific to the site by construction.
PRO-001 fires wherever /llms.txt is absent, which is most sites, and is kept
anyway because docs/DECISIONS.md requires the llms.txt position to be stated as
speculative and low rather than left unsaid; references/proactive.md explains.

Every claim value that enters a prompt is observed content, and CLAUDE.md
forbids relaying observed content as a recommendation. So the panel uses only
claim kinds whose values are short facts (a name, a year, an address), never a
tagline or a product string, and each value must be short and made only of the
characters such facts are written in. A value that fails is left out, and so is
the panel if the name fails.

Standard library only.
"""

import re

SKILL = "audit-orchestrator"
SAFE_VALUE = re.compile(r"^[\w .,&'()/-]{1,80}$", re.UNICODE)


def _ref(url, observation, retrieved_at):
    return {"url": url, "observation": observation, "layer": "first_party", "method": "fetch",
            "retrieved_at": retrieved_at}


def pro_001(evidence, out):
    """/llms.txt was probed, answered, and is not present."""
    entry = [w for w in evidence["well_known"] if w["path"] == "/llms.txt"]
    if not entry or entry[0]["status"] is None:
        out["not_assessed"].append({"rule_id": "PRO-001", "reason": "/llms.txt was not probed or did not answer",
                                    "enable_hint": "the probe runs only where robots.txt allows the path"})
        return
    if entry[0]["present"]:
        out["passed"].append({"rule_id": "PRO-001", "summary": "/llms.txt is present; nothing to recommend"})
        return
    origin = (evidence["site"]["resolved_origin"] or evidence["site"]["input"]).rstrip("/")
    status = entry[0]["status"]
    # A 2xx without a file is the site's page for unknown addresses or an empty
    # body; saying "answered 200 and is not present" would read as a contradiction.
    answer = ("answered HTTP %s with no file: an empty body or the site's page for unknown addresses" % status
              if isinstance(status, int) and 200 <= status <= 299 else "answered HTTP %s" % status)
    out["findings"].append({
        "id": "F-001",
        "title": "Optional and speculative: publish /llms.txt",
        "evidence": "/llms.txt at %s %s, so no /llms.txt is published. No major assistant is documented to read this "
                    "file, so this is listed only as a low-cost hedge, not as a gap." % (origin, answer),
        "suggested_action": {
            "summary": "If it costs little, publish a short /llms.txt; do not expect it to change how assistants see "
                       "the site.",
            "what": "Publish a plain-text /llms.txt summarising what the site is and linking its key pages.",
            "where": "%s/llms.txt" % origin,
            "why": "It is a proposed convention some tools read; no major assistant documents consuming it, which is "
                   "why this is a suggestion and never reported as a problem.",
            "how": "Write a short markdown file: one paragraph describing the organization, then links to the pages "
                   "that answer the questions people ask about it. Keep it consistent with those pages.",
            "mechanism": "A possible, undocumented discovery channel for tools that adopt the convention.",
            "success_criteria": "/llms.txt answers 200 with content that is not the site's soft-404 page.",
            "effort": "low",
        },
        "skill": SKILL, "rule_id": "PRO-001", "status": "proactive", "category": "discoverability",
        "symptom": ["invisible"], "confidence": "low",
        "impact": {"blocking": False, "breadth": "page", "content_importance": "secondary"},
        "scope": {"pages_affected": 0, "pages_examined": 0, "page_types": []},
        "evidence_refs": [_ref(origin + "/llms.txt", "HTTP %s, no file published" % status,
                               evidence["run_context"]["started_at"])],
        "false_positive_controls_applied": [], "exceptions_checked": [],
    })


# The name question expects the site's own domain, not the name back: an
# assistant names the right website only if it resolved the right entity.
QUESTIONS = {
    "legal_name": "What is {name}, and what is its official website?",
    "founded_year": "When was {subject} founded?",
    # A buying question, because the answer an assistant gives it is often a
    # marketplace's search URL rather than the seller's own product page, and
    # which one it names is only visible where answers are produced.
    "product_name": "Where can I buy {subject}'s {value}, and on which page?",
}
# Two product questions at most: the panel is meant to be re-run by hand.
MAX_PRODUCT_QUESTIONS = 2


def pro_002(evidence, out):
    """A monitoring prompt panel, seeded from the claims this audit promoted."""
    claims = [c for c in evidence["canonical_claims"]
              if c["first_party_confidence"] in ("high", "medium") and c["kind"] in QUESTIONS
              and SAFE_VALUE.match(c["value_normalized"] or "")]
    claims.sort(key=lambda c: c["kind"] == "product_name")
    names = [c for c in claims if c["kind"] == "legal_name"]
    if not names:
        out["not_assessed"].append({"rule_id": "PRO-002", "reason":
                                    "no organization name was promoted with at least medium confidence and a plain "
                                    "short value, so there is nothing safe to build a prompt panel around",
                                    "enable_hint": "state the organization's name in Organization JSON-LD"})
        return
    name = names[0]["value_normalized"]
    # Medium counts too: a single distinctive word is shared by unrelated
    # companies often enough, and naming the domain costs the panel nothing.
    ambiguous = names[0]["entity_ambiguity"] in ("medium", "high")
    origin = (evidence["site"]["resolved_origin"] or evidence["site"]["input"]).rstrip("/")
    domain = origin.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    domain = domain[4:] if domain.startswith("www.") else domain
    # An ambiguous name gets the domain in every other question, so those answers
    # are about this organization; the name question stays bare, because whether
    # an assistant finds this organization from the name alone is what it tests.
    subject = "%s (%s)" % (name, domain) if ambiguous else name
    # One question per kind, and at most two products: a site that promotes three
    # names must not ask the same question three times, and the panel is meant to
    # be re-run by hand.
    limits = {"legal_name": 1, "founded_year": 1, "product_name": MAX_PRODUCT_QUESTIONS}
    panel, asked = [], {}
    for claim in claims:
        kind = claim["kind"]
        if asked.get(kind, 0) >= limits[kind]:
            continue
        asked[kind] = asked.get(kind, 0) + 1
        question = QUESTIONS[kind].format(name=name, subject=subject, value=claim["value_normalized"])
        # The buying question expects the site's own domain: an assistant naming a
        # marketplace's search page instead is the answer worth recording.
        expected = domain if claim["kind"] in ("legal_name", "product_name") else claim["value_normalized"]
        panel.append("%s (expected: %s)" % (question, expected))
    out["findings"].append({
        "id": "F-001",
        "title": "Monitor how assistants describe %s with a fixed prompt panel" % name,
        "evidence": "This audit observes the site, not assistants' answers, by design. %s, built from the claims "
                    "promoted with at least medium first-party confidence, so its expected answers are known: %s.%s"
                    % ("1 question" if len(panel) == 1 else "%d questions" % len(panel), "; ".join(panel[:6]),
                       " The name may be shared with other organizations, so the other questions name the domain, "
                       "and the first shows whether assistants find this organization from its name alone."
                       if ambiguous else ""),
        "suggested_action": {
            "summary": "Ask the same questions of the main assistants monthly and record whether each answer matches "
                       "the site.",
            "what": "Run a fixed panel of questions about %s against the assistants that matter to the site, on a "
                    "schedule, and record each answer against the expected value." % name,
            "where": "Outside the site: a shared sheet or a scheduled script owned by whoever owns the brand's facts.",
            "why": "Whether a fix changes what assistants say is not observable from the site, so it has to be "
                   "measured where it happens.",
            "how": "Use exactly these prompts each time, record date, assistant, answer and whether it matches: %s. "
                   "Re-run after each fix from this report to see whether it moved anything." % " | ".join(panel),
            "mechanism": "Turns the audit's fixes into something whose effect can be seen.",
            "success_criteria": "A dated record of answers per assistant exists, and each answer is marked as "
                                "matching or not matching the site's stated value.",
            "effort": "low",
        },
        "skill": SKILL, "rule_id": "PRO-002", "status": "proactive", "category": "discoverability",
        "symptom": ["misrepresented"], "confidence": "medium",
        "impact": {"blocking": False, "breadth": "site", "content_importance": "secondary"},
        "scope": {"pages_affected": 0, "pages_examined": 0, "page_types": []},
        "evidence_refs": [_ref(origin + "/", "claims promoted from first-party evidence: %d" % len(claims),
                               evidence["run_context"]["started_at"])],
        "false_positive_controls_applied": [], "exceptions_checked": [],
    })


# The organization types identity-and-markup recognises, repeated here because
# no skill imports another. A type missing from the list can only keep PRO-003
# silent: the recommendation needs an organization node to exist.
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


def _page_ref(page, observation):
    return {"url": page["url"], "observation": observation, "layer": page["provenance"]["layer"],
            "method": page["provenance"]["method"], "retrieved_at": page["fetched_at"]}


def _ok(page):
    return isinstance(page["status"], int) and 200 <= page["status"] <= 299


def pro_003(evidence, out):
    """Organization markup exists and declares no identity links at all."""
    pages = [p for p in evidence["pages"] if _ok(p)]
    anchors = [p for p in pages if p["page_type"] in ("home", "about")
               and any(n["type"] in ORG_TYPES for n in p["jsonld"])]
    if not anchors:
        out["not_assessed"].append({"rule_id": "PRO-003", "reason":
                                    "no 2xx home or about page carries organization markup to add identity links to",
                                    "enable_hint": "add Organization JSON-LD to the home page first; identity links "
                                                   "are then checked on the next audit"})
        return
    # Any node declaring sameAs silences the recommendation: an empty declaration
    # is IDM-002's defect, and a site anchoring identity on another node type has
    # already made the statement this recommendation asks for.
    declares = any("sameAs" in n["fields_present"] for p in pages for n in p["jsonld"])
    if declares:
        out["passed"].append({"rule_id": "PRO-003", "summary":
                              "Identity links (sameAs) are declared in the markup, so none is recommended; whether their "
                              "values identify anything is checked by IDM-002"})
        return
    page = anchors[0]
    ambiguous = any(c["kind"] == "legal_name" and c["entity_ambiguity"] == "high"
                    for c in evidence["canonical_claims"])
    node_type = [n["type"] for n in page["jsonld"] if n["type"] in ORG_TYPES][0]
    out["findings"].append({
        "id": "F-001",
        "title": "Anchor the organization's identity to its profiles elsewhere",
        "evidence": "%s describes the organization as %s in JSON-LD, and no organization node on any of the %d "
                    "sampled pages declares sameAs, so nothing in the markup ties this entity to its descriptions "
                    "elsewhere.%s" % (page["url"], node_type, len(pages),
                                      " The organization's name was scored as ambiguous, the case identity links "
                                      "exist for." if ambiguous else ""),
        "suggested_action": {
            "summary": "Add a sameAs array to the organization markup listing its Wikidata, Wikipedia and official "
                       "profile URLs.",
            "what": "Add a sameAs array to the organization markup listing the absolute URLs of its entries elsewhere.",
            "where": "The organization JSON-LD on %s." % page["url"],
            "why": "Identity links let a machine tie this site to the same entity in the sources it already trusts.",
            "how": "List the organization's Wikidata item and Wikipedia article if they exist, then its official "
                   "profiles (LinkedIn, Crunchbase, the main social accounts), only ones that describe this "
                   "organization.",
            "mechanism": "Entity disambiguation.",
            "success_criteria": "The organization node in the server response carries a sameAs array of absolute "
                                "URLs that each describe this organization.",
            "effort": "low",
        },
        "skill": SKILL, "rule_id": "PRO-003", "status": "proactive", "category": "discoverability",
        "symptom": ["misrepresented"], "confidence": "high" if ambiguous else "medium",
        "impact": {"blocking": False, "breadth": "site", "content_importance": "secondary"},
        "scope": {"pages_affected": 1, "pages_examined": len(pages), "page_types": [page["page_type"]]},
        "evidence_refs": [_page_ref(page, "%s node without sameAs" % node_type)],
        "false_positive_controls_applied": [], "exceptions_checked": [],
    })


def pro_004(evidence, out):
    """Articles show a date and state none in structured data."""
    # Only English or undeclared pages: a date written in another language is
    # not read, so an article showing one would silently drop out of the count.
    articles = [p for p in evidence["pages"] if _ok(p) and p["page_type"] == "article"
                and (p["page_type_confidence"] or 0) >= 0.8 and p["dates"]["visible_dates"]
                and (p["lang"] is None or re.split(r"[-_]", p["lang"].strip().lower())[0] in ("en", ""))]
    if len(articles) < 2:
        out["not_assessed"].append({"rule_id": "PRO-004", "reason":
                                    "%d sampled articles show a visible date; at least 2 are needed to judge the "
                                    "article template" % len(articles),
                                    "enable_hint": "only applies to sites that publish dated articles; audit the "
                                                   "blog or news section's URL directly to sample more of them"})
        return
    bare = [p for p in articles
            if not p["dates"]["schema_date_published"] and not p["dates"]["schema_date_modified"]]
    if len(bare) < 2 or len(bare) * 2 < len(articles):
        out["passed"].append({"rule_id": "PRO-004", "summary":
                              "Articles that show a date also state it in structured data (%d of %d do not)"
                              % (len(bare), len(articles))})
        return
    out["findings"].append({
        "id": "F-001",
        "title": "Give the dates articles show a machine-readable form",
        "evidence": "%d of %d sampled articles show a date on the page and carry neither datePublished nor "
                    "dateModified in structured data: %s." % (len(bare), len(articles),
                                                             ", ".join(p["url"] for p in bare[:5])),
        "suggested_action": {
            "summary": "Emit datePublished and dateModified in the article template's structured data.",
            "what": "Emit the article's publication and update dates in its structured data.",
            "where": "The article template behind the URLs cited.",
            "why": "A structured date states which date is the article's, in an unambiguous format.",
            "how": "Add datePublished and dateModified in ISO 8601 to the Article, NewsArticle or BlogPosting JSON-LD, "
                   "generated from the same fields that render the visible date.",
            "mechanism": "Recency read rather than inferred.",
            "success_criteria": "Every cited article carries datePublished or dateModified in its server response "
                                "JSON-LD, matching the date it shows.",
            "effort": "low",
        },
        "skill": SKILL, "rule_id": "PRO-004", "status": "proactive", "category": "discoverability",
        "symptom": ["misrepresented"], "confidence": "medium",
        "impact": {"blocking": False, "breadth": "section", "content_importance": "secondary"},
        "scope": {"pages_affected": len(bare), "pages_examined": len(articles), "page_types": ["article"]},
        "evidence_refs": [_page_ref(p, "a date is shown on the page; no datePublished or dateModified")
                          for p in bare],
        "false_positive_controls_applied": [], "exceptions_checked": [],
    })


RECOMMENDATIONS = (pro_001, pro_002, pro_003, pro_004)


def recommend(evidence):
    """Findings, not_assessed and checks_passed for every proactive recommendation."""
    out = {"findings": [], "not_assessed": [], "passed": []}
    for build in RECOMMENDATIONS:
        build(evidence, out)
    return out["findings"], out["not_assessed"], out["passed"]
