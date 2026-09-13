# Rule review log

Static review of every rule block before it ever runs against a real site.
Five tests, in order. Each is a hard stop: fail one, reject, stop reading.

| Test | What it asks | Reject when |
|---|---|---|
| 1 Mechanism | Does it explain *causally* why this affects a machine reaching, reading, retrieving or quoting — or a visitor orienting? | "Best practice", "industry standard", "Google recommends", "improves SEO", "signals quality", "users expect". Convention is not mechanism |
| 2 Threshold | Is there a number, and does the justification explain *why that number*, referencing how real sites vary? | Circular justification ("three is a reasonable minimum"). If you cannot tell what would change were the number doubled, it is not justified |
| 3 Minimum evidence | What happens when data is thin? Exactly three legal outcomes: fire, `checks_passed`, `not_assessed` | The rule treats "we did not observe it" as "it is fine". That is a clean bill of health for an unexamined site |
| 4 False positives | Name a real site where the signal is present and the site is fine. Would the listed controls stop it firing? | The exception you thought of is missing, or is listed but not *detectable from evidence*. Undetectable exceptions are decoration |
| 5 Remediation | Read only what/where/why/how/mechanism/success_criteria | It would paste into an unrelated case study, or `success_criteria` names nothing observable |

Cross-cutting, checked per skill once its rules are complete:

- **Impact inputs derived, not asserted.** The block must say *how* `breadth` is computed from evidence, not simply declare it.
- **`severity` appears nowhere in the block.** It is derived by the orchestrator. A rule assigning it is a contract violation.
- **Overlap.** Does any rule reach the same conclusion from the same evidence fields as a rule in another skill? Two rules on one root cause is the duplication a judge calls padding. One becomes evidence on the other.

---

## Log

