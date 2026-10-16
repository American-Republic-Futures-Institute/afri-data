#!/usr/bin/env python3
"""Fail-closed validation for the ARFI publisher catalog and web artifacts."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
RELEASE = Path("publication/releases/census-state-population-v2025")
FIPS = frozenset((
    "01 02 04 05 06 08 09 10 11 12 13 15 16 17 18 19 20 21 "
    "22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 "
    "40 41 42 44 45 46 47 48 49 50 51 53 54 55 56 72"
).split())


def fail(message):
    raise ValueError("ARFI publication rejected: " + str(message))


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_schema(doc, schema_name):
    schema = load_json(ROOT / "contracts" / (schema_name + ".schema.json"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(doc),
                    key=lambda e: ".".join(map(str, e.absolute_path)))
    if errors:
        e = errors[0]
        fail(f"{schema_name}: {'.'.join(map(str, e.absolute_path))}: {e.message}")


def validate_catalog():
    raw_publishers = load_json(ROOT / "catalog/publishers.json")
    publishers = raw_publishers["publishers"]
    if len(publishers) < 30:
        fail("Publisher seed registry unexpectedly incomplete")
    by_id = {}
    for pub in publishers:
        validate_schema(pub, "publisher")
        if pub["id"] in by_id:
            fail("Duplicate publisher " + pub["id"])
        by_id[pub["id"]] = pub
    datasets = {}
    for path in sorted((ROOT / "catalog/datasets").glob("*.json")):
        doc = load_json(path)
        validate_schema(doc, "dataset")
        if doc["id"] in datasets:
            fail("Duplicate dataset " + doc["id"])
        if doc["publisherId"] not in by_id:
            fail("Unknown source publisher " + doc["publisherId"])
        for name in ("sourceUrl", "methodologyUrl"):
            if urlsplit(doc[name]).scheme != "https":
                fail("Non-HTTPS data reference")
        if doc["stage"] == "published" and doc["licenseStatus"] == "review-required":
            fail("A restricted dataset cannot be published without license review")
        datasets[doc["id"]] = doc
    indicators = {}
    for path in sorted((ROOT / "catalog/indicators").glob("*.json")):
        doc = load_json(path)
        validate_schema(doc, "indicator")
        if doc["datasetId"] not in datasets:
            fail("Indicator references an unknown dataset")
        if doc["id"] in indicators:
            fail("Duplicate indicator")
        indicators[doc["id"]] = doc
    inventory_path = ROOT / "catalog/source-programs.json"
    if inventory_path.exists():
        inventory = load_json(inventory_path)
        seen = set()
        for item in inventory["programs"]:
            if item["id"] in seen or item["publisherId"] not in by_id:
                fail("Program inventory has duplicate or unknown publisher " + item["id"])
            if urlsplit(item["url"]).scheme != "https":
                fail("Program source URL must be HTTPS")
            if item["stage"] != "registered":
                fail("Discovery registry entries are not approved ingestion sources")
            seen.add(item["id"])
    return {"publishers": len(publishers), "datasets": len(datasets),
            "indicators": len(indicators)}


def validate_coordinates(geometry):
    if geometry["type"] not in ("Polygon", "MultiPolygon"):
        fail("Unexpected Census map geometry")
    count = 0
    def walk(x):
        nonlocal count
        if isinstance(x, (list, tuple)) and len(x) >= 2 and \
                all(isinstance(y, (int, float)) and not isinstance(y, bool) for y in x[:2]):
            lon, lat = x[:2]
            if not math.isfinite(lon) or not math.isfinite(lat) \
                    or not (-180 <= lon <= 180 and -90 <= lat <= 90):
                fail("Invalid geographic coordinate")
            count += 1
        else:
            for y in x:
                walk(y)
    walk(geometry["coordinates"])
    if count < 4:
        fail("Insufficient polygon coordinates")


def validate_publication(root=ROOT):
    index_path = root / "publication/index.json"
    if not index_path.exists():
        fail("No published dataset release/index. Run the Census ingestion pipeline first.")
    index = load_json(index_path)
    releases = index.get("releases", [])
    if len(releases) != 1:
        fail("Unexpected publication index release count")
    release = releases[0]
    if release.get("releaseId") != "census-state-population-v2025":
        fail("Unregistered release in publication index")
    expected_paths = {
        "manifestPath": "manifest.json",
        "observationsPath": "observations.json",
        "geometryPath": "states.geojson"
    }
    for field, name in expected_paths.items():
        if release.get(field) != (RELEASE / name).as_posix():
            fail("Website publication path contract changed: " + field)
    path = root / RELEASE
    manifest = load_json(path / "manifest.json")
    validate_schema(manifest, "release")
    if manifest["releaseId"] != release["releaseId"]:
        fail("Inconsistent release identifier")
    if manifest["geography"]["features"] != len(FIPS):
        fail("State map requires 50 states, DC and Puerto Rico")
    if manifest["geography"]["joinKey"] != "GEOID":
        fail("Unsupported geometry join key")
    if (manifest["temporalCoverage"]["firstYear"], manifest["temporalCoverage"]["lastYear"]) != (2020, 2025):
        fail("Unexpected indicator year series")
    roles = {"originalTable": "source-table.csv", "observations": "observations.json",
             "observationsCsv": "observations.csv", "geometry": "states.geojson"}
    if set(manifest["assets"]) != set(roles):
        fail("Unexpected or missing published artifacts")
    for role, expected_name in roles.items():
        asset = manifest["assets"][role]
        name = asset["path"]
        if name != expected_name or "/" in name or "\\" in name or name in (".", ".."):
            fail("Unsafe or incorrect relative artifact path")
        contents = (path / name).read_bytes()
        digest = hashlib.sha256(contents).hexdigest()
        if not contents or asset["bytes"] != len(contents) or asset["sha256"] != digest:
            fail("Artifact integrity mismatch: " + name)
    source_file = manifest["sourceFiles"][0]
    if source_file["sha256"] != manifest["assets"]["originalTable"]["sha256"] \
            or source_file["bytes"] != manifest["assets"]["originalTable"]["bytes"]:
        fail("The original Census CSV was modified")
    for source in manifest["sourceFiles"]:
        if urlsplit(source["url"]).hostname != "www2.census.gov":
            fail("Source provenance does not point to authoritative Census downloads")
    values = load_json(path / "observations.json")
    if values.get("datasetId") != manifest["datasetId"] \
            or values.get("indicatorId") != release["indicatorId"] \
            or values.get("joinKey") != "fips" or values.get("vintage") != 2025:
        fail("Typed observation contract mismatch")
    rows = values.get("observations", [])
    expected = len(FIPS) * 6
    if len(rows) != expected:
        fail(f"Expected {expected} published observations; found {len(rows)}")
    lookup = {}
    for obs in rows:
        key = (obs.get("fips"), obs.get("year"))
        if key in lookup or obs.get("fips") not in FIPS or obs.get("year") not in range(2020, 2026):
            fail("Missing, duplicate or unexpected observation geography/period")
        if not isinstance(obs.get("value"), int) or isinstance(obs["value"], bool) or obs["value"] <= 0:
            fail("Invalid unsuppressed population value")
        if obs.get("statistic") != "published_estimate" or obs.get("unit") != "persons":
            fail("Mislabelled source measurement")
        lookup[key] = obs
    geo = load_json(path / "states.geojson")
    if geo.get("type") != "FeatureCollection" or geo.get("metadata", {}).get("vintage") != 2025:
        fail("GeoJSON metadata invalid")
    features = geo.get("features", [])
    if len(features) != len(FIPS):
        fail("GeoJSON coverage incomplete")
    mapped = set()
    for item in features:
        fips = item.get("properties", {}).get("GEOID")
        if fips not in FIPS or fips in mapped or item.get("id") != fips:
            fail("Wrong or repeated boundary GEOID")
        if item["properties"]["NAME"] != lookup[fips, 2025]["name"]:
            fail("Map boundary label differs from the official population table")
        validate_coordinates(item["geometry"])
        mapped.add(fips)
    if mapped != FIPS or set(k[0] for k in lookup) != FIPS:
        fail("Observation geography and geometry do not align")
    with (path / "observations.csv").open(encoding="utf-8", newline="") as f:
        csv_rows = list(csv.DictReader(f))
    if len(csv_rows) != expected:
        fail("CSV/JSON observation row count mismatch")
    for row in csv_rows:
        key = (row["fips"], int(row["year"]))
        if key not in lookup or int(row["value"]) != lookup[key]["value"]:
            fail("CSV/JSON observation values differ")
    return {"release": release["releaseId"], "observations": len(rows),
            "geometryFeatures": len(features), "verifiedAssets": len(roles)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-only", action="store_true")
    parser.add_argument("--publication-only", action="store_true")
    args = parser.parse_args()
    if args.catalog_only and args.publication_only:
        parser.error("Choose at most one validation scope")
    result = {}
    if not args.publication_only:
        result.update(validate_catalog())
    if not args.catalog_only:
        result.update(validate_publication())
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
