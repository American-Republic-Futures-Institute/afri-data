#!/usr/bin/env python3
"""Fail-closed validation for the ARFI publisher catalog and web artifacts."""
from __future__ import annotations

import argparse
import csv
import hashlib
import gzip
import io
import json
import math
from pathlib import Path
import sys
from urllib.parse import urlsplit

try:
    from tools.release_registry import checked_path, exact_release_path, valid_asset_name, valid_id
except ModuleNotFoundError:
    from release_registry import checked_path, exact_release_path, valid_asset_name, valid_id

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # Support CLI `python tools/validate.py` replay imports.
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


def validate_census_release(root, release):
    """Original strict Census source and geometry regression validation."""
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



def validate_generic_release(root, release, datasets, indicators):
    rid = release.get("releaseId")
    indicator_id = release.get("indicatorId")
    if not valid_id(rid) or not valid_id(indicator_id):
        fail("Invalid release or indicator id")
    if indicator_id not in indicators:
        fail("Unknown published indicator")
    indicator = indicators[indicator_id]
    dataset = datasets[indicator["datasetId"]]
    if dataset["licenseStatus"] == "review-required" or release.get("status") != "published":
        fail("Unreviewed or rights-restricted evidence")
    if release.get("manifestPath") != exact_release_path(rid, "manifest.json"):
        fail("Noncanonical manifest path")
    manifest = load_json(checked_path(root, rid, "manifest.json"))
    validate_schema(manifest, "release")
    if manifest["datasetId"] != dataset["id"] or manifest["releaseId"] != rid:
        fail("Release identity mismatch")
    period, geography = manifest["temporalCoverage"], manifest["geography"]
    if (geography["level"] != release.get("geography") or geography["level"] != indicator["geography"]
            or period["vintage"] != release.get("vintage")
            or period["firstYear"] != release.get("time", {}).get("firstYear")
            or period["lastYear"] != release.get("time", {}).get("lastYear")
            or period["firstYear"] > period["lastYear"]):
        fail("Incompatible release geography or time")
    for source in manifest["sourceFiles"]:
        u = urlsplit(source["url"])
        if u.scheme != "https" or not u.hostname or u.username or u.password or u.fragment:
            fail("Unsafe original evidence URL")
    assets = manifest["assets"]
    if "observations" not in assets:
        fail("Missing canonical observations")
    seen_names = set()
    for role, asset in assets.items():
        name = asset["path"]
        if not valid_asset_name(name) or name in seen_names:
            fail("Unsafe or duplicate asset name")
        seen_names.add(name)
        if asset["bytes"] > 25000000:
            fail("Asset exceeds static publication limit")
        file = checked_path(root, rid, name)
        if not file.is_file() or file.is_symlink():
            fail("Missing or linked asset")
        raw = file.read_bytes()
        if len(raw) != asset["bytes"] or hashlib.sha256(raw).hexdigest() != asset["sha256"]:
            fail("Artifact integrity mismatch: " + name)
        if asset["contentType"] not in ("application/json", "application/geo+json", "text/csv", "application/gzip"):
            fail("Unsupported asset MIME type")
    # A release with new sources must be reproducible from exact archived
    # publisher bytes, not a mutable URL and unchecked hash claim.
    source_roles = set()
    for source in manifest["sourceFiles"]:
        if source["role"] in source_roles:
            fail("Duplicate primary source role")
        source_roles.add(source["role"])
        archive_role = source.get("archiveAsset")
        if archive_role is None:
            if rid != "census-state-population-v2025":
                fail("Reproducible releases require original source archives")
            continue
        archived = assets.get(archive_role)
        if not archived or archived["contentType"] != "application/gzip":
            fail("Missing archived primary source")
        raw_compressed = checked_path(root, rid, archived["path"]).read_bytes()
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw_compressed)) as stream:
                original = stream.read(25_000_001)
                if stream.read(1):
                    fail("Source archive exceeds decompression limit")
        except (OSError, EOFError) as exc:
            fail("Invalid compressed primary source")
        if len(original) > 25_000_000 or len(original) != source["bytes"] \
                or hashlib.sha256(original).hexdigest() != source["sha256"]:
            fail("Archived original source SHA-256 or length mismatch")
        if source["role"] == "originalData" and urlsplit(source["url"]).hostname != urlsplit(dataset["sourceUrl"]).hostname:
            fail("Source hostname mismatches approved publisher")

    for field, role in (("observationsPath", "observations"), ("geometryPath", "geometry")):
        if role in assets:
            if release.get(field) != exact_release_path(rid, assets[role]["path"]):
                fail("Incorrect published asset path")
        elif field in release:
            fail("Published index refers to absent asset")
    content = load_json(checked_path(root, rid, assets["observations"]["path"]))
    if (content.get("datasetId") != dataset["id"] or content.get("indicatorId") != indicator_id
            or content.get("vintage") != period["vintage"]
            or content.get("geography") != geography["level"]):
        fail("Inconsistent observations envelope")
    observations = content.get("observations")
    if not isinstance(observations, list) or not observations:
        fail("Missing observations")
    if len(observations) != assets["observations"].get("rows"):
        fail("Observation count mismatch")
    keys = set()
    for row in observations:
        geoid = row.get("geoid", row.get("fips"))
        year = row.get("year")
        if not isinstance(geoid, str) or not geoid.isdigit():
            fail("GEOID must be a string of digits")
        lengths = {"state":2, "county":5, "tract":11}
        if geography["level"] in lengths and len(geoid) != lengths[geography["level"]]:
            fail("Unexpected geographic identifier width")
        if type(year) is not int or not period["firstYear"] <= year <= period["lastYear"]:
            fail("Observation year is outside release coverage")
        key = (geoid, year)
        if key in keys:
            fail("Duplicate observation")
        keys.add(key)
        value = row.get("value")
        if value is None:
            if row.get("status") not in ("missing", "suppressed", "not_available"):
                fail("Null observation needs missing/suppressed status")
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            fail("Invalid numeric observation")
    if "geometry" in assets:
        geo = load_json(checked_path(root, rid, assets["geometry"]["path"]))
        if geo.get("type") != "FeatureCollection" or len(geo.get("features", [])) != geography["features"]:
            fail("Geometry count or structure invalid")
    return {"observations":len(observations), "verifiedAssets":len(assets),
            "geometryFeatures":geography["features"] if "geometry" in assets else 0}

