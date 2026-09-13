# Samples

Three complete audits, produced by `python scripts/build_samples.py` from the
fictional sites in `tests/fixtures/archetypes/`, served locally. No real brand is
audited here. Start with any `report.md`.

| Sample | Site | Capabilities | What it shows |
|---|---|---|---|
| `storefront-full/` | a storefront with theme-level defects | browser and network | template defects found at template scope, a price shown only after rendering, a crawler refused by user agent, and the legitimate look-alikes beside them producing nothing |
| `spa-shell-browser/` | a client-rendered site that serves one empty shell at every path | browser, no network | the empty server response as the critical finding, and the missing organization markup beneath it marked as conditional on fixing it first |
| `spa-shell-no-browser/` | the same site | neither | the audit still finds that the server response carries no text, and lists every check it could not make and what would enable it |

Each directory holds `report.md` (for the person fixing the site), `report.json`
(the structured report) and `evidence/` (every observation the findings cite).
Local ports and timestamps differ between regenerations; the findings do not.
