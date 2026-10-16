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

def parse_authoritative_annual(data: bytes, series: bytes, areas: bytes) -> list[dict]:
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
        projected.append({**row, "name": name,
                          "referencePeriod": "2025 annual average"})
    return projected

def stage(root: Path, data: bytes, series: bytes, areas: bytes) -> dict:
    if not all((data,series,areas)):
        raise ValueError("Complete original source triplet required")
    values = parse_authoritative_annual(data,series,areas)
    sources = [(role, url, raw) for (role,url,_),raw in zip(SOURCES,(data,series,areas))]
    fingerprint = hashlib.sha256(
        b"".join(hashlib.sha256(raw).digest() for _,_,raw in sources)
    ).hexdigest()[:16]
    release_id = f"bls-laus-state-unemployment-2025-{fingerprint}"
    result = stage_release(
        root, release_id=release_id,
        dataset_id="bls-laus-state-unemployment-2025",
        indicator_id="state-unemployment-rate",
        title="BLS LAUS state annual unemployment rate, unadjusted, 2025",
        publisher_name="U.S. Bureau of Labor Statistics",
        geography="state",year=YEAR,vintage=YEAR,geography_vintage=2025,
        observations=values,originals=sources,
        method=("Select 2025 M13 annual-average unemployment-rate observations "
                "from the official BLS LAUS unadjusted state file. Validate "
                "each series against the original BLS series and area files "
                "for measure code 03, seasonal U and area type A. No rate "
                "normalization or derived annual average was performed."),
        warnings=("Source is the BLS published annual-average estimate and "
                  "may be revised. Geographic areas include states, DC and "
                  "Puerto Rico when independently verified. Annual M13 "
                  "must not be confused with monthly seasonally adjusted rates."),
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
    p.add_argument("--out-root",type=Path,default=ROOT)
    args=p.parse_args()
    local = [args.data_file,args.series_file,args.area_file]
    if any(local) and not all(local):
        p.error("Supply all three original files or allow verified HTTPS acquisition")
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