def validate_publication(root=ROOT):
    index_file = root / "publication/index.json"
    if not index_file.is_file():
        fail("No approved publication index")
    index = load_json(index_file)
    releases = index.get("releases")
    if index.get("schemaVersion") != "1.0.0" or not isinstance(releases, list) or not 1 <= len(releases) <= 250:
        fail("Invalid publication index")
    datasets = {doc["id"]:doc for p in (ROOT / "catalog/datasets").glob("*.json") if (doc := load_json(p))}
    indicators = {doc["id"]:doc for p in (ROOT / "catalog/indicators").glob("*.json") if (doc := load_json(p))}
    seen = set()
    totals = {"releases":0,"observations":0,"verifiedAssets":0,"geometryFeatures":0}
    for entry in releases:
        if not isinstance(entry, dict) or entry.get("releaseId") in seen:
            fail("Duplicate or invalid release")
        seen.add(entry["releaseId"])
        metrics = validate_generic_release(root, entry, datasets, indicators)
        if entry.get("indicatorId") == "state-median-household-income":
            from pipelines.census_acs_release import project as project_acs_income
            import gzip
            folder = checked_path(root, entry["releaseId"], "manifest.json").parent
            original = gzip.decompress((folder / "originalData.gz").read_bytes())
            if load_json(folder / "observations.json")["observations"] != project_acs_income(original):
                fail("Published ACS observations are not reproducible from originals")
        if entry.get("indicatorId") == "county-modeled-obesity-prevalence":
            from pipelines.cdc_places_release import parse_places
            import gzip
            folder = checked_path(root, entry["releaseId"], "manifest.json").parent
            original = gzip.decompress((folder / "originalData.gz").read_bytes())
            if load_json(folder / "observations.json")["observations"] != parse_places(original):
                fail("Published CDC PLACES observations are not reproducible from originals")
        if entry.get("indicatorId") == "state-federal-award-obligations":
            from pipelines.usaspending_release import project as project_spending, exclusion_report
            import gzip
            folder = checked_path(root, entry["releaseId"], "manifest.json").parent
            original = gzip.decompress((folder / "originalData.gz").read_bytes())
            request = gzip.decompress((folder / "requestBody.gz").read_bytes())
            if load_json(folder / "observations.json")["observations"] != project_spending(original,request):
                fail("USAspending obligations are not reproducible from original response and POST")
            if load_json(folder / "geography-exclusions.json") != exclusion_report(original):
                fail("USAspending excluded or unattributed obligations were changed")
        # Replay the publisher-specific projection from archived original bytes.
        # Hash-consistent edited values are not authentic government evidence.
        if entry.get("indicatorId") == "state-unemployment-rate":
            from pipelines.bls_laus_release import parse_authoritative_annual
            import gzip
            folder = checked_path(root, entry["releaseId"], "manifest.json").parent
            source_bytes = [
                gzip.decompress((folder / name).read_bytes())
                for name in ("originalData.gz", "originalSeries.gz", "originalAreas.gz")
            ]
            expected = parse_authoritative_annual(*source_bytes)
            projected = load_json(folder / "observations.json")["observations"]
            if projected != expected:
                fail("Published LAUS observations are not reproducible from originals")
        if entry["releaseId"] == "census-state-population-v2025":
            validate_census_release(root, entry)
            totals["release"] = entry["releaseId"]
        totals["releases"] += 1
        for k in ("observations","verifiedAssets","geometryFeatures"):
            totals[k] += metrics[k]
    return totals


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
        from tools.validate_geography import validate_geography
        result.update(validate_geography())
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
