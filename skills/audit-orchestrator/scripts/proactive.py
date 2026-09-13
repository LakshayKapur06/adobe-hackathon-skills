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
    out["findings"].append({
        "id": "F-001",
        "title": "Optional and speculative: publish /llms.txt",
        "evidence": "/llms.txt at %s answered HTTP %s and is not present. No major assistant is documented to read this "
                    "file, so this is listed only as a low-cost hedge, not as a gap." % (origin, entry[0]["status"]),
        "suggested_action": {
            "summary": "If it costs little, publish a short /llms.txt; do not expect it to change how assistants see "
                       "the site.",
            "what": "Publish a plain-text /llms.txt summarising what the site is and linking its key pages.",
            "where": "%s/llms.txt" % origin,
            "why": "It is a proposed convention some tools read; no major assistant documents consuming it, which is "
                   "why this is proactive and never a finding.",
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
        "evidence_refs": [_ref(origin + "/llms.txt", "HTTP %s, not present" % entry[0]["status"],
                               evidence["run_context"]["started_at"])],
        "false_positive_controls_applied": [], "exceptions_checked": [],
    })


QUESTIONS = {
    "legal_name": "What is {name}, and what does it do?",
    "founded_year": "When was {name} founded?",
    "address": "Where is {name} based?",
}


def pro_002(evidence, out):
    """A monitoring prompt panel, seeded from the claims this audit promoted."""
    claims = [c for c in evidence["canonical_claims"]
              if c["first_party_confidence"] in ("high", "medium") and c["kind"] in QUESTIONS
              and SAFE_VALUE.match(c["value_normalized"] or "")]
    names = [c for c in claims if c["kind"] == "legal_name"]
    if not names:
        out["not_assessed"].append({"rule_id": "PRO-002", "reason":
                                    "no organization name was promoted with at least medium confidence and a plain "
                                    "short value, so there is nothing safe to build a prompt panel around",
                                    "enable_hint": "state the organization's name in Organization JSON-LD"})
        return
    name = names[0]["value_normalized"]
    panel = []
    for claim in claims:
        question = QUESTIONS.get(claim["kind"])
        if question:
            panel.append("%s (expected: %s)" % (question.format(name=name, value=claim["value_normalized"]),
                                                claim["value_normalized"]))
    ambiguous = names[0]["entity_ambiguity"] == "high"
    origin = (evidence["site"]["resolved_origin"] or evidence["site"]["input"]).rstrip("/")
    out["findings"].append({
        "id": "F-001",
        "title": "Monitor how assistants describe %s with a fixed prompt panel" % name,
        "evidence": "This audit observes the site, not assistants' answers, by design. %d claims were promoted with at "
                    "least medium first-party confidence, which gives a panel whose expected answers are known: %s.%s"
                    % (len(claims), "; ".join(panel[:6]),
                       " The name was scored ambiguous, so answers may describe a different entity; add the domain to "
                       "each prompt." if ambiguous else ""),
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
                                    "no 2xx home or about page carries organization markup to anchor",
                                    "enable_hint": "applies to sites whose home or about page describes the "
                                                   "organization in JSON-LD"})
        return
    # Any node declaring sameAs silences the recommendation: an empty declaration
    # is IDM-002's defect, and a site anchoring identity on another node type has
    # already made the statement this recommendation asks for.
    declares = any("sameAs" in n["fields_present"] for p in pages for n in p["jsonld"])
    if declares:
        out["passed"].append({"rule_id": "PRO-003", "summary":
                              "The site's markup declares sameAs identity links"})
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
    articles = [p for p in evidence["pages"] if _ok(p) and p["page_type"] == "article"
                and (p["page_type_confidence"] or 0) >= 0.8 and p["dates"]["visible_dates"]]
    if len(articles) < 2:
        out["not_assessed"].append({"rule_id": "PRO-004", "reason":
                                    "articles showing a visible date, classified with confidence >= 0.8: %d; 2 are "
                                    "needed" % len(articles),
                                    "enable_hint": "applies to sites publishing dated articles"})
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
        "evidence_refs": [_page_ref(p, "visible date %s, no structured date" % p["dates"]["visible_dates"][0])
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
