"""Weekly source-native Treasury backfill for ARFI's public source library.

Not an analytical/statistical approval lane. Writes only publication/source-library.
Historical years are preserved in Git; the current branch exposes publisher revisions.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parents[1]
CATALOG = Path("catalog/source-library/treasury-fiscaldata.json")
OUTPUT = Path("publication/source-library")
BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
PAGE_SIZE = 1000
MAX_PAGES = 600
MAX_PAGE_BYTES = 7_000_000
MAX_YEAR_BYTES = 3_000_000  # bounded website response; large years split by month
ID = re.compile(r"^[a-z][a-z0-9-]{3,70}$")
ENDPOINT = re.compile(r"^v[12]/accounting/(?:od|dts|mts)/[a-z0-9_]{2,75}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PERIOD = re.compile(r"^(19|20|21)\d{2}-(?:0[1-9]|1[0-2])$")
HEX = re.compile(r"^[0-9a-f]{64}$")


class SourceLibraryError(ValueError):
    pass


def assert_that(value, reason):
    if not value:
        raise SourceLibraryError(reason)


def canonical(obj):
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def digest(content):
    return hashlib.sha256(content).hexdigest()


def validate_catalog(catalog):
    assert_that(catalog.get("schemaVersion") == "1.0.0" and
                catalog.get("publisherApi") == BASE and
                catalog.get("refreshCadence") == "weekly" and
                catalog.get("datasetClass") == "source-native-unreviewed",
                "Unrecognized source mirror catalog")
    datasets = catalog.get("datasets")
    assert_that(isinstance(datasets, list) and 1 <= len(datasets) <= 50,
                "Source count not bounded")
    seen = set()
    for item in datasets:
        assert_that(isinstance(item, dict), "Source descriptor malformed")
        key = item.get("id")
        assert_that(isinstance(key, str) and ID.fullmatch(key) and key not in seen,
                    "Duplicate or unsafe source ID")
        seen.add(key)
        if item.get("provider") == "bls-qcew":
            from tools.bls_qcew_source_library import BASE as BLS_BASE, SOURCE_PAGE, INDUSTRIES
            industry = item.get("industryCode")
            assert_that(industry in INDUSTRIES.values() and
                        item.get("id") in ("bls-qcew-" + k for k in INDUSTRIES) and
                        INDUSTRIES.get(key.removeprefix("bls-qcew-")) == industry and
                        item.get("endpoint") == BLS_BASE and
                        item.get("sourcePage") == SOURCE_PAGE and
                        item.get("dateField") == "record_date" and
                        item.get("dateBasis") == "publisher-quarter-end-marker" and
                        item.get("startYear") == 2022,
                        "Unapproved BLS QCEW publisher")
        elif item.get("provider") == "cdc-places":
            from tools.cdc_places_source_library import BASE as CDC_BASE, KNOWN, MEASURES
            year = item.get("releaseYear")
            entry = KNOWN.get(year)
            assert_that(entry is not None and
                        item.get("sourceId") == entry[0] and
                        item.get("modelReferenceYear") == entry[1] and
                        item.get("indicatorStem") in MEASURES and
                        key == f"cdc-places-{item['indicatorStem']}-{year}" and
                        item.get("endpoint") == CDC_BASE + entry[0] + ".json" and
                        item.get("sourcePage") == (
                            "https://data.cdc.gov/500-Cities-Places/"
                            f"PLACES-County-Data-GIS-Friendly-Format-{year}-releas/"
                            + entry[0]) and
                        item.get("dateBasis") == "publisher-release-year-marker" and
                        item.get("dateField") == "record_date",
                        "Unapproved CDC public source")
        else:
            assert_that(item.get("provider") is None and
                        isinstance(item.get("endpoint"), str) and
                        ENDPOINT.fullmatch(item["endpoint"]) and
                        item.get("dateField") == "record_date" and
                        isinstance(item.get("sourcePage"), str) and
                        item["sourcePage"].startswith("https://fiscaldata.treasury.gov/datasets/"),
                        "Unapproved federal origin or endpoint")
        assert_that(isinstance(item.get("title"), str) and
                    4 <= len(item["title"]) <= 110 and
                    isinstance(item.get("description"), str) and
                    20 <= len(item["description"]) <= 450 and
                    isinstance(item.get("unit"), str) and len(item["unit"]) <= 40 and
                    (item.get("preferredField") is None or
                     re.fullmatch(r"[a-z_]{3,70}", item["preferredField"])) and
                    type(item.get("maxRows")) is int and
                    1 <= item["maxRows"] <= 500000,
                    "Invalid source metric, description or row ceiling")


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise SourceLibraryError("Treasury redirect not allowed")


def acquire(url, opener=None):
    assert_that(url.startswith(BASE) and "@" not in url and "#" not in url,
                "Unapproved upstream URL")
    opener = opener or build_opener(NoRedirects())
    request = Request(url, headers={
        "User-Agent": "ARFI-Source-Library/1.0 (https://www.arfinstitute.org/)",
        "Accept": "application/json", "Accept-Encoding": "identity",
    })
    last = None
    for attempt in range(3):
        try:
            with opener.open(request, timeout=40) as response:
                assert_that(response.geturl() == url, "Unexpected Treasury redirect")
                header_size = response.headers.get("Content-Length")
                if header_size is not None:
                    assert_that(int(header_size) <= MAX_PAGE_BYTES,
                                "Publisher payload exceeds byte ceiling")
                data = response.read(MAX_PAGE_BYTES + 1)
                assert_that(0 < len(data) <= MAX_PAGE_BYTES,
                            "Publisher payload empty or oversized")
                return json.loads(data.decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last = exc
            if attempt < 2:
                time.sleep(1 + attempt)
    raise SourceLibraryError("Treasury acquisition failed: " + str(last))


def pages(spec, opener=None):
    """Fetch full official source history; return publisher fields without reinterpretation."""
    if spec.get("provider") == "cdc-places":
        from tools.cdc_places_source_library import cdc_records
        return cdc_records(spec)
    if spec.get("provider") == "bls-qcew":
        from tools.bls_qcew_source_library import bls_records
        return bls_records(spec)
    """Treasury pagination never silently truncates."""
    endpoint = spec["endpoint"]
    result = []
    declared_total = None
    for number in range(1, MAX_PAGES + 1):
        params = urlencode({"format": "json", "sort": "record_date",
                            "page[number]": str(number),
                            "page[size]": str(PAGE_SIZE)})
        url = BASE + endpoint + "?" + params
        doc = acquire(url, opener=opener)
        assert_that(isinstance(doc, dict) and isinstance(doc.get("data"), list),
                    "Unexpected Treasury API response")
        meta = doc.get("meta") or {}
        assert_that(isinstance(meta, dict), "Malformed source pagination metadata")
        if declared_total is None and "total-count" in meta:
            declared_total = int(meta["total-count"])
        rows = doc["data"]
        assert_that(len(rows) <= PAGE_SIZE, "Treasury page exceeded requested size")
        assert_that(rows or number > 1, "No source records returned")
        for row in rows:
            assert_that(isinstance(row, dict) and 1 <= len(row) <= 160 and
                        all(isinstance(k, str) and re.fullmatch(r"[a-z0-9_]{1,90}", k)
                            for k in row) and
                        all(v is None or type(v) in (str, int, float, bool)
                            for v in row.values()),
                        "Malformed original publisher record")
            date = row.get(spec["dateField"])
            assert_that(type(date) is str and DATE.fullmatch(date),
                        "Unrecognized source record date")
            try:
                when = datetime.strptime(date, "%Y-%m-%d").date()
            except ValueError:
                raise SourceLibraryError("Invalid Gregorian source date") from None
            assert_that(when.year >= 1900 and
                        when <= datetime.now(timezone.utc).date() + timedelta(days=1),
                        "Unexpected future or pre-1900 publication date")
        result.extend(rows)
        assert_that(len(result) <= spec["maxRows"],
                    "Source exceeds configured safe-history ceiling")
        if len(rows) < PAGE_SIZE:
            if declared_total is not None:
                assert_that(len(result) == declared_total,
                            "Treasury API returned incomplete history")
            break
    else:
        raise SourceLibraryError("Unbounded Treasury pagination; not publishing partial history")
    assert_that(len(set(canonical(row) for row in result)) == len(result),
                "Duplicate Treasury rows across publisher pages")
    return sorted(result, key=lambda r: (r[spec["dateField"]], canonical(r)))


def partition(spec, records):
    """Version source-native annual records; split oversized years by month.

    Partitioning never truncates source history or aggregates reported values.
    Old annual partitions remain byte-identical when below the budget.
    """
    groups = {}
    for row in records:
        year = int(row[spec["dateField"]][:4])
        groups.setdefault(year, []).append(row)
    partitions = []
    blobs = {}

    def emit(year, source_rows, period=None):
        doc = {"schemaVersion": "1.0.0", "sourceClass": "official-raw-values",
               "datasetId": spec["id"], "year": year,
               "dateField": spec["dateField"], "records": source_rows}
        if period is not None:
            doc["period"] = period
        payload = canonical(doc)
        assert_that(len(payload) <= MAX_YEAR_BYTES,
                    "Source month exceeds safe serving ceiling; require smaller source periods")
        key = period or str(year)
        path = f"publication/source-library/data/{spec['id']}/{key}.json"
        metadata = {"year": year, "path": path, "sha256": digest(payload),
                    "bytes": len(payload), "rows": len(source_rows),
                    "firstDate": source_rows[0][spec["dateField"]],
                    "lastDate": source_rows[-1][spec["dateField"]]}
        if period is not None:
            metadata["period"] = period
        partitions.append(metadata)
        blobs[path] = payload

    for year in sorted(groups):
        doc = {"schemaVersion": "1.0.0", "sourceClass": "official-raw-values",
               "datasetId": spec["id"], "year": year,
               "dateField": spec["dateField"], "records": groups[year]}
        if len(canonical(doc)) <= MAX_YEAR_BYTES:
            emit(year, groups[year])
        else:
            months = {}
            for row in groups[year]:
                month = row[spec["dateField"]][:7]
                assert_that(PERIOD.fullmatch(month), "Unexpected source month")
                months.setdefault(month, []).append(row)
            for month in sorted(months):
                emit(year, months[month], month)
    assert_that(bool(partitions) and len(partitions) <= 1200,
                "Source has no dated records or exceeds bounded partition count")
    return partitions, blobs

def verify(root=ROOT):
    index_path = Path(root) / OUTPUT / "index.json"
    index = json.loads(index_path.read_text("utf-8"))
    assert_that(index.get("schemaVersion") == "1.0.0" and
                index.get("sourceClass") == "automated-official-source-copy" and
                isinstance(index.get("datasets"), list) and index["datasets"],
                "No verified source library")
    for entry in index["datasets"]:
        assert_that(ID.fullmatch(entry["id"]) and
                    isinstance(entry.get("partitions"), list), "Invalid source metadata")
        total = 0
        keys = set()
        annual_years = set()
        monthly_years = set()
        for part in entry["partitions"]:
            year = part["year"]
            period = part.get("period")
            assert_that(type(year) is int and 1900 <= year <= 2150 and
                        (period is None or (type(period) is str and
                         PERIOD.fullmatch(period) and period.startswith(str(year) + "-"))),
                        "Unrecognized source date partition")
            key = period or str(year)
            assert_that(key not in keys and
                        part["path"] == f"publication/source-library/data/{entry['id']}/{key}.json",
                        "Unrecognized or duplicate source partition")
            keys.add(key)
            if period is None:
                annual_years.add(year)
            else:
                monthly_years.add(year)
            path = Path(root) / part["path"]
            payload = path.read_bytes()
            assert_that(0 < len(payload) <= MAX_YEAR_BYTES and
                        len(payload) == part["bytes"] and digest(payload) == part["sha256"] and
                        HEX.fullmatch(part["sha256"]), "Source partition digest mismatch")
            doc = json.loads(payload)
            records = doc.get("records")
            assert_that(doc["datasetId"] == entry["id"] and doc["year"] == year and
                        doc.get("period") == period and
                        isinstance(records, list) and len(records) == part["rows"] and
                        records and
                        all(type(row) is dict and
                            type(row.get("record_date")) is str and
                            row["record_date"].startswith(key + ("-" if period is None else "-"))
                            for row in records) and
                        records[0]["record_date"] == part["firstDate"] and
                        records[-1]["record_date"] == part["lastDate"],
                        "Source partition record or date mismatch")
            total += part["rows"]
        assert_that(not (annual_years & monthly_years),
                    "Cannot mix annual and monthly partitions of one source year")
        assert_that(total == entry["rowCount"], "Source dataset row-count mismatch")
    return {"datasets": len(index["datasets"]),
            "records": sum(d["rowCount"] for d in index["datasets"])}


def refresh(root=ROOT, catalog=None, loader=pages, now=None):
    root = Path(root)
    if catalog is None:
        treasury = json.loads((root / CATALOG).read_text("utf-8"))
        from tools.cdc_places_source_library import registry_sources as cdc_sources
        from tools.bls_qcew_source_library import registry_sources as bls_sources
        catalog = {**treasury,
                   "datasets": treasury["datasets"] + cdc_sources(root) + bls_sources(root)}
    validate_catalog(catalog)
    checked_at = now or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    directory = root / OUTPUT
    old_file = directory / "index.json"
    old = json.loads(old_file.read_text("utf-8")) if old_file.exists() else {"datasets": []}
    previous = {d["id"]: d for d in old.get("datasets", [])}
    fresh, failures = {}, {}
    for spec in catalog["datasets"]:
        try:
            records = loader(spec)
            assert_that(isinstance(records, list) and records, "Empty publisher result")
            records.sort(key=lambda r: (r[spec["dateField"]], canonical(r)))
            partitions, blobs = partition(spec, records)
            if spec["id"] in previous:
                prior = previous[spec["id"]]["rowCount"]
                assert_that(len(records) >= prior * .8,
                            "Publisher history shrank unexpectedly; keeping prior snapshot")
            for path, payload in blobs.items():
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.is_file() or target.read_bytes() != payload:
                    target.write_bytes(payload)
            fresh[spec["id"]] = {
                "id": spec["id"], "title": spec["title"], "domain": spec["domain"],
                "description": spec["description"], "sourcePage": spec["sourcePage"],
                "publisher": spec.get("publisher", catalog["publisher"]),
                "endpoint": spec["endpoint"] if spec.get("provider") in ("cdc-places", "bls-qcew") else BASE + spec["endpoint"],
                "dateBasis": spec.get("dateBasis", "original-publisher-record-date"),
                "dateField": spec["dateField"], "preferredField": spec["preferredField"],
                "unit": spec["unit"], "refreshCadence": "weekly",
                "rowCount": len(records), "firstDate": partitions[0]["firstDate"],
                "latestDate": partitions[-1]["lastDate"],
                "partitions": partitions, "sourceClass": "source-native-unreviewed",
            }
        except (ValueError, RuntimeError, KeyError, TypeError, OSError) as exc:
            failures[spec["id"]] = str(exc)[:250]
            if spec["id"] in previous:
                fresh[spec["id"]] = previous[spec["id"]]
    # Do not publish the source mirror if all new source acquisitions failed.
    assert_that(len(fresh) > 0 and len(failures) < len(catalog["datasets"]),
                "All authoritative source acquisitions failed; previous publication preserved")
    index = {"schemaVersion": "1.0.0",
             "sourceClass": "automated-official-source-copy",
             "sourceSystem": "U.S. Treasury Fiscal Data API, CDC PLACES and BLS QCEW original sources" if any(d.get("provider") == "bls-qcew" for d in catalog["datasets"]) else ("U.S. Treasury Fiscal Data API and CDC PLACES official county sources" if any(d.get("provider") == "cdc-places" for d in catalog["datasets"]) else "U.S. Treasury Fiscal Data API"),
             "refreshCadence": "weekly",
             "datasets": [fresh[id] for id in sorted(fresh)]}
    directory.mkdir(parents=True, exist_ok=True)
    contents = canonical(index)
    if not old_file.is_file() or old_file.read_bytes() != contents:
        old_file.write_bytes(contents)
    health = {"schemaVersion": "1.0.0", "checkedAt": checked_at,
              "attempted": len(catalog["datasets"]),
              "succeeded": len(catalog["datasets"]) - len(failures),
              "failed": failures,
              "nextExpectedCheck": "within 7 days of last successful scheduled run"}
    (directory / "health.json").write_bytes(canonical(health))
    verification = verify(root)
    return {**verification, "failedSources": failures,
            "checkedAt": checked_at}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true",
                        help="Verify retained GitHub source bytes and checksums")
    args = parser.parse_args()
    result = verify() if args.verify else refresh()
    print(json.dumps(result, sort_keys=True))
    if result.get("failedSources"):
        print("WARNING: One or more source feeds failed; previously published datasets kept.")


if __name__ == "__main__":
    main()
