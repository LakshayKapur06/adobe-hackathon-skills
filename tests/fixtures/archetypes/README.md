# Fixture archetypes — the evidence that the audit generalises

Five small sites, each standing for a class of real website, run through the
whole audit exactly as a live site is: collector, claim promotion, second pass,
six diagnostics, arbitration, report. `tests/test_archetypes.py` serves each one
locally and asserts on the final report. Every site here is fictional.

A fixture that only makes rules fire proves nothing about generalisation, so each
variant asserts in four directions:

| Assertion | Catches |
|---|---|
| every expected finding is present, with its status, severity, confidence, breadth and `conditional_on` | a false negative, or a right finding at the wrong severity |
| **no other finding is present** | a false positive; each archetype carries legitimate patterns placed there to tempt one |
| named rules are assessed **and pass** | a true negative that is really a silent `not_assessed` |
| named rules are `not_assessed` | a rule running on evidence it does not have |

Every variant also requires a schema-valid report in which every one of the 22
rules reaches exactly one outcome, and several assert literal bundle values so a
finding only counts when the observation beneath it is also right.

## The five

| Archetype | Real-world class | What it proves |
|---|---|---|
| `healthy-minimal` | a small, well-built organization site | a well-built site produces no defect or risk; 17 rules assessed and passing without a browser, 9 checked as passing with one |
| `spa-shell` | a client-rendered site answering every path with one shell (the G2 storefront class) | the empty server response is found with and without a browser, at critical, and the markup finding it explains is marked conditional |
| `storefront-defects` | a hosted e-commerce store with theme-level mistakes | template defects are found at template scope beside legitimate look-alikes |
| `publisher-docs` | a content-heavy publisher with documentation and a slow origin | content defects are found while every text metric the audit rejected stays silent |
| `crawler-restricted` | a site that allowlists named crawlers, or whose robots.txt is failing | the auditor requests nothing but `/robots.txt`, yet reports what the policy costs |

## Rule coverage

`TP` means the archetype must produce the finding. `TN` means the rule must be
assessed and pass there. `R` marks a variant that needs a browser; without one
it is skipped with the reason, and the no-browser variants still run.

| Rule | healthy-minimal | spa-shell | storefront-defects | publisher-docs | crawler-restricted |
|---|---|---|---|---|---|
| ACC-001 crawler shut out by `*` | TN | TN | TN | TN | **TP** allowlist |
| ACC-002 robots.txt 5xx or 429 | TN | | | | **TP** robots-503, TN allowlist |
| ACC-003 noindex on a primary template | TN | | **TP** | TN | |
| ACC-004 nosnippet on a primary template | TN | | TN | **TP** | |
| ACC-005 canonicals collapsed to home | TN | **TP** R | TN | TN | |
| ACC-006 named crawler refused by user agent | TN | | **TP** | TN | |
| ACC-007 advertised URLs return errors | TN | TN R | **TP** | TN (one dead link) | |
| ACC-008 retrieval crawler excluded by name | TN | TN | | | **TP** allowlist |
| ACC-009 declared sitemap unreadable | TN | | TN | **TP** | |
| RND-001 text only after JavaScript | TN R | **TP** R | TN R | | |
| RND-002 no server text, nothing rendered | TN | **TP** | TN | TN | |
| RND-003 prices only after rendering | | | **TP** R | | |
| IDM-001 no organization identity | TN | **TP**, conditional | TN | TN | |
| IDM-002 empty sameAs | TN | | **TP** | TN | |
| IDM-003 JSON-LD that fails to parse | TN | | TN | **TP** | |
| IDM-004 markup price contradicts page | | | **TP** | | |
| ANS-001 long pages without sections | TN | | | **TP** | |
| FRC-001 undated articles | TN | | | **TP** | |
| ARR-001 slow server response | TN | TN R | TN | **TP** | |
| PRO-001 optional /llms.txt | TN (file present) | TP | TP | TP | |
| PRO-002 monitoring prompt panel | TP | | TP | TP | |
| PRO-003 organization markup without identity links | TN (sameAs declared) | | TN (empty sameAs is IDM-002) | **TP** | |
| PRO-004 visible dates without structured dates | TN | | | **TP** | |

**Not covered end to end: FRC-002**, the founding year against Wikidata. It
needs the second pass to reach Wikidata, and a fixture run cannot, by design:
the archetypes run without egress so that nothing outside the machine can vary
a result. It is covered instead by `tests/test_freshness_rules.py` (the rule over
bundles) and `tests/test_corroboration.py` (the second pass with a faked network,
including the Wikidata identity check), and it fired on a real site during
development.

## The traps

Each of these is a real pattern the build met or measured, and each must produce
nothing:

- **storefront-defects:** noindexed collection pages (deliberate consolidation),
  `max-snippet:-1` (no limit), an `aria-modal` cart dialog hidden in every page,
  a review widget that hydrates onto two product pages.
- **publisher-docs:** long news articles with a single heading (house style), one
  dead link in the sitemap (ordinary rot), a `paywall-container` class around
  fully served text, a privacy page written as one `<br>`-separated block, two
  `h1` elements on one page, `display:none` footer text, noindexed tag archives,
  navigation repeated in header and footer.
- **healthy-minimal:** long documentation that is properly sectioned, dated
  posts, self-referencing canonicals, an `/llms.txt` that exists.
- **spa-shell (no browser):** four more routes that do exist but are served the
  same shell, which must not become four duplicate pages.

## Also tested here

- **Robots compliance of the auditor itself.** The crawler-restricted variants
  record every request the server receives and require it to be `/robots.txt`
  alone.
- **Scripts read only their declared evidence.** Every diagnostic and the
  proactive step are run over real archetype bundles with every field read
  recorded, and each read must fall inside that skill's allow-list. `check.py`
  proves the rule text names only allowed fields; this proves the code does too.
- **The committed sites are exactly what `generate.py` produces**, so a fixture
  cannot be hand-edited out of step with its generator.
