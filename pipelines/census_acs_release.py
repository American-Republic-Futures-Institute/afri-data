"""Secure reproducible acquisition and staging for official ACS 2024 state income.

The API key is used for transport only; it is forbidden in output artifacts,
provenance URLs and logs. This pipeline never merges published data into main.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from urllib.parse import urlencode

from pipelines.census_acs_income import (
    ACS_YEAR, ESTIMATE, MOE, OFFICIAL_URL, parse_acs_state_income,
)
from pipelines.census_state_population import FIPS
from pipelines.evidence_publish import stage_release
from pipelines.source_io import download_official
from tools.validate import validate_publication

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_QUERY = urlencode({"get":f"NAME,{ESTIMATE},{MOE}","for":"state:*"})
PUBLIC_URL = f"{OFFICIAL_URL}?{PUBLIC_QUERY}"
DATASET_ID = "census-acs5-state-income-2024"
INDICATOR_ID = "state-median-household-income"


def project(original: bytes) -> list[dict]:
    rows = parse_acs_state_income(original)
    geographic_ids={row["geoid"] for row in rows}
    if geographic_ids != FIPS:
        raise ValueError("ACS coverage differs from the 52 approved state and equivalent identifiers")
    if len(rows) != 52:
        raise ValueError("Duplicate or incomplete ACS state projection")
    return rows


def stage(root: Path, original: bytes) -> dict:
    rows = project(original)
    content_fingerprint = sha256(original).hexdigest()[:16]
    rid = f"census-acs5-state-income-2024-{content_fingerprint}"
    result=stage_release(
        root, release_id=rid,dataset_id=DATASET_ID,indicator_id=INDICATOR_ID,
        title="Census 2024 five-year median household income by state (2024 USD)",
        publisher_name="U.S. Census Bureau",
        geography="state",year=ACS_YEAR,vintage=ACS_YEAR,
        geography_vintage=2024,first_year=2024,last_year=2024,
        observations=rows,originals=[("originalData",PUBLIC_URL,original)],
        method=("Use the official 2024 five-year ACS Detailed Table B19013; "
                "preserve state GEOID strings, B19013_001E estimate, B19013_001M "
                "margin of error, source suppression codes, and separate "
                "published statistical status. Reference period is 2020–2024, "
                "with dollar values expressed in inflation-adjusted 2024 USD."),
        warnings=("These are model-assisted five-year ACS survey estimates, "
                  "not a single-calendar-year income census. 2020–2024 "
                  "pooled periods, median income MOE and response suppression "
                  "require explicit display. Do not use absent values as zero."),
    )
    return {"releaseId":rid, "records":len(rows),
            "sourceSha256":sha256(original).hexdigest(),
            "review":result["diff"]}


def acquire(key: str) -> bytes:
    if (not key or len(key)>256 or any(ch in key for ch in "\r\n\t &?#")):
        raise ValueError("CENSUS_API_KEY is not configured or contains invalid characters")
    # urllib may include the original URL in HTTP exceptions. source_io catches
    # and replaces all such exceptions before they can be surfaced in workflow logs.
    remote = PUBLIC_URL + "&" + urlencode({"key":key})
    return download_official(remote,host="api.census.gov",limit=1_000_000)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-file",type=Path)
    parser.add_argument("--out-root",type=Path,default=ROOT)
    args=parser.parse_args()
    if args.source_file is not None:
        original=args.source_file.read_bytes()
        if len(original)>1_000_000:
            raise SystemExit("Source file exceeds approved ACS response limit")
    else:
        key=os.environ.get("CENSUS_API_KEY","")
        if not key:
            raise SystemExit("CENSUS_API_KEY workflow secret required for live Census ACS acquisition")
        original=acquire(key)
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        prior=args.out_root/"publication"
        if prior.is_dir():
            shutil.copytree(prior,root/"publication",dirs_exist_ok=True)
        summary=stage(root,original)
        validate_publication(root)
        release=root/"publication/releases"/summary["releaseId"]
        target=args.out_root/"publication/releases"/summary["releaseId"]
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.is_dir():
            shutil.rmtree(target)
        shutil.copytree(release,target)
        shutil.copyfile(root/"publication/index.json",args.out_root/"publication/index.json")
    print(json.dumps(summary,sort_keys=True))


if __name__ == "__main__":
    main()
