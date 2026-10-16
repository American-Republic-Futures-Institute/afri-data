"""Acquire, project, verify and stage the official 2025 BLS LAUS state release.

This does NOT merge or approve a release. Its output is review-gated. Original
publisher data, series and area files are retained byte-for-byte via gzip.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import tempfile

from pipelines.bls_laus import (
    SOURCE_DATA_URL, SOURCE_SERIES_URL, SOURCE_AREA_URL,
    STATE_RATE_SERIES, parse_laus_state_annual,
)
from pipelines.census_state_population import FIPS
from pipelines.evidence_publish import stage_release
from pipelines.source_io import download_official
from tools.validate import validate_publication

ROOT = Path(__file__).resolve().parents[1]
YEAR = 2025
SOURCES = (
    ("originalData", SOURCE_DATA_URL, 21_000_000),
    ("originalSeries", SOURCE_SERIES_URL, 8_000_000),
    ("originalAreas", SOURCE_AREA_URL, 2_000_000),
    ("originalFootnotes", "https://download.bls.gov/pub/time.series/la/la.footnote", 100_000),
)

def rows_from_tsv(source: bytes, expected: frozenset[str] | set[str]) -> list[dict]:
    try:
        text = source.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("Non-UTF8 publisher metadata") from exc
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    if not reader.fieldnames or not expected.issubset({x.strip() for x in reader.fieldnames}):
        raise ValueError("BLS metadata schema drift")
    out = []
    for item in reader:
        if None in item:
            raise ValueError("Malformed BLS metadata row width")
        out.append({k.strip(): str(v or "").strip() for k, v in item.items()})
    return out

def parse_authoritative_annual(data: bytes, series: bytes, areas: bytes, footnotes: bytes) -> list[dict]:
    """Cross-check unadjusted annual rates against BLS series and area catalogs."""
    values = parse_laus_state_annual(data, YEAR)
    by_series = {}
    for row in rows_from_tsv(series, {"series_id","area_code","measure_code","seasonal","area_type_code"}):
        sid = row["series_id"]
        if not STATE_RATE_SERIES.fullmatch(sid):
            continue
        if sid in by_series:
            raise ValueError("Duplicate BLS series catalog entry")
        code = sid[3:18]
        if (code != row["area_code"] or row["measure_code"] != "03"
                or row["seasonal"] != "U" or row["area_type_code"] != "A"):
            raise ValueError("BLS series metadata conflicts with identifier")
        by_series[sid] = row
    by_area = {}
    for row in rows_from_tsv(areas, {"area_type_code","area_code","area_text"}):
        code = row["area_code"]
        if not re.fullmatch(r"ST[0-9]{2}0{11}", code):
            continue
        if row["area_type_code"] != "A":
            raise ValueError("Unexpected BLS statewide area type")
        if code in by_area or not row["area_text"]:
            raise ValueError("Duplicate or blank BLS geographic description")
        by_area[code] = row["area_text"]

    definitions = {}
    for item in rows_from_tsv(footnotes, {"footnote_code", "footnote_text"}):
        key = item["footnote_code"]
        if not re.fullmatch(r"[A-Z]", key) or key in definitions or not item["footnote_text"]:
            raise ValueError("Invalid BLS source footnote definitions")
        definitions[key] = item["footnote_text"]
    definition = definitions.get("G", "").lower()
    if not all(term in definition for term in ("2025", "11-month", "october")):
        raise ValueError("Required official BLS missing-October footnote absent")

    observed = {v["geoid"] for v in values}
    if observed != FIPS:
        raise ValueError("BLS coverage mismatch: missing or unapproved FIPS")
    projected = []
    for row in values:
        sid = row["seriesId"]
        if sid not in by_series:
            raise ValueError("BLS data series absent from source catalog")
        name = by_area.get(by_series[sid]["area_code"])
        if not name:
            raise ValueError("Missing source metadata for BLS area")
        codes = row["footnoteCodes"]
        if any(code not in definitions for code in codes):
            raise ValueError("Undefined original BLS source footnote code")
        eleven_month = row["geoid"] != "72"
        if ("G" in codes) != eleven_month:
            raise ValueError("BLS 2025 source footnote G does not match geography")
        projected.append({
            **row, "name": name,
            "referencePeriod": ("2025 annual estimate excluding October"
                                if eleven_month else "2025 full-year annual estimate"),
            "annualAverageMonths": 11 if eleven_month else 12,
            "excludedMonths": ["2025-10"] if eleven_month else [],
            "sourcePeriodQualifier": ("no_october_cps_2025" if eleven_month
                                      else "full_12_months_2025"),
        })
    return projected

def stage(root: Path, data: bytes, series: bytes, areas: bytes, footnotes: bytes) -> dict:
    if not all((data,series,areas,footnotes)):
        raise ValueError("Four original BLS source files are required")
    values = parse_authoritative_annual(data,series,areas,footnotes)
    sources = [(role, url, raw) for (role,url,_),raw in zip(SOURCES,(data,series,areas,footnotes))]
    fingerprint = hashlib.sha256(
        b"".join(hashlib.sha256(raw).digest() for _,_,raw in sources)
    ).hexdigest()[:16]
    release_id = f"bls-laus-state-unemployment-2025-{fingerprint}"
    result = stage_release(
        root, release_id=release_id,
        dataset_id="bls-laus-state-unemployment-2025",
        indicator_id="state-unemployment-rate",
        title="BLS LAUS 2025 unemployment: 11-month averages except 12-month Puerto Rico",
        publisher_name="U.S. Bureau of Labor Statistics",
        geography="state",year=YEAR,vintage=YEAR,geography_vintage=2025,
        observations=values,originals=sources,
        method=("Preserve BLS 2025 M13 published rates with unadjusted "
                "state series, official area/series tables and original "
                "la.footnote definition G. All 50 states and DC exclude "
                "October 2025 and have 11-month annual estimates. Puerto "
                "Rico alone retains a 12-month calendar-year annual rate. "
                "Do not impute the missing month or recompute the published rate."),
        warnings=("BLS 2025 LAUS 11-month annual estimates for states and "
                  "DC omit October and are not strictly comparable with "
                  "prior 12-month annual averages. Puerto Rico is a "
                  "full-year 12-month exception. Rates remain publisher "
                  "estimates, subject to revision, not seasonally adjusted "
                  "monthly observations. Source explanation: "
                  "https://www.bls.gov/lau/launews1.htm"),
    )
    return {"releaseId":release_id,"records":len(values),
            "sourceFingerprints":{role:hashlib.sha256(raw).hexdigest()
                                  for role,_,raw in sources},
            "review":result["diff"]}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-file",type=Path)
    p.add_argument("--series-file",type=Path)
    p.add_argument("--area-file",type=Path)
    p.add_argument("--footnote-file",type=Path)
    p.add_argument("--out-root",type=Path,default=ROOT)
    args=p.parse_args()
    local = [args.data_file,args.series_file,args.area_file,args.footnote_file]
    if any(local) and not all(local):
        p.error("Supply all four original files or allow verified HTTPS acquisition")
    originals = ([x.read_bytes() for x in local] if all(local)
                 else [download_official(url,host="download.bls.gov",limit=limit)
                       for _,url,limit in SOURCES])
    with tempfile.TemporaryDirectory() as temp:
        staging=Path(temp)
        prior=args.out_root/"publication"
        if prior.is_dir():
            shutil.copytree(prior,staging/"publication",dirs_exist_ok=True)
        info=stage(staging,*originals)
        validate_publication(staging)
        src=staging/"publication/releases"/info["releaseId"]
        dst=args.out_root/"publication/releases"/info["releaseId"]
        dst.parent.mkdir(parents=True,exist_ok=True)
        if dst.is_dir():
            shutil.rmtree(dst)
        shutil.copytree(src,dst)
        shutil.copyfile(staging/"publication/index.json",
                        args.out_root/"publication/index.json")
    print(json.dumps(info,sort_keys=True))

if __name__=="__main__":
    main()
