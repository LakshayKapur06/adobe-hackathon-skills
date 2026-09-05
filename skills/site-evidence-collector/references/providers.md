# Corroboration providers — and the coverage bound we state out loud

Off-site corroboration matters because machines treat a fact as more trustworthy
when independent places agree on it, and because mistaken identity — several
things sharing a name — is resolved by what the wider web says, not by what the
brand's own pages say. A site-only auditor cannot see either phenomenon.

Every provider writes the identical `external` schema. Nothing downstream
branches on which provider answered, except the `external.method` label and a
confidence gate.

## The keyless set — always available, no configuration

| Provider | What it establishes | Cap |
|---|---|---|
| Wikidata (`wbsearchentities`, then entity fetch) | Whether the entity exists as a distinguishable node, and what identifiers and claims are attached to it | 15s |
| Wikipedia / MediaWiki API | Encyclopedic description and its currency | 15s |
| Wayback CDX | First-seen date, snapshot cadence, digest-change frequency | 20s |
| Declared `sameAs` target verification | Whether the profiles the brand points to actually exist and actually name it back | 20s |
| Linked-press verification | Whether press the brand links to says what the brand says | 20s |
| Common Crawl index | Best-effort corpus presence | 10s hard, never blocking |

**Wayback, stated precisely.** CDX returns snapshot timestamps and content
digests, and a digest changes on any byte, including a rotating token or a
timestamp in the footer. It is therefore used for coarse signals only —
first-seen date, cadence, change frequency. At most two snapshots are fetched,
for the single highest-value claim, to diff extracted text. Treating a digest
change as a content change would manufacture freshness findings out of cache
busters.

**Independence, counted honestly.** Before breadth is computed, syndication
clusters are collapsed to one origin and brand-owned origins are excluded. A
single press release republished across twelve outlets is one independent
source, not twelve, and reporting it as twelve would be the most flattering lie
this audit could tell.

## Host-volunteered search

No script can detect what tools its host agent has. So this tier is
agent-volunteered, stated in the collector's instructions rather than probed
for: if the host agent has a web-search capability, it runs the query panel and
writes results into the same `external` schema; otherwise it skips, and
`external.method` records which happened. There is no failure mode here — only a
recorded difference in coverage.

## The coverage bound, stated in the report and never hidden

Without privileged search access we do not have open-web recall. Breadth is
measured over an **enumerable frontier**: encyclopedic entries, the profiles the
brand itself points to, the press it links, and its own archived history.
`external.frontier_size` is that frontier, and it is the denominator of every
breadth statement we make.

This means a corroboration finding may legitimately be read as "within the
sources we could enumerate", and it must be worded that way. No finding may
imply we searched the open web. An absent corroboration is reported as
`not_assessed` or as a `risk`, never as a confirmed absence — absence of
observation is not observation of absence.

## Failure behaviour

Any provider that is invalid, rate-limited, slow or unreachable is recorded in
`run_context.corroboration.provider_unavailable` and the audit continues. A
third party's bad day is not an audit failure. If egress is unavailable
altogether, `external.attempted` is false, every corroboration rule becomes
`not_assessed`, and the entire on-site half of the audit still runs and still
produces a complete report.
