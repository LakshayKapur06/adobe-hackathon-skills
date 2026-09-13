# Corroboration providers — and the coverage bound we state out loud

Off-site corroboration matters because machines treat a fact as more trustworthy
when independent places agree on it, and because mistaken identity — several
things sharing a name — is resolved by what the wider web says, not by what the
brand's own pages say. A site-only auditor cannot see either phenomenon.

Every provider writes the identical `external` schema. Nothing downstream
branches on which provider answered, except the `external.method` label.

## The keyless set — no configuration, and every host's robots.txt obeyed

The second pass is seeded by the canonical claims `identity-and-markup` promoted,
and it runs only if at least one claim was promoted. Each provider was chosen by
reading its host's robots.txt first, because an audit that grades sites on
crawler policy does not get an exception for itself.

| Provider | Route | What it establishes |
|---|---|---|
| Wikipedia | Search through `api.wikimedia.org`, then read at most three matching articles | Whether an encyclopedic article about *this* brand exists: an article counts only if its Wikidata entity names the audited domain as official website, or, failing that, if the article links the domain. A namesake is recorded as looked at, and is not evidence |
| Wikidata | The entity id the Wikipedia article itself names, then `Special:EntityData/{id}.json` | Identity settled by the record's official-website property, and structured statements to compare with the site's claims: the label against the claimed name, the inception date against the claimed founding year |
| Declared `sameAs` profiles | Each URL the site's own markup declares, at most eight | Whether the profiles the brand points at exist and name it back |
| Wayback CDX | One query for the origin's first archived snapshot | The first year anyone archived the site, a bound on a founding claim from one side only |

**Routes that were checked and are not used.** Every endpoint that can *search*
Wikidata — `/w/api.php`, `/w/rest.php`, `Special:Search` and
`query.wikidata.org/sparql` — is disallowed to crawlers, so Wikidata is reached
only through the id a permitted Wikipedia article supplies. Common Crawl's index
endpoint is disallowed, and DBpedia's data endpoints are disallowed, so neither
is used. RDAP domain registration dates are permitted but were cut, because a
registration date can neither confirm nor deny a founding year and would have
produced authoritative-looking verdicts carrying no information.

## What a hit means, and what it does not

`external.hits[].matches_current` records whether a source asserts the claimed
value. `false` is not, on its own, a disagreement: a Wayback first-snapshot year
does not assert a founding year, a Wikidata label is a common name that may
legitimately differ from a legal name, and a social profile may simply refuse an
automated client. `freshness-and-corroboration` therefore compares only
like-for-like structured values, and its rules file explains which.

**Independence, counted honestly.** Every origin is marked `brand_owned` when it
is the audited domain, so a brand's own pages never count as corroboration. The
schema also carries `syndication_cluster`, for collapsing a press release
republished twelve times to one source; none of the keyless providers can detect
syndication, so it is always null here, and no rule measures breadth as a
result.

## Host-volunteered search

No script can detect what tools its host agent has. So this tier is
agent-volunteered: if the host agent has a web-search capability, it may run
queries about the canonical claims and write the results into the same
`external` schema; otherwise it skips, and `external.method` records which
happened. There is no failure mode here, only a recorded difference in coverage.

## The coverage bound, stated in the report and never hidden

Without privileged search access we do not have open-web recall. Breadth is
measured over an **enumerable frontier**: encyclopedic entries, the profiles the
brand itself points to, and its own archived history. `external.frontier_size`
is that frontier, and the report states it next to every corroboration
statement.

A corroboration finding is therefore worded as "within the sources we could
enumerate". No finding may imply we searched the open web, and an absent
corroboration is reported as `not_assessed`, never as a confirmed absence.

## Failure behaviour

A provider that is slow, refuses, or is unreachable costs only its own hits: the
probe continues with the next, and `external.truncated` is set if the 90s
budget runs out. If egress is unavailable altogether, `external.attempted` is
false, every corroboration rule becomes `not_assessed`, and the whole on-site
half of the audit still runs and still produces a complete report. The second
pass failing never fails the run.
