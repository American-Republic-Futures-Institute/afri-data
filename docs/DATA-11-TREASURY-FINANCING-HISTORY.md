# DATA-11 — Treasury monthly financing and federal agency borrowing source expansion

This is a source-first increment, not a statistical or fiscal-policy inference. Register and ingest four additional **official U.S. Treasury Monthly Treasury Statement (MTS)** published tables by reusing the keyless, weekly `tools.source_library` source-native acquisition and SHA-256 partitioning. It adds **four** registered feeds on top of existing 11 Treasury feeds; **15 Treasury feeds total** after merge. Do not count the new datasets as acquired until `data/source-library` completes a genuine publisher refresh.

| ARFI source ID | Official endpoint, relative to Treasury Fiscal Data API | Subject |
| --- | --- | --- |
| `treasury-monthly-deficit-financing` | `v1/accounting/mts/mts_table_6` | Means of financing federal deficits or disposing of surpluses |
| `treasury-monthly-liability-analysis` | `v1/accounting/mts/mts_table_6a` | Analysis of changes in excess federal liabilities |
| `treasury-monthly-agency-securities` | `v1/accounting/mts/mts_table_6b` | Securities issued by federal agencies under special financing authorities |
| `treasury-monthly-agency-borrowing` | `v1/accounting/mts/mts_table_6c` | Federal agency borrowing financed by Treasury securities |

Official government dataset page: `https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/`. API origin: `https://api.fiscaldata.treasury.gov/services/api/fiscal_service/`. All records are source-reported publisher strings or native scalar values; `record_date` is the Treasury fiscal reporting date, **not necessarily the web publication timestamp**. The source library does not calculate deficit ratios, normalize line structures, or imply agency-specific authorization to borrow or spend.

## Acquisition and release acceptance

The new scoped `tools/treasury_mts_probe.py` checks only one first-page JSON response per table, from the four allowlisted Treasury endpoints. It records exact source URI, checked-at UTC, raw first-response SHA-256, bytes, first record date and availability. It rejects changed source paths, bad hosts, redirected responses, excessive response size, missing `record_date` or invalid JSON. A successful probe establishes **publisher API availability only**, not complete original source backfill, published analysis or source completeness.

`.github/workflows/probe-treasury-expansion.yml` exercises that probe from a real GitHub runner and retains a 30-day JSON attempt artifact. It runs alongside the repository's full exact-head validation. After merging:

- The existing `refresh-source-library.yml` weekly or source-catalog push workflow must fetch all four source histories, compare publisher row counts, use safe yearly or monthly source partitions with original record values and per-file SHA-256, and update `publication/source-library/index.json` and `health.json` in `data/source-library`.
- Failed new source retrievals must not create false index entries or overwrite previous publisher data. `health.json` must enumerate errors separately. **A green first-page probe is not a successful full-history ingestion.**
- A publisher's monthly reporting cycle must be tracked separately from ARFI's seven-day refresh interval. Target 7–14 calendar days between a genuinely identifiable publisher release and its verified ARFI GitHub source copy; measure rather than simply assert this SLA.
- No approved data-product, reviewed statistical method, website dashboard or human interpretation is modified.

## Reproducibility

```sh
python -m unittest discover -s tests -p 'test_treasury_mts_probe.py' -v
python -m unittest discover -s tests -p 'test_source_library.py' -v
python -m tools.treasury_mts_probe --output evidence/data11-treasury/source-probe.json
# On data/source-library branch:
python -m tools.source_library --verify
```

The first two commands are network-free regression tests. The probe and subsequent real source refresh require online access to the official Treasury host. Binary originals, huge source files and source transformations must be managed with Git blob bounds and separately verified receipts as the source program expands.
