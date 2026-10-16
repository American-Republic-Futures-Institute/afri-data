# Website consumption contract — ARFI Public Data Observatory

The authoritative public data repository feeds the planned ARFI website path /data/. **This bootstrap does not yet modify or deploy the website.** It produces the verified static assets and metadata needed for a separate visualization increment.

## Static published assets

After the generated release PR has been reviewed and merged:

- publication/index.json — discovery index and approved release path.
- publication/releases/census-state-population-v2025/manifest.json — release provenance, source URLs and hashes.
- publication/releases/census-state-population-v2025/observations.json — typed source estimates and stable FIPS.
- publication/releases/census-state-population-v2025/observations.csv — downloadable corresponding rows.
- publication/releases/census-state-population-v2025/states.geojson — 2025 state/cartographic geometry.
- publication/releases/census-state-population-v2025/source-table.csv — exact original Census source.

Rows contain fips, name, year, value, unit, measure, statistic and vintage. The numbers are *publisher population estimates*, not rates, forecasts, decennial enumeration totals, or invented sample records.

Join the two-character observation.fips to feature.properties.GEOID. Do not coerce FIPS to integer: leading zeros are significant. There are 52 matched geographies (50 states, Washington DC, Puerto Rico), six years (2020–2025) and 312 individual observations. The original boundary source includes other Island Areas; they are intentionally not visualized with missing population values.

## Website release publishing

- Prefer copying data at build time from an **approved immutable Git commit** into existing static hosting. Alternative: a bounded read-only server endpoint that fetches the approved release by commit hash and verifies SHA-256.
- Never pull arbitrary visitor-supplied upstream URLs.
- Keep original SHA-256 hashes and source-vintage metadata available in a details panel.
- The browser requests only small static JSON/GeoJSON assets; no new backend, paid map tiles, external database or exposed API keys are required.
- Cache immutable versions, use content-type-safe parsing, reject oversized or invalid assets, and preserve an accessible table fallback.
- A dynamic GitHub main-branch link is a convenience URL, not an immutable publication identifier.

## Choropleth and charts

The first map demonstrates real original-source statistics. Because state populations are absolute totals, it should **not** be interpreted as comparative performance. Label the 2025 July 1 estimates, boundary simplification 1:20 million, different Census vintage concepts and excluded geographies. Show the precise value, FIPS, publisher link and methodology on selection.

User controls should support year choice (2020–2025), chart versus map, per-state trend and accessible sorted table plus CSV. Color missing values distinctly and never silently invent estimates.

The example under examples/choropleth.html works with a static HTTP server once the release assets are present. Use a locally bundled Apache ECharts version within the final site rather than treating demo-CDN scripts as a production dependency.

## Future optional publication API

- GET /api/data → approved release index.
- GET /api/data?release=census-state-population-v2025 → release manifest/source metadata.
- GET /api/data?release=...&asset=observations|geometry → strictly allowlisted and hash-checked payload.
- Unknown releases or asset IDs return 404; invalid source or checksums fail closed without a cached success.

Architecture Atlas integration comes later. Observational data, model relationships, hypothetical outcomes and policy proposals must remain separate objects.
