"""Keyless CDC PLACES county source snapshots, not new ARFI statistics.

Reads fourteen publisher-modeled health measures across the official 2023, 2024,
and 2025 GIS-friendly county releases. Copies source fields and CDC-reported
intervals; record_date is an explicitly labeled release-vintage index marker,
not a survey observation date. No prevalence is calculated or inferred.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
from urllib.parse import urlencode

from pipelines.source_io import download_official

ROOT = Path(__file__).resolve().parents[1]
CATALOG = Path("catalog/source-library/cdc-places.json")
BASE = "https://data.cdc.gov/resource/"
KNOWN = {2023: ("7cmc-7y5g", 2021),
         2024: ("d3i6-k6z5", 2022),
         2025: ("i46a-9kgh", 2023)}
MEASURES = {
    "obesity", "diabetes", "arthritis", "csmoking", "lpa", "chd",
    "access2", "casthma", "cancer", "copd", "depression",
    "mhlth", "phlth", "stroke",
}
COUNTIES = {2023: 3143, 2024: 3144, 2025: 3143}  # source-release-specific official county row counts


def validate_registry(catalog):
    if (catalog.get("schemaVersion") != "1.0.0" or
            catalog.get("sourceFamily") != "cdc-places-county-gis" or
            catalog.get("refreshCadence") != "weekly" or
            catalog.get("publisher") != "Centers for Disease Control and Prevention"):
        raise ValueError("Unsupported CDC source registry")
    vintages = catalog.get("vintages")
    if (not isinstance(vintages, list) or len(vintages) != 3 or
            {v["year"]: (v["id"], v["modelReferenceYear"]) for v in vintages}
            != KNOWN):
        raise ValueError("CDC source vintage identity changed")
    measures = catalog.get("datasets")
    if (not isinstance(measures, list) or
            {m["indicatorStem"] for m in measures} != MEASURES or
            len(measures) != len(MEASURES)):
        raise ValueError("Unexpected or missing CDC health measure")
    for m in measures:
        if (not isinstance(m.get("title"), str) or
                not isinstance(m.get("description"), str) or
                not re.fullmatch(r"[a-z][a-z0-9]{1,14}", m["id"]) or
                m["id"] != m["indicatorStem"] or m["domain"] != "health" or
                m["unit"] != "percent" or m["maxRows"] != 3300):
            raise ValueError("Invalid CDC source metadata")


def registry_sources(root=ROOT):
    catalog = json.loads((Path(root) / CATALOG).read_text("utf-8"))
    validate_registry(catalog)
    specs = []
    for measure in catalog["datasets"]:
        for vintage in sorted(catalog["vintages"], key=lambda v: v["year"]):
            year = vintage["year"]
            source_id = vintage["id"]
            specs.append({
                "id": f"cdc-places-{measure['id']}-{year}",
                "title": f"CDC PLACES {measure['title']} — {year} release",
                "domain": "health",
                "description": (
                    f"CDC PLACES {year} county model-based estimate: "
                    f"{measure['description']}; original CDC crude modeled prevalence "
                    "and publisher confidence interval. This is not a direct "
                    "county survey measurement or local-policy effect."
                ),
                "provider": "cdc-places",
                "sourceId": source_id,
                "indicatorStem": measure["indicatorStem"],
                "publisher": catalog["publisher"],
                "dateBasis": "publisher-release-year-marker",
                "modelReferenceYear": vintage["modelReferenceYear"],
                "releaseYear": year,
                "endpoint": BASE + source_id + ".json",
                "dateField": "record_date",
                "preferredField": measure["indicatorStem"] + "_crudeprev",
                "unit": "percent",
                "maxRows": measure["maxRows"],
                "sourcePage": (
                    "https://data.cdc.gov/500-Cities-Places/"
                    f"PLACES-County-Data-GIS-Friendly-Format-{year}-releas/"
                    + source_id
                ),
            })
    return specs


def cdc_records(spec, fetch=download_official):
    year = spec.get("releaseYear")
    identity = KNOWN.get(year)
    if (not identity or identity[0] != spec.get("sourceId") or
            spec.get("modelReferenceYear") != identity[1] or
            spec.get("indicatorStem") not in MEASURES or
            spec.get("id") != f"cdc-places-{spec['indicatorStem']}-{year}" or
            spec.get("endpoint") != BASE + identity[0] + ".json"):
        raise ValueError("Unapproved official CDC PLACES source identity")
    stem = spec["indicatorStem"]
    value = stem + "_crudeprev"
    interval = stem + "_crude95ci"
    fields = ("countyfips", "countyname", "stateabbr", value, interval)
    query = urlencode({"$select": ",".join(fields),
                       "$order": "countyfips", "$limit": "4000"})
    url = spec["endpoint"] + "?" + query
    original = fetch(url, host="data.cdc.gov", limit=3_500_000)
    try:
        rows = json.loads(original.decode("utf-8"))
    except (UnicodeError, ValueError):
        raise ValueError("Official CDC response is not JSON") from None
    if not isinstance(rows, list) or len(rows) != COUNTIES[year]:
        raise ValueError("CDC county coverage changed; do not publish partial data")
    seen = set()
    output = []
    observed = 0
    for row in rows:
        if not isinstance(row, dict) or not set(fields[:3]) <= set(row):
            raise ValueError("CDC county identity fields missing")
        fips = row["countyfips"]
        if (not isinstance(fips, str) or
                not re.fullmatch(r"\d{5}", fips) or fips in seen or
                not isinstance(row["countyname"], str) or
                not isinstance(row["stateabbr"], str) or
                not re.fullmatch(r"[A-Z]{2}", row["stateabbr"])):
            raise ValueError("Invalid or duplicate CDC county FIPS")
        seen.add(fips)
        if not set(row) <= set(fields):
            raise ValueError("CDC response returned unrequested source fields")
        estimate = row.get(value)
        ci = row.get(interval)
        if estimate is not None:
            observed += 1
            try:
                number = Decimal(str(estimate))
            except (InvalidOperation, ValueError):
                raise ValueError("Invalid CDC modeled prevalence") from None
            if not number.is_finite() or number < 0 or number > 100:
                raise ValueError("Out-of-range CDC modeled prevalence")
        if ci is not None and (not isinstance(ci, str) or len(ci) > 80):
            raise ValueError("Unsupported CDC publisher confidence interval")
        # Original source fields are untouched. The following separate
        # metadata are indexing annotations, never government measurements.
        output.append({**row,
                       "record_date": f"{year}-12-31",
                       "publisher_release_vintage": str(year),
                       "model_reference_year": str(spec["modelReferenceYear"]),
                       "time_basis": "publisher_release_year_marker_not_survey_date"})
    if observed == 0:
        raise ValueError("CDC measure has no published prevalence observations")
    return sorted(output, key=lambda r: (r["record_date"], r["countyfips"]))