| rule_id | skill | test failed | what I said | outcome |
|---|---|---|---|---|
| ACC-001 | access | 4 False positives | robots.py records every agent `disallowed` when robots.txt is 5xx/429/unreachable, so a policy rule reading only `ai_agents` would report an outage as a crawler policy | tightened: requires `parse_reason == "ok"`; outage case moved to ACC-002 |
| ACC-001 | access | 4 False positives | a publisher naming PerplexityBot in its own group has made a licensing decision; calling it a defect is FP-EXC on every publisher that opts out | tightened: named-group exclusions never fire, reported in `checks_passed` instead |
| ACC-001 | access | 3 Minimum evidence | first draft sent `absent_4xx` / `not_plausibly_robots` to `not_assessed`, but RFC 9309 settles those as "no restrictions" | tightened: those emit `checks_passed` |
| ACC-001 | access | cross-cutting | first draft lowered confidence and narrowed breadth for re-allowed paths, penalising one fact twice | tightened: breadth only |
| ACC-006 | access | 4 False positives | edges that refuse requests *claiming* Googlebot/GPTBot from unpublished addresses admit the real crawler; the probe cannot present a network origin | tightened: `risk`, confidence low always, Googlebot excluded, 429/5xx excluded, remediation starts at the server logs |
| ACC-006 | access | 4 False positives | all identities refused (gadgets360 specimen) says nothing about real crawlers | tightened: `not_assessed` |
| ACC-003 | access | 4 False positives | `noindex` on archive/facet listings is deliberate consolidation; a single `noindex` article is editorial | tightened: `category` not primary; per-type 2-page and 50% floor; canonical-elsewhere pages excluded |
| ACC-004 | access | 4 False positives | a paywalled publisher may permit indexing but not reproduction; the markup cannot tell that from a template error | tightened: confidence capped at medium; never on a page ACC-003 already covers |
| ACC-005 | access | 4 False positives | first idea (any 3 pages sharing a non-self canonical) fires on legitimate product-variant consolidation | tightened: only canonicals naming the site root, same registrable domain, root aliases excluded |
| ACC-007 | access | 4 False positives | 401/403/429 are refusals to this client, not dead URLs | tightened: excluded; 5xx lowers confidence |
| ACC-002 | access | 1 Mechanism | fact check: the drafted mechanism said a 5xx robots.txt closes the site outright; Google pauses 12h then uses its last good copy, and RFC 9309 never names 429 | tightened: mechanism rewritten to the documented behaviour; stays `risk`/low |
| (cut) redirect chains | access | 1 Mechanism | no documented hop limit for any AI crawler; Googlebot follows up to ten. Would be "best practice" | cut |
| (cut) hreflang reciprocity | access | 1 Mechanism | evidence holds locale codes only, not target URLs, so reciprocity cannot be checked; locale selection has no documented AI-retrieval effect | cut |
| (cut) canonical host/scheme mismatch | access | 4 False positives | www-vs-apex canonical is harmless when the other host redirects here, which is unobservable; a `risk` at low confidence would carry no information | cut |
| (cut) UA text-length drop | access | 2 Threshold | same-status, shorter body for a bot has no threshold separating dynamic content from cloaking, and serving bots a prerendered page is the opposite defect | cut |
| ACC-009 | access | allow-list | needed `sitemaps[].status`, `sitemaps[].parse_ok`, `sitemaps[].url`, outside the allow-list | allow-list amended in `contracts-v3` (D17); written with only robots-declared URLs counted, null statuses and client refusals excluded |
| ACC-008 | access | 3 Minimum evidence | a named retrieval-crawler exclusion was filed under `checks_passed`, which reads as a miss to anyone who knows the site blocks that assistant | added as `proactive`; honest impact inputs, severity capped at medium by `contracts-v3` (D17) |
| (budget) | access | cross-cutting | 9 rules, one over the 5-8 target. ACC-008 is the policy half of ACC-001 and ACC-009 was a DECISIONS-assigned mechanism blocked only by the allow-list; nothing was written to reach a number | accepted over target, under the 12 ceiling |
| (cut) `llms.txt` absent | access | scope | never a defect (DECISIONS exclusions); a proactive item, which the orchestrator's proactive step owns | moved to orchestrator step 2 |
| RND-001 | render | 2 Threshold | first idea was delta_ratio >= 0.5; measured G2 pages put hydrated Shopify product templates at 0.04-0.24 and server-rendered templates at <= 0.015, shells at 1.0 | tightened: 0.8 plus a 200-character gain, per-type 50% share, home alone; the lone `/subscribe` page on a publisher does not fire |
| RND-001 | render | 3 Minimum evidence | pages outside the render budget have no delta and must not dilute or pad the share | tightened: excluded from both counts, stated in the evidence |
| RND-002 | render | cross-cutting | the no-browser shell and RND-001 describe one root cause | tightened: RND-002 applies only when no page was comparable, otherwise `not_assessed` naming RND-001 |
| RND-002 | render | 4 False positives | a CDN block page is recorded empty on purpose and would read as a shell | tightened: 2xx HTML home page required |
| RND-003 | render | 4 False positives | a related-products carousel rendered on the server would hide a hydrated main price, and a price in both texts is not a defect | tightened: any server-side price token or offers.price/lowPrice JSON-LD excludes the page; kept to RULE_FORMAT's worked-example numbers |
| (cut) facts locked in images | render | 4 False positives | `text_likely` is a filename/alt keyword match; `pricing-hero.jpg` and `menu-icon.svg` match | cut: not detectable from evidence |
| (cut) PDFs, canvas, iframes | render | 3 Minimum evidence | the collector records no PDF or canvas at all and only an iframe count, with no content | cut |
| (cut) interaction-gated facts | render | 3 Minimum evidence | the collector never clicks, by design and by the handout; an interaction-gated fact is unobservable | cut |
| (budget) | render | cross-cutting | 3 rules, under the 5-8 target: every cut above failed on evidence, and nothing was added to reach a number | accepted |

