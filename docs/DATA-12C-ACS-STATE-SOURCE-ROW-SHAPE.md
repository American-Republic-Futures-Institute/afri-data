# DATA-12C — source-projection row-shape repair

### Observed production evidence

The 85-feed source refresh attempted the original 2022 ACS B25002
housing-occupancy table again and reported:

    census-acs5-b25002-2022: Unexpected ACS row width

The immutable state-equivalent 2022 B25002 copy remains in the rolling
Git archive from earlier successful acquisition; the 85-source index
contains all requested new CDC sources, but the source health report
documents **84 successes and one failure**.

### Scope of the repair

Census table-based Summary Files contain many levels of geography.
The Source Library's currently authorized product is a *state and
equivalent projection*, specifically original rows with
`GEO_ID=0400000USXX` for 52 known publisher geographic identities.
Only those state rows are published in the projection; the source
file's original bytes and SHA-256 hash remain independently traceable.

Previously a DictReader-width check occurred before checking the
source row's geography. A malformed or irregular **non-state** row
could therefore invalidate an otherwise complete, correctly formatted
52-jurisdiction source dataset.

The repair reads `GEO_ID` first, skips unselected geographies and
enforces full original column presence and no extra columns on
**every selected state row**. It does not permit invalid estimate/MOE
pairs, geographic duplicates, missing state records or modified
publisher estimate strings.

This is a targeted robustness correction for selection semantics,
not an invitation to ignore malformed included rows or to fabricate
data to achieve a green refresh.

### Acceptance

The suite appends irregular non-state county/tract rows to a synthetic
original file and verifies that the state source product still
preserves its 52 original observations and complete source hash.
It then independently corrupts a selected state row with extra and
missing columns and proves the importer rejects both cases.

The live government test is the next weekly source refresh. Do not
assert a fresh B25002 success until `health.json` reports zero
failures with the repaired parser, all requested original state
records, and SHA-256 replay. Existing previously validated
source periods remain available throughout.
