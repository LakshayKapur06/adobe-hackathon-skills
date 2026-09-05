# CONTRACTS.md — frozen data contracts

**This file is frozen.** Everything else compiles against it. Changing it
mid-build invalidates written rules and tests. If a change looks necessary,
stop and ask.

Three contracts: the evidence bundle, the finding, and the severity function.

---

## 1. `evidence/evidence.json`

Produced by `site-evidence-collector`. Consumed by every diagnostic. Diagnostics
may read nothing else.

```jsonc
{
  "schema_version": "1.0.0",
  "site": {
    "input": "https://example.com",
    "resolved_origin": "https://www.example.com",
    "registrable_domain": "example.com",
    "detected_locales": ["en-IN"]
  },
  "run_context": {
    "started_at": "2026-09-20T14:32:00Z",
    "finished_at": "2026-09-20T14:35:10Z",
    "capabilities": { "js_render": true, "egress": true, "renderer": "system-chromium" },
    "budgets": { "global_s": 300, "crawl_s": 90, "render_s": 60, "external_s": 90 },
    "degradations": [ { "what": "render", "reason": "no browser found", "impact": "render-delta rules not assessed" } ],
    "corroboration": { "method": "keyless", "provider_unavailable": [] }
  },
  "robots": {
    "fetched": true, "url": "https://example.com/robots.txt", "status": 200,
    "groups": [ { "user_agent": "*", "allow": [], "disallow": ["/cart"], "crawl_delay": null } ],
    "ai_agents": { "GPTBot": "disallowed", "ClaudeBot": "unspecified", "PerplexityBot": "unspecified",
                   "Google-Extended": "unspecified", "OAI-SearchBot": "unspecified", "CCBot": "unspecified",
                   "Googlebot": "allowed" },
    "sitemaps": ["https://example.com/sitemap.xml"]
  },
  "sitemaps": [ { "url": "...", "status": 200, "url_count": 412, "lastmod_present_ratio": 0.12, "parse_ok": true } ],
  "crawl": {
    "discovered": 412, "fetched": 24, "blocked_by_robots": 3, "errors": 1,
    "sampling": { "strategy": "stratified:sitemap+nav+linkgraph",
                  "strata": [ { "page_type": "product", "discovered": 300, "sampled": 12 } ] }
  },
  "pages": [ /* PageEvidence, see below */ ],
  "link_graph": { "edges": [["/", "/shoes"]], "orphans": ["/legacy/x"], "max_depth_from_home": 4 },
  "claim_candidates": [
    { "id": "CC-001", "kind": "tagline|legal_name|founded_year|price|address|product_name|numeric_claim",
      "value_raw": "Built to Fly", "value_normalized": "built to fly",
      "source_url": "https://example.com/", "locator": "h2:nth-of-type(1)",
      "extraction_method": "visible_text|jsonld|meta", "observed_count": 7 }
  ],
  "canonical_claims": [
    { "id": "C-001", "from_candidates": ["CC-001"], "kind": "tagline",
      "value_normalized": "built to fly", "first_party_confidence": "high",
      "entity_ambiguity": "low|medium|high" }
  ],
  "external": {
    "attempted": true, "method": "keyless", "frontier_size": 14, "truncated": false,
    "origins": [ { "registrable_domain": "wikidata.org", "source_type": "encyclopedic",
                   "urls": ["..."], "syndication_cluster": null, "brand_owned": false } ],
    "hits": [ { "claim_id": "C-001", "origin": "wikidata.org", "url": "...",
                "asserted_value": "fly higher", "matches_current": false,
                "retrieved_at": "2026-09-20T14:34:02Z" } ]
  },
  "errors": [ { "url": "...", "stage": "fetch", "message": "timeout" } ]
}
```

### PageEvidence

```jsonc
{
  "url": "https://example.com/shoes/x9",
  "final_url": "https://example.com/shoes/x9",
  "status": 200,
  "redirect_chain": [],
  "content_type": "text/html",
  "fetched_at": "2026-09-20T14:32:40Z",
  "headers": { "x_robots_tag": null, "last_modified": null, "cache_control": "..." },
  "meta_robots": ["index", "follow"],
  "canonical": "https://example.com/shoes/x9",
  "canonical_self": true,
  "lang": "en",
  "hreflang": [],
  "page_type": "product",
  "page_type_confidence": 0.82,
  "raw": {
    "bytes": 48213, "text_len": 1840, "text_hash": "sha256:...",
    "headings": [ { "level": 1, "text": "Velocity X9" } ],
    "links": [ { "href": "/cart", "rel": null, "anchor": "Buy", "internal": true } ],
    "images": [ { "src": "/img/spec.png", "alt": "", "text_likely": true } ],
    "tables": 1, "iframes": 0, "forms": 1
  },
  "rendered": { "available": true, "text_len": 4210, "text_hash": "sha256:...",
                "headings": [], "delta_ratio": 0.56 },
  "jsonld": [ { "type": "Product", "valid": true, "errors": [],
                "fields_present": ["name","offers.price","offers.priceCurrency"],
                "contradicts_visible_text": false } ],
  "microdata_or_rdfa": false,
  "text": { "visible_excerpt": "...", "word_count": 620, "boilerplate_ratio": 0.41,
            "longest_block_words": 180, "heading_density_per_1k": 6.4 },
  "dates": { "visible_dates": [], "schema_date_modified": null,
             "schema_date_published": null, "http_last_modified": null },
  "obstructions": [ { "kind": "cookie_wall|modal|paywall|age_gate", "evidence": "..." } ],
  "timing": { "ttfb_ms": 210, "fetch_ms": 340, "render_ms": 1420 },
  "provenance": { "layer": "first_party", "method": "fetch|render" }
}
```

