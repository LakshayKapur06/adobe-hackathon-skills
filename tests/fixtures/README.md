# Fixtures

Everything CI runs against. Three kinds of fixture live here, and they are
deliberately kept apart because they answer different questions.

## `site/` — the reference site

A four-file static site: `robots.txt`, `sitemap.xml`, `index.html`,
`about.html`. It is small, well-formed and deliberately unremarkable — valid
canonical, self-consistent JSON-LD with an `Organization` `@id` that the About
page references, a declared language, a sitemap with `lastmod`, dated content,
and its substance in server-side HTML with no client-side hydration.

It exists so that CI always has something real to run against, and so that the
build has, from Day 1, an example of the case that matters most: a site that
should produce almost no findings. A rule set that lights this site up is
measuring conformity rather than defects.

Serve it with any static file server rooted at this directory; the absolute
URLs inside it assume `http://localhost:8000`. The adversarial fixture set — a
JS shell with an empty server response, a 300-product catalogue, a documentation
site, a publisher, a multilingual site, a site that disallows us, a site
returning 5xx — is a Day 5 deliverable per `docs/PLAN.md`, not optional polish.

## `evidence/` and `findings/` — pipeline inputs

`evidence/minimal.evidence.json` is a hand-written bundle for `site/`, kept
because report assembly needs fixed, human-checked input that does not move
when the collector changes. It is schema-valid and internally consistent with
`site/`: the same two URLs, the same counts, the same claim strings. The
collector itself is tested against `site/` served locally, in
`tests/test_collector.py`.

`robots/` holds two robots.txt files modelled on real deployments — a storefront
with a separately named ad-bot group and faceted crawl traps, and a media site
with leading-wildcard, end-anchored and literal-bracket patterns and three
sitemaps. `echo-site/shell.html` is served byte-identical at every path,
`/robots.txt` included, the way a client-rendered site with no server-side
routes behaves.

`evidence/pages/*.txt` are the extracted-text sidecars that the bundle's
`raw.text_path` and `rendered.text_path` fields point at, named by the sha256
of their own contents.

`findings/*.json` are diagnostic outputs in the shape each diagnostic writes.
They carry rule identifiers from rule sets that land on Days 3 and 4. Today they
serve one purpose only: exercising the orchestrator's merge, derivation,
ordering, counting and validation path, and giving the determinism check
something with real structure to compare. They are not evidence that any rule
exists yet.

## `schema/` — conformance vectors

`schema/valid/` and `schema/invalid/` are hand-built instances that assert the
schemas actually reject what they are supposed to reject. Each invalid vector
isolates exactly one violation, and its filename names the violation. A schema
that accepts everything is not a contract, and these vectors are what stops it
quietly becoming one — particularly the `unknown-field` vectors, which are the
anti-hallucination guard: an invented evidence field must fail the build.