Measured on real bundles before commit: POCO fires RND-001 site-wide (5/5, delta 1.0) with a browser and RND-002 at high confidence without one; iflexbtw, indianexpress and python.org fire nothing; the refused publisher is not assessed on all three.
| IDM-001 | identity | 4 False positives | an Organization subtype list can never be complete, so a Winery or Dentist site would read as having no identity | tightened: any node with logo or sameAs, or a nested publisher organization, counts; an about page or a Person node satisfies it; microdata or RDFa is not_assessed |
| IDM-001 | identity | cross-cutting | JSON-LD is parsed from the server response, so on a client-rendered site (POCO) the absence may be a render gap | kept, stated in the rule's definitions; the orchestrator's arbitration must mark it conditional on RND-001/RND-002 |
| IDM-002 | identity | 4 False positives | values is capped at 4KB with long values dropped first, so a truncated sameAs would read as empty; and the self-description test counts any node with sameAs | tightened: truncated values excluded, strictly organization types only |
| IDM-003 | identity | 4 False positives | "missing @type" is legal JSON-LD for a node typed where its @id is referenced | tightened: parse failures only, identified by structure rather than error text |
| IDM-004 | identity | 4 False positives | server-side currency conversion or a default variant can make markup and visible price differ legitimately | tightened: confidence medium on a single page; relies on the collector's narrow definition |
| (cut) name-collision risk | identity | 1 Mechanism | promote.py's entity_ambiguity is a string-shape heuristic with no observation of an actual collision; a finding on it would be confident output carrying no information | cut; ambiguity still gates corroboration confidence |
| (cut) markup completeness beyond identity (Product without offers, Article without author) | identity | 1 Mechanism | completeness to a vendor's recommended property list is convention, and a missing Product price is already RND-003's fact when it matters | cut |
| (cut) trust and provenance affordances | identity | 3 Minimum evidence | no typed evidence field records authorship, contact or policy affordances beyond page_type | cut |
| (budget) | identity | cross-cutting | 4 rules, under the 5-8 target; every cut above failed a test | accepted |