**Rule:** if a diagnostic needs a field that is not in this schema, that is a
contract change. Stop and ask. Do not invent the field.

---

## 2. Finding

Handout-required fields are marked. Everything else is an approved extension.

```jsonc
{
  "id": "F-001",                                   // REQUIRED
  "title": "Product prices absent from server HTML",// REQUIRED
  "severity": "critical|high|medium|low",           // REQUIRED (summary counts the first three)
  "evidence": "Rendered 12 product pages; price present in rendered DOM on 12/12, present in server HTML on 0/12.", // REQUIRED
  "suggested_action": {                             // REQUIRED
    "summary": "Server-render or prerender price and availability on product templates.", // REQUIRED
    "priority": "P0|P1|P2|P3",                      // REQUIRED
    "what": "...", "where": "...", "why": "...", "how": "...",
    "mechanism": "Retrieval operates on fetched HTML; a fact absent there cannot be extracted or quoted.",
    "success_criteria": "Price string present in the server response for 100% of sampled product URLs.",
    "effort": "low|medium|high"
  },

  "skill": "render-and-extraction",
  "rule_id": "RND-002",
  "status": "found|risk|proactive",
  "category": "discoverability|engagement",
  "symptom": ["invisible", "misrepresented", "bounce"],
  "confidence": "high|medium|low",
  "impact": { "blocking": true, "breadth": "site|section|page", "content_importance": "primary|secondary" },
  "scope": { "pages_affected": 12, "pages_examined": 12, "page_types": ["product"] },
  "evidence_refs": [ { "url": "...", "observation": "raw.text lacks price token; rendered.text contains it",
                       "layer": "first_party", "method": "render", "retrieved_at": "..." } ],
  "false_positive_controls_applied": ["price-token normalisation", "excluded pages with no Offer markup"],
  "exceptions_checked": ["quote-on-request pricing model"]
}
```

Separate top-level arrays in the report, so neither inflates `total_findings`:

```jsonc
"not_assessed": [ { "rule_id": "RND-002", "reason": "no browser available",
                    "enable_hint": "install a Chromium-based browser and re-run" } ],
"checks_passed": [ { "rule_id": "ACC-001", "summary": "No AI crawler is disallowed in robots.txt" } ]
```

Also required at report top level: `site`, `audited_at`, `summary`, plus our
`run_context` block (pages crawled vs discovered, sampling strategy, capabilities,
degradations, time spent) so no finding can be attacked as drawn from three pages.

### Status semantics

- `found` — an observed defect. Requires direct evidence.
- `risk` — evidence is suggestive but incomplete. Never `critical`.
- `proactive` — no defect observed; a strengthening recommendation. Never above
  `medium`, always `P2` or `P3`.

### Mechanism-to-symptom mapping (many-to-many, fixed)

| Skill | invisible | misrepresented | bounce |
|---|---|---|---|
| access-and-indexability | yes | yes | no |
| render-and-extraction | yes | yes | yes |
| identity-and-markup | yes | yes | no |
| answerability | yes | no | yes |
| freshness-and-corroboration | no | yes | no |
| arrival-and-engagement | no | no | yes |

---

## 3. Severity, confidence, impact, priority

Four separate concepts. Severity is **derived**, never hand-assigned.

- **impact** — observed properties: `blocking`, `breadth`, `content_importance`.
- **confidence** — how sure we are the diagnosis is correct.
- **severity** — a pure function of impact, capped by confidence.
- **priority** — severity adjusted by effort; drives the ordering a reader acts on.

Severity is defined on observables only. We cannot observe whether a fix changes
AI citation rates, so severity never encodes predicted AI outcomes.

```python
def severity(impact, confidence):
    blocking = impact["blocking"]                 # prevents a funnel stage entirely
    breadth = impact["breadth"]                   # "site" | "section" | "page"
    primary = impact["content_importance"] == "primary"

    if blocking and breadth == "site" and primary:      base = "critical"
    elif blocking and (breadth in ("site", "section")): base = "high"
    elif not blocking and breadth == "site" and primary:base = "high"
    elif breadth == "section":                          base = "medium"
    else:                                               base = "low"

    cap = {"high": "critical", "medium": "high", "low": "medium"}[confidence]
    return min(base, cap, key=ORDER.index)        # ORDER = ["critical","high","medium","low"]
```

Only a high-confidence finding can ever be `critical`.

```python
def priority(sev, effort, status):
    if status == "proactive":                 return "P3" if effort == "high" else "P2"
    if sev == "critical":                     return "P0"
    if sev == "high":                         return "P2" if effort == "high" else "P1"
    if sev == "medium":                       return "P2"
    return "P3"
```

Both functions are unit-tested with a truth table covering every combination.

---

## 4. Budgets

Global deadline 300s, enforced by the orchestrator. On expiry, whatever has
completed is reported and the rest becomes `not_assessed` with reason
`budget_exhausted`. Never fail the whole run.

| Stage | Budget | On overrun |
|---|---|---|
| robots + sitemap | 15s | continue without sitemap |
| first-party crawl | 90s | stop, report `crawl.fetched` vs `discovered` |
| rendering | 60s, max 3 concurrent renders | remaining pages fetch-only, mark degraded |
| external probe | 90s | partial results, `external.truncated = true` |
| diagnosis + synthesis | 45s | n/a (local, fast) |
