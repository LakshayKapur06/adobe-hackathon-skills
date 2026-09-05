# RULE_FORMAT.md — the canonical rule block

Every detection rule in every diagnostic skill is written in this exact block,
in that skill's `references/rules.md`. One engineering vocabulary across six
skills, not six voices.

This matters more than it looks: the handout says submissions are evaluated on
the marketplace itself, so these reference files are a primary deliverable. A
judge flipping between skills should see the same disciplined shape every time.

CI validates that every block has all fourteen fields present and non-empty, and
that every field named under **Evidence read** exists in
`docs/CONTRACTS.md`. A rule referencing a schema field that does not exist is a
build failure. That check is what makes fabricated evidence impossible.

---

## Template

```markdown
### <RULE_ID> — <one-line name>

- **Mechanism:** why this actually affects discovery, retrieval, citation or
  engagement. One or two sentences, causal. Not "best practice".
- **Signal:** the observable condition, stated precisely enough to implement.
- **Evidence read:** exact `evidence.json` field paths this rule consumes.
- **Threshold:** the numeric or boolean trigger, **with a one-line justification
  for the number.** An unexplained threshold is a build failure.
- **Minimum evidence:** what must be observed before this rule may fire at all.
  If unmet, emit nothing (not a low-confidence finding).
- **False-positive controls:** the specific checks applied before firing.
- **Legitimate exceptions:** cases where the signal is present and the site is
  fine. Each must be detectable, or the rule is gated tighter.
- **Confidence:** high | medium | low, and what drives it up or down.
- **Impact inputs:** `blocking`, `breadth`, `content_importance` and how each is
  derived from evidence. Severity is computed from these, never hand-assigned.
- **Status:** found | risk | proactive.
- **Symptom tags:** invisible | misrepresented | bounce.
- **Remediation:** what / where / why / how / mechanism improved.
- **Success criteria:** the observable that would change if the fix worked.
- **Effort:** low | medium | high.
```

---

## Worked example

```markdown
### RND-002 — Primary commercial fact absent from server HTML

- **Mechanism:** retrieval and quoting operate on the fetched response. A price
  that exists only after client-side hydration cannot be extracted by a fetcher,
  so it cannot appear in an assistant's answer even though a human sees it.
- **Signal:** a price token is present in `rendered.text` and absent from
  `raw.text` on pages classified as `product`.
- **Evidence read:** `pages[].raw.text_len`, `pages[].rendered.available`,
  `pages[].rendered.delta_ratio`, `pages[].jsonld[].fields_present`,
  `pages[].page_type`, `pages[].page_type_confidence`.
- **Threshold:** fires when the pattern holds on >= 60% of sampled product pages
  with `page_type_confidence >= 0.6`. Chosen because a minority of pages showing
  the pattern usually indicates template variance or a single promo page rather
  than a template-wide defect; 60% is the point at which the template itself is
  implicated.
- **Minimum evidence:** `rendered.available == true` on at least 5 product
  pages. Without a browser this rule emits `not_assessed`, never "no problem".
- **False-positive controls:** currency and separator normalisation before
  comparison; exclude pages whose JSON-LD already exposes `offers.price` in the
  server response, since the fact is then machine-readable regardless of the
  visible DOM; exclude pages returning non-200.
- **Legitimate exceptions:** quote-on-request or B2B pricing models (detected by
  absence of any price token in both raw and rendered across all products);
  region-gated pricing (detected by a currency or region selector in
  `obstructions`).
- **Confidence:** high when >= 8 product pages sampled and JSON-LD also lacks
  price; medium when the sample is 5-7 pages; never low (below 5 it does not fire).
- **Impact inputs:** `blocking = true` (the fact cannot reach extraction at all);
  `breadth = "site"` when the affected pages span >= 2 URL patterns, else
  `"section"`; `content_importance = "primary"` for product pages.
- **Status:** found
- **Symptom tags:** invisible, misrepresented
- **Remediation:** server-render or prerender price and availability in the
  product template, or emit them in `Product`/`Offer` JSON-LD in the server
  response. Where: the product page template. Why: puts the fact in the fetched
  response. How: SSR, static generation, or server-side JSON-LD injection.
  Mechanism improved: extraction and quotability.
- **Success criteria:** the price string appears in the raw server response for
  100% of sampled product URLs, verifiable with a plain fetch and no JS.
- **Effort:** medium
```

---

## Anti-patterns — reject these in review

| Anti-pattern | Why it fails |
|---|---|
| "Add more content" / "improve SEO" / "improve UX" | Not mechanism-sound; would paste into any unrelated case study |
| A rule with no false-positive control | Under this rubric a false positive costs more than a miss |
| A threshold with no justification | Unfalsifiable; a reviewer cannot check it |
| A rule that fires on absence of evidence | Absence of observation is `not_assessed`, not a defect |
| Severity hand-assigned in the rule | Severity is computed from impact inputs. Always |
| Two rules in two skills reading the same fields for the same conclusion | Duplication. Merge, or the decomposition is padding |
| A rule that cites a fashionable practice without a mechanism | The `llms.txt` trap. State the mechanism or do not ship it |
