#!/usr/bin/env python3
"""Publish Census Bureau data without rewriting the authoritative measurements.

Uses public static Vintage 2025 source files (no API key, database, or paid ETL).
Every source byte is hashed; only typed fields and simplified geometry are
materialized. Failed downloads/validation never modify the published release.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import shutil
import tempfile
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import zipfile

import shapefile  # pyshp; pinned by requirements.txt

ROOT = Path(__file__).resolve().parents[1]
# Resolve sibling packages for both `python -m` and direct script execution.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
RELEASE_ID = "census-state-population-v2025"
RELEASE_PATH = Path("publication/releases") / RELEASE_ID
YEARS = tuple(range(2020, 2026))
# Only the 50 states, DC and Puerto Rico. Never invent values for other territories.
FIPS = frozenset((
    "01 02 04 05 06 08 09 10 11 12 13 15 16 17 18 19 20 21 "
    "22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 "
    "40 41 42 44 45 46 47 48 49 50 51 53 54 55 56 72"
).split())
assert len(FIPS) == 52


def compact_json(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def pretty_json(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       indent=2, allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fetch_source(url: str, max_bytes: int) -> bytes:
    if not url.startswith("https://www2.census.gov/"):
        raise ValueError("Only the declared official Census source host is allowed")
    last_error = None
    for attempt in range(3):
        try:
            req = Request(url, headers={
                "User-Agent": "ARFI-Public-Data-Observatory/0.1 (+https://www.arfinstitute.org/)",
                "Accept": "text/csv,application/zip,application/octet-stream,*/*"
            })
            with urlopen(req, timeout=35) as response:
                if response.geturl().split("/")[2] != "www2.census.gov":
                    raise ValueError("Unexpected download redirect to non-Census host")
                payload = response.read(max_bytes + 1)
                if not payload or len(payload) > max_bytes:
                    raise ValueError("Empty or unexpectedly large source file")
                return payload
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Official Census download failed: {last_error}")


def parse_population(raw: bytes) -> list[dict]:
    decoded = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(decoded))
    required = {"SUMLEV", "STATE", "NAME"} | {f"POPESTIMATE{year}" for year in YEARS}
    if not required.issubset(set(reader.fieldnames or ())):
        raise ValueError(f"Official Census table missing columns: {required - set(reader.fieldnames or ())}")
    names: dict[str, str] = {}
    rows: list[dict] = []
    for source in reader:
        fips = (source.get("STATE") or "").strip().zfill(2)
        if fips not in FIPS:
            continue
        if str(source.get("SUMLEV") or "").strip().zfill(3) != "040":
            raise ValueError(f"Unexpected geographic summary level for {fips}")
        if fips in names:
            raise ValueError(f"Duplicate population geography: {fips}")
        name = str(source.get("NAME") or "").strip().lstrip(".")
        if not name:
            raise ValueError("Missing Census geographic label")
        names[fips] = name
        for year in YEARS:
            raw_value = str(source.get(f"POPESTIMATE{year}") or "").strip()
            if not raw_value.isascii() or not raw_value.isdecimal():
                raise ValueError(f"Invalid official population estimate {fips} {year}: {raw_value!r}")
            value = int(raw_value)
            if value <= 0:
                raise ValueError(f"Unexpected nonpositive resident population: {fips} {year}")
            rows.append({
                "fips": fips, "name": name, "year": year,
                "value": value, "unit": "persons",
                "measure": "resident_population_estimate",
                "statistic": "published_estimate",
                "vintage": 2025
            })
    if set(names) != FIPS:
        raise ValueError(f"Official table has {len(names)} matched state/DC/PR geographies; missing {sorted(FIPS - set(names))}")
    rows.sort(key=lambda row: (row["year"], row["fips"]))
    return rows


def parse_geometry(raw_zip: bytes, expected: dict[str, str]) -> dict:
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as archive:
        members = {Path(info.filename).suffix.lower(): info for info in archive.infolist()
                   if Path(info.filename).suffix.lower() in {".shp", ".shx", ".dbf"}}
        if not {".shp", ".dbf", ".shx"}.issubset(members):
            raise ValueError("Census boundary archive lacks .shp/.shx/.dbf components")
        if sum(info.file_size for info in members.values()) > 25_000_000:
            raise ValueError("Excessive uncompressed geographic source size")
        def load(extension):
            return io.BytesIO(archive.read(members[extension]))
        reader = shapefile.Reader(shp=load(".shp"), shx=load(".shx"), dbf=load(".dbf"))
        features: dict[str, dict] = {}
        for item in reader.iterShapeRecords():
            record = item.record.as_dict()
            fips = str(record.get("GEOID") or record.get("STATEFP") or "").strip().zfill(2)
            if fips not in FIPS:
                continue
            if fips in features:
                raise ValueError(f"Duplicate boundary geometry for {fips}")
            geom = item.shape.__geo_interface__
            if geom.get("type") not in {"Polygon", "MultiPolygon"}:
                raise ValueError(f"Unsupported Census boundary geometry for {fips}")
            if not geom.get("coordinates"):
                raise ValueError(f"Empty Census boundary for {fips}")
            features[fips] = {
                "type": "Feature",
                "id": fips,
                "properties": {"GEOID": fips, "NAME": expected[fips], "vintage": 2025},
                "geometry": geom
            }
        reader.close()
    if set(features) != FIPS:
        raise ValueError(f"Geographic archive incomplete: missing {sorted(FIPS - set(features))}")
    return {"type": "FeatureCollection",
            "metadata": {"publisher": "U.S. Census Bureau", "vintage": 2025,
                         "cartographicScale": "1:20,000,000", "joinKey": "GEOID",
                         "purpose": "generalized thematic mapping, not surveyed legal boundaries"},
            "features": [features[key] for key in sorted(features)]}


def build_release(root: Path, csv_bytes: bytes, zip_bytes: bytes,
                  source_urls: tuple[str, str], created_at: str | None = None) -> dict:
    observations = parse_population(csv_bytes)
    labels = {x["fips"]: x["name"] for x in observations if x["year"] == 2025}
    boundaries = parse_geometry(zip_bytes, labels)
    if len(observations) != len(FIPS) * len(YEARS):
        raise AssertionError("Missing observed years or geographic rows")

    output = root / RELEASE_PATH
    output.mkdir(parents=True, exist_ok=True)
    payloads = {
        "originalTable": ("source-table.csv", csv_bytes, "text/csv"),
        "observations": ("observations.json", compact_json({
            "schemaVersion": "1.0.0", "datasetId": RELEASE_ID,
            "indicatorId": "state-resident-population",
            "geography": "state", "joinKey": "fips",
            "vintage": 2025, "observations": observations
        }), "application/json"),
        "geometry": ("states.geojson", compact_json(boundaries), "application/geo+json")
    }

    csv_buf = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buf, fieldnames=[
        "fips", "name", "year", "value", "unit", "measure", "statistic", "vintage"
    ], lineterminator="\n")
    writer.writeheader()
    writer.writerows(observations)
    payloads["observationsCsv"] = ("observations.csv", csv_buf.getvalue().encode("utf-8"), "text/csv")

    assets = {}
    for role, (name, contents, content_type) in payloads.items():
        (output / name).write_bytes(contents)
        assets[role] = {
            "path": name, "sha256": sha256(contents),
            "bytes": len(contents), "contentType": content_type
        }
        if role in {"observations", "observationsCsv"}:
            assets[role]["rows"] = len(observations)
        if role == "geometry":
            assets[role]["rows"] = len(boundaries["features"])
    sources = [
        {"role": "originalTable", "url": source_urls[0],
         "sha256": sha256(csv_bytes), "bytes": len(csv_bytes)},
        {"role": "originalBoundaryArchive", "url": source_urls[1],
         "sha256": sha256(zip_bytes), "bytes": len(zip_bytes)}
    ]

    # Retain the original publication timestamp for identical source bytes.
    previous_path = ROOT / RELEASE_PATH / "manifest.json"
    prior = {}
    if previous_path.exists():
        try:
            prior = json.loads(previous_path.read_text(encoding="utf-8"))
        except ValueError:
            pass
    if (prior.get("sourceFiles") == sources and prior.get("assets") == assets
            and prior.get("createdAt")):
        timestamp = prior["createdAt"]
    else:
        timestamp = created_at or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    manifest = {
        "schemaVersion": "1.0.0", "releaseId": RELEASE_ID,
        "datasetId": RELEASE_ID, "createdAt": timestamp, "status": "published",
        "sourceFiles": sources, "assets": assets,
        "geography": {"level": "state", "vintage": 2025, "joinKey": "GEOID",
                      "features": len(FIPS), "coverage": "50 states, District of Columbia, Puerto Rico"},
        "temporalCoverage": {"firstYear": 2020, "lastYear": 2025, "vintage": 2025},
        "method": ("Select official STATE FIPS and POPESTIMATE2020-2025 fields for "
                   "the 50 states, DC and Puerto Rico; cast Census estimates to "
                   "integers without imputation, aggregation, interpolation or "
                   "rate normalization. Join Census 2025 generalized state "
                   "cartographic boundaries on GEOID. Retain both original "
                   "source-file checksums and original population CSV bytes."),
        "interpretation": "Census estimates are estimates; map values are absolute population totals.",
        "publishedSource": "U.S. Census Bureau"
    }
    (output / "manifest.json").write_bytes(pretty_json(manifest))
    index = {
        "schemaVersion": "1.0.0",
        "publicationStatus": "published",
        "publisher": "American Republic Futures Institute",
        "sourceOfTruth": "https://github.com/American-Republic-Futures-Institute/afri-data",
        "releases": [{
            "releaseId": RELEASE_ID, "indicatorId": "state-resident-population",
            "title": "State resident population, July 1 estimates, 2020–2025 (Vintage 2025)",
            "geography": "state", "vintage": 2025,
            "manifestPath": f"{RELEASE_PATH.as_posix()}/manifest.json",
            "observationsPath": f"{RELEASE_PATH.as_posix()}/observations.json",
            "geometryPath": f"{RELEASE_PATH.as_posix()}/states.geojson",
            "time": {"firstYear": 2020, "lastYear": 2025},
            "status": "published"
        }]
    }
    (root / "publication").mkdir(parents=True, exist_ok=True)
    from tools.release_registry import upsert_release_entry
    upsert_release_entry(root, index["releases"][0])
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv-file", type=Path, help="Fixture or verified downloaded original CSV")
    parser.add_argument("--shape-zip", type=Path, help="Fixture or verified downloaded Census boundary ZIP")
    parser.add_argument("--out-root", type=Path, default=ROOT)
    parser.add_argument("--created-at", help="ISO 8601 timestamp used in deterministic tests")
    args = parser.parse_args()
    if bool(args.csv_file) != bool(args.shape_zip):
        parser.error("--csv-file and --shape-zip must be provided together")
    dataset = json.loads((ROOT / "catalog/datasets/census-state-population-v2025.json").read_text())
    geometry = json.loads((ROOT / "catalog/datasets/census-state-boundaries-v2025.json").read_text())
    urls = (dataset["sourceUrl"], geometry["sourceUrl"])
    if args.csv_file:
        raw_csv, raw_zip = args.csv_file.read_bytes(), args.shape_zip.read_bytes()
    else:
        raw_csv = fetch_source(urls[0], 2_000_000)
        raw_zip = fetch_source(urls[1], 8_000_000)
    # Build and check in a private staging area so failures do not touch output.
    with tempfile.TemporaryDirectory() as temp:
        stage = Path(temp)
        prior = args.out_root / 'publication'
        if prior.is_dir():
            shutil.copytree(prior, stage / 'publication', dirs_exist_ok=True)
        manifest = build_release(stage, raw_csv, raw_zip, urls, args.created_at)
        # Validate before publishing (run in-process, no external service).
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        from validate import validate_publication
        validate_publication(stage)
        for relative in [RELEASE_PATH / name for name in [
                "source-table.csv", "observations.json", "observations.csv",
                "states.geojson", "manifest.json"
        ]] + [Path("publication/index.json")]:
            target = args.out_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(stage / relative, target)
    print(json.dumps({
        "release": manifest["releaseId"], "populationRows": len(FIPS) * len(YEARS),
        "mappedGeographies": manifest["geography"]["features"],
        "sourceCsvSha256": manifest["sourceFiles"][0]["sha256"],
        "sourceGeometryZipSha256": manifest["sourceFiles"][1]["sha256"],
        "out": str(args.out_root / RELEASE_PATH)
    }, sort_keys=True))


if __name__ == "__main__":
    main()
