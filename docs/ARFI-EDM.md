# ARFI-EDM D-01: multi-release contract

This increment generalizes the approved publication index while retaining the
original Census v2025 integrity and statistical fidelity checks. No new official
measurements are introduced in this increment.

- All evidence is read from an approved \`publication/index.json\` and an immutable
  repository commit. The website cannot authorize arbitrary source URLs.
- Each release has a unique lowercase-kebab-case ID, a reviewed manifest, source
  provenance, SHA-256 for each published asset, and versioned observations.
- The registry now upserts an individual release without dropping independent
  published releases. The Census refresh copies pre-existing approved releases
  into the staging directory before validation and replacement.
- Geography may be national, state, county, tract, place, point or mixed.
  County FIPS must remain five-character strings; state FIPS two characters.
- A null observation requires explicit \`missing\`, \`suppressed\`, or
  \`not_available\` status. Silent zero-filling is prohibited.
- Original evidence, source-preserving projections, derived statistics and
  interpretation remain separate. Signed provenance is not inferred from a
  SHA-256 hash alone.
- Published source material retains source rights independent of the MIT license
  on ARFI-authored software.
- Adapters for ACS, LAUS, PLACES and USAspending are separate subsequent PRs.

Validation: \`python tools/validate.py\` and
\`python -m unittest discover -s tests -v\`.
Synthetic multi-release tests use temporary files only, never official
published asset directories.
