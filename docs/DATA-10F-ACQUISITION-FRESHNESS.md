# DATA-10F — Per-source original acquisition coverage and 7/14-day freshness evidence

**Repository:** `afri-data`, source acquisition first. Parent: [DATA-10 #71](https://github.com/American-Republic-Futures-Institute/afri-data/issues/71). This increment does **not** admit new publisher data, authorize derived claims, or claim whole-federal saturation.

## What actually exists

The stable `data/source-library` branch retains SHA-256-verified publisher record partitions. Current approved adapters cover Treasury Fiscal Data, CDC PLACES, BLS QCEW and Census ACS. **Registered** source feeds are not **successfully mirrored** feeds. The publication index and the acquisition `health.json` file are the authoritative on-repository evidence of that distinction.

At inspection on 2026-10-21, the published rolling branch contained **103 mirrored sources, 103/103 successful checks**, and no discovery warnings. The updated `main` BLS industry registrations had not yet reached the rolling source branch; a new refresh was running. Numbers are point-in-time evidence, not a government-wide enumerated denominator.

## New immutable-evidence-preserving operating ledger

Each successful source refresh now also writes `publication/source-library/acquisition-ledger.json`. It does **not** change the format or location of `publication/source-library/index.json`, the index used by the public website, or previous owner-authorized releases.

The ledger summarizes for each *registered* source:

- `verified_this_refresh` when the actual publisher response passed validation and its publisher source rows are in the SHA-256-verified mirror.
- `retained_previous_after_failure` when an upstream error left the last valid dataset untouched. The last successful check is **not** advanced.
- `registered_not_acquired` when a registration has no valid mirrored original source at all.
- `mirrorFingerprint`: SHA-256 of the **paths, partition SHA-256 digests, byte counts, and row counts** of that exact source dataset. Every historical source revision changes this fingerprint; mere review/check time does not.
- `firstSeenInMirrorAt` and `lastChangeObservedAt` only when a first download or change was **actually observed in a refresh with this ledger**. Existing sources predating ledger adoption retain `null` history rather than invented first-acquired times.
- `publisherRecordThrough` and `publisherDateBasis`, which are source measurement/edition markers, **not the date the publisher released or modified the dataset**.
- Per-family and whole-mirror counts of registered, mirrored, failed, retained, newly mirrored, revised, original records and partitions.

The ledger explicitly keeps `publisherReleasePublishedAt: null`, `sourceReleaseToGitLagDays: null`, and `publicationLagMeasurementStatus: not_measurable_without_publisher_release_timestamps`. We cannot establish the requested publisher-release-to-Git seven-day target by relabeling measurement dates or acquisition checks as real publisher release timestamps. The correct subsequent step is *per-source original publisher modified/published timestamp capture* at the official metadata endpoint, independently verified with timezone and source edition.

The `nextExpectedCheckAt` is seven days after the last completed refresh; `escalateIfUncheckedAt` is fourteen days afterward. These are **ingestion execution cadence controls**, not publisher release latency guarantees.

## Fail-closed verification

```sh
python -m unittest discover -s tests -p 'test_source_freshness.py' -v
python -m unittest discover -s tests -v
# In a populated checkout of data/source-library:
python -m tools.source_library --verify
python -m tools.source_freshness --verify --check-cadence
```

The source mirror `verify()` re-verifies actual retained partition bytes and hashes, then checks the ledger against the index and health state. Tests deny fabricated publisher timestamps, claimed zero-day release lag, incorrect mirrored counts, mismatched partition fingerprints, timestamp regressions, fake publisher success after failure, duplicate source IDs, source removal and unrecorded source changes. Historical Git commits retain previous original bytes; no original dataset is replaced with a status summary.

`.github/workflows/refresh-source-library.yml` already runs weekly (plus targeted `main` pushes), acquires the originals, verifies them, and publishes the refreshed index/health/ledger to `data/source-library`. The new `.github/workflows/watch-source-freshness.yml` monitors the actual source branch daily without refetching megabytes of public datasets. Seven days without a successful check fails the operational monitor; after fourteen days it escalates. Publisher failures and new-vintage discovery warnings are surfaced separately.

## Scaling toward government-wide acquisition

This work is deliberately **infrastructure for saturation**, not a tally of all publicly eligible datasets. Continue adding direct official government originals in bounded batches, preserving original units, period definitions, geography, response-body custody, redirects and source revisions. In particular:

1. Complete and verify the next BLS/ACS source backfill on `data/source-library`. A source registration is not an acquired original.
2. Integrate federal Data.gov Catalog API v4 discovery, subject to a real `DATA_GOV_API_KEY` GitHub secret and cursor/agency/access-right filters. Discovery *metadata* is not a downloaded original dataset or permission to redistribute restricted data.
3. Extend source publication timestamps from official metadata (for sources that expose them). Only then measure authentic publisher-release-to-repo lag and the seven-day and fourteen-day target.
4. Expand adapters across BEA, NOAA, EPA, USDA, HHS/CMS, HUD, NCES, DOT, DOE/EIA and other authoritative programs. Preserve large originals through explicit immutable storage and hash manifests rather than committing >100-MB blobs into ordinary Git.

Website visualizations, governed statistical transformations, institutional authority and policy analysis are separately staged; nothing here publishes a newly approved analysis.
