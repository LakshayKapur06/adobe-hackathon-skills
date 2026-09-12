# robots.txt — the exact semantics the collector applies

Every access verdict in the report rests on this file being read correctly. A
wrong verdict here is not a small error: it becomes a confidently wrong critical
finding, or a crawl the site owner forbade. The collector therefore follows
RFC 9309 exactly, and `scripts/robots.py` is tested case by case against the
behaviours below.

## Reading the file

- **Only five directives have any effect:** `User-agent`, `Allow`, `Disallow`,
  `Crawl-delay` and `Sitemap`, with keys matched case-insensitively. Every other
  line is dropped.
- **Comments are neither obeyed nor recorded.** A robots.txt is read as a
  grammar, not as prose. Text in a comment addressed to "AI agents" — and at
  least one widely deployed storefront template carries such text — is a
  comment like any other.
- **A group** is one or more consecutive `User-agent` lines followed by rules.
  Rules that appear before any `User-agent` line belong to no group and are
  ignored. `Sitemap` lines are file-global.
- **A leading byte-order mark and CRLF line endings** are tolerated.

## Which group applies

1. A crawler is identified by its product token, compared case-insensitively.
   `User-agent: GPTBot/1.1` names `GPTBot`. RFC 9309 asks crawlers to choose
   tokens of letters, underscores and hyphens; digits are accepted too, because
   real crawlers carry them — `User-agent: MJ12bot` names MJ12bot, and reading
   it as `MJ` would apply that group to nobody.
2. **A group naming the crawler wins.** If several groups name it, their rules
   are merged into one.
3. **Otherwise the `*` group applies.** A crawler covered only by `*` is
   `allowed` or `disallowed` according to that group.
4. **`unspecified` means no group applies at all** — no group names the
   crawler and there is no `*` group. It is never reported for a crawler a `*`
   group covers.
5. **A similar name is a different product.** `adsbot-google` does not govern
   `Googlebot`, and a `GPTBot` group does not govern `OAI-SearchBot`. Matching is
   exact on the token, never by substring.
6. A crawler with a documented fallback, such as `Googlebot-Image` to
   `Googlebot`, is checked most specific first.

The per-crawler verdict recorded in `robots.ai_agents` is taken at the site
root, `/`. The groups are also recorded verbatim, one entry per `User-agent`
line, so any finer question — is `/products/` open to this crawler? — can be
answered from the evidence without re-fetching.

## Which rule applies

- **The longest matching pattern wins**, measured in octets.
- **An `Allow` and a `Disallow` of equal length resolve to `Allow`.**
- **An empty value is no rule:** `Disallow:` permits everything.
- `*` matches any sequence of characters, including none, anywhere in the
  pattern — leading `*` included.
- A `$` at the end of a pattern anchors it to the end of the path. A `$`
  anywhere else is literal.
- **Every other character is literal,** including brackets: `/[slug]/` matches
  those seven characters, not a character class.
- The path matched includes the query string: `/collections/*sort_by*` catches
  `/collections/shoes?sort_by=price`.
- Percent-escapes compare case-insensitively, so `%2b` and `%2B` are the same
  octet, and non-ASCII characters are compared as their UTF-8 escapes.
- `/robots.txt` itself is always allowed.

## What the fetch outcome means

| Outcome | Meaning | Effect |
|---|---|---|
| 2xx, a real robots file | Parsed | Rules apply as above |
| 2xx, not a robots file | Treated as absent | No restrictions; reason recorded in `errors[]` with stage `robots` |
| 4xx | Absent (RFC 9309 2.3.1.3) | No restrictions; every AI crawler recorded `unspecified` |
| 429 | Unreachable | Full disallow. A rate-limit signal is not permission to crawl freely |
| 5xx, timeout, no response | Unreachable (RFC 9309 2.3.1.4) | Full disallow. The crawl does not start, and the report says it could not proceed |
| More than five redirects | Absent (RFC 9309 2.3.1.2) | No restrictions |

**"Not a robots file"** exists because some sites answer every path with the
same HTML shell, `/robots.txt` included. The body decides:

- An empty body is a legitimate empty file.
- A body that begins like an HTML document is not a robots file, whatever text
  it happens to contain.
- Anything else must contain at least one directive line.

A body of genuine directives served with a `text/html` content type is accepted:
treating a mislabelled but real file as absent would crawl paths its owner
disallowed, which is the worse error.

## How the collector obeys it

- The collector identifies itself honestly, with the product token
  `agent-readiness-audit`. Sites rarely name it, so in practice the `*` group
  governs the audit's own requests.
- Every URL is checked before it is requested: sampled pages, sitemap files, the
  soft-404 probe paths and the three agent-facing discovery files.
- `Crawl-delay` in the governing group sets the minimum interval between
  requests to that host.