Measured on real bundles before commit: iflexbtw fires IDM-002 (29 of 30 pages, nine empty sameAs entries); python.org fires IDM-001 (home carries only WebSite); indianexpress passes all four; the refused publisher is not assessed on all four.
| (cut) boilerplate dominance | answerability | 2 Threshold | boilerplate_ratio counts only nav/aside/landmark text and spanned 0.0-0.93 on healthy sites (python.org listings 0.8-0.93, 700-word news articles 0.69); no number separates defect from markup habit | cut |
| (cut) passage / chunk length | answerability | 4 False positives | longest_block_words treats `<br>` as a space, so a line-break-formatted policy page read as one 3,036-word block | cut; would need an extraction change and re-measurement first |
| (cut) heading architecture counts, multiple h1 | answerability | 1 Mechanism | multiple h1 is valid HTML and common (13 on one python.org page); a count tests conformity | cut |
| (cut) query-intent coverage | answerability | 3 Minimum evidence | W1's evidence gate (a structured attribute with no page answering by it) has no observable counterpart in the bundle; PLAN.md's first cut | cut |
| ANS-001 | answerability | 1 Mechanism | section headings aid passage retrieval but no operator documents a penalty for their absence | written as proactive at medium confidence; news article types excluded as house style |
| (budget) | answerability | cross-cutting | 1 rule. The skill keeps a distinct mechanism, but the collector's text metrics cannot carry defect-level rules; flagged to the user rather than padded | accepted, flagged |
| FRC-001 | freshness | 4 False positives | blog indexes classify as article at 0.6 while real articles score 0.9; visible_dates include sidebar dates; a client-rendered shell returns one Last-Modified for every URL | tightened: classifier confidence >= 0.8, any visible date counts, HTTP Last-Modified never accepted |
| FRC-002 | freshness | 4 False positives | matches_current is false for Wayback first-snapshot years, Wikidata labels vs legal names, and refused social profiles, none of which is a disagreement | tightened: only wikidata.org founding-year hits compared; risk, never found, because the two years may describe different events |
| (cut) external breadth and agreement rate | freshness | 3 Minimum evidence | the only real run reaching pass 2 had a frontier of one Wayback snapshot; a rate over that implies recall we do not have | cut |
| (cut) unsupported-claim inventory | freshness | 3 Minimum evidence | a claim with no hit in an enumerable frontier is unchecked, not unsupported | cut |
| (cut) sitemap lastmod absence | freshness | 4 False positives | lastmod_present_ratio cannot tell a sitemap index, which legitimately omits lastmod, from a urlset | cut |
| (collector bug) sameAs list read as one URL | collector | observation | external.py treated the " | "-joined sameAs value as a single URL and recorded a broken identity link the site never had | fixed in 3149cb4 with a test, before any rule read it |
| (budget) | freshness | cross-cutting | 2 rules; every cut failed on evidence | accepted |
| (cut) content-obstructing interstitials | arrival | 4 False positives | obstructions is a class/attribute marker: `paywall` matched nine fully served 2,000-word articles, `aria-modal` matched a hidden cart drawer on 29 of 30 pages | cut |
| (cut) orphans and depth from home | arrival | 3 Minimum evidence | computed within the ~30 sampled pages only, so a page linked from any unsampled page reads as an orphan | cut |
| (cut) deep-link anchors | arrival | 1 Mechanism | text fragments (#:~:text=) address a passage without any id in every current major browser | cut |
| (cut) task completability, above-the-fold completeness | arrival | 3 Minimum evidence | the collector never clicks, submits or renders the page as a visitor sees it after load; form counts miss button-driven purchases | cut |
| ARR-001 | arrival | 4 False positives | client distance and a fresh TLS connection per request inflate TTFB against a returning browser | tightened: median against web.dev's poor boundary, risk at low confidence, remediation starts with field data |
| (budget) | arrival | cross-cutting | 1 rule; the engagement half of the audit is thin on observable evidence, flagged to the user rather than padded | accepted, flagged |

Fact check against operator documentation, 2026-09-13:

| claim | source | result |
|---|---|---|
| OAI-SearchBot = ChatGPT search, GPTBot = training, settings independent, IP ranges published | OpenAI crawler docs | confirmed |
| PerplexityBot = search index, not training; IP ranges published | Perplexity crawler docs | confirmed |
| ClaudeBot = training; Claude-SearchBot is Anthropic's search crawler | Anthropic help centre | confirmed; Claude-SearchBot is not in the tracked seven, recorded as a limit in the definitions |
| Google-Extended does not govern Search AI features | Google "AI features and your website" | confirmed |
| nosnippet / max-snippet:0 govern AI Overviews and AI Mode input | Google robots meta docs | confirmed, stronger than drafted; ACC-004 mechanism now quotes it |
| `none` = noindex, nofollow; X-Robots-Tag may be scoped to a user agent | Google robots meta docs | confirmed |
| robots.txt 5xx means "crawl nothing" | RFC 9309 2.3.1.4; Google robots.txt spec | RFC confirmed; Google pauses 12h then uses last good copy up to 30 days. ACC-002 mechanism corrected, it overstated the effect |
| robots.txt 429 means "crawl nothing" | RFC 9309; Google robots.txt spec | RFC is silent; Google excepts 429 from the 4xx "no robots.txt" rule and groups it with 5xx. ACC-002 now says exactly that |
| Google documents verifying real Googlebot | Google "Verifying Googlebot" | confirmed |
| Organization markup is used to disambiguate the organization, recommended on the home page or about page | Google Organization structured data docs | confirmed; IDM-001 quotes it |
| sameAs is a URL unambiguously indicating identity | schema.org/sameAs | confirmed, expected type URL; IDM-002 quotes it |
| structured data must represent visible page content | Google structured data general guidelines | confirmed; IDM-004 quotes it |
| Google estimates page dates from several signals and recommends a visible labelled date plus datePublished/dateModified | Google "Influence your byline dates" | confirmed; FRC-001 follows it |
| TTFB good <= 0.8 s, poor > 1.8 s, and it precedes FCP and LCP | web.dev "Time to First Byte" | confirmed; ARR-001 quotes it |

Author static review only. The user reviewed the open decisions on
2026-09-13 (named opt-outs, the sitemap allow-list, Claude-SearchBot) and
approved the `contracts-v3` amendments; no real-site specimens were available,
so true-positive evidence for each rule comes from the step 3 fixtures.

## Accepted without change

| rule_id | skill | note |
|---|---|---|

## Adjudication fixes (D30)

| Rule | Verdict | Pattern | Change | Test |
|---|---|---|---|---|
| ACC-006 | FP-INT | Bot management refusing every unverifiable declared crawler, Googlebot included | `not_assessed` when Googlebot is refused on the same URLs | `test_access_rules.TestACC006.test_googlebot_refused_too_reads_as_verification_not_a_block`; archetype `storefront-defects / bot-verification-edge` |
| IDM-001 | FP-EXC | Subdomain of an organization whose identity is on its main domain | `not_assessed` on a non-`www` subdomain, naming the main domain | `test_identity_rules.TestIDM001.test_a_subdomain_defers_to_its_main_domain` |
| RND-001 | TP, label | One client-side application filed under several URL-inferred page types | Title, evidence and where name the shared path | `test_render_rules.TestRND001.test_a_shared_path_names_the_application_not_the_guessed_type` |
