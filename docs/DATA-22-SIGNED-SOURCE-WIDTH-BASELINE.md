# DATA-22 — Signed published-source field-width inventory (2026-10-21)

This review measures **retained ARFI source-library observation records**, across *every* SHA-256-verified Git-backed yearly/monthly partition at the cited source ledger checkpoint. A source projection may include ARFI custody/period fields and may not have all columns of a publisher's full original bulk file. The latter must be audited separately when selecting a new publisher feed.

## Measured baseline

- Source acquisition ledger checkpoint: `2026-10-21T20:32:30Z`.
- Verified published source datasets: **238 of 238**; source records: **584,785**; historical partitions: **1,487**.
- Maximum observed fields in any published record: **44**.
- Records with more than 160 fields: **0**.
- Exact-source audit: [GitHub run 39692273490](https://github.com/American-Republic-Futures-Institute/afri-data/actions/runs/39692273490), with 30-day JSON evidence artifact `data22-original-signed-widths`.
- The audit replays every published partition's SHA-256 and verifies record/partition totals against the acquisition ledger before reporting. It never modifies original values.

| Publisher family | Datasets | Raw published records | Maximum published row fields |
|---|---:|---:|---:|
| U.S. Treasury Fiscal Data | 15 | 297,363 | 27 |
| CDC PLACES | 42 | 132,020 | 9 |
| EPA AirData | 74 | 56,861 | 20 |
| BLS QCEW | 21 | 54,740 | **44** |
| EIA SEDS | 5 | 16,575 | 9 |
| BEA regional accounts | 4 | 12,852 | 16 |
| USDA ERS | 2 | 7,890 | 13 |
| USGS ComCat | 27 | 3,988 | 24 |
| Census ACS | 48 | 2,496 | 17 |
| **Total** | **238** | **584,785** | **44** |

The earlier 160-field gateway ceiling was **not truncating any currently published observation**. DATA-22 is a prospective capability upgrade, not evidence of an existing missing dataset.

## Reviewed forward-compatible row budget

The bounded wide-row contract authorizes at most **512 original scalar fields**, **16,384 UTF-8 bytes per cell**, and **131,072 serialized bytes per row**. Publisher row names remain exact and hostile keys are rejected. The existing Git partition limit of **3,000,000 bytes** and website response ceiling of **7,000,000 bytes**, as well as each partition's SHA-256, remain mandatory.

The browser presents fields in explicit, searchable 32-column windows with accessible next/previous controls; all fields are still exported without omission in the original-column CSV. CSV formula defenses remain active. The 512-field ceiling is a bounded risk envelope, **not** a license to publish a new wide feed without its own raw source schema, unit, provenance, release and byte-budget acceptance.

## Ongoing acceptance

Run `python -m tools.audit_source_field_widths --root /path/to/checked-out/data/source-library` after the signed data branch has refreshed. Compare the resulting maximum and histogram with this checkpoint. Any legitimate publisher requiring more than 512 columns or exceeding the row/partition byte budgets must undergo a new bounded contract and consumer update; do not silently trim or flatten its original fields.
