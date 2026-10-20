"""Secure reproducible acquisition and staging for official ACS 2024 state income.

Downloads Census's public table-based 5-year B19013 Summary File without an
API key. Archives all publisher bytes, projects only 52 state-equivalent rows,
and records estimate, original margin of error and suppression status.
This pipeline never merges its candidate release into main.
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
    ACS_YEAR, ESTIMATE, MOE, OFFICIAL_URL, parse_acs_state_income, parse_acs_table_based_income,
)
from pipelines.census_state_population import FIPS
from pipelines.evidence_publish import stage_release
from pipelines.source_io import download_official
from tools.validate import validate_publication

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_QUERY = urlencode({"get":f"NAME,{ESTIMATE},{MOE}","for":"state:*"})
PUBLIC_URL = f"{OFFICIAL_URL}?{PUBLIC_QUERY}"
STATIC_URL = ("https://www2.census.gov/programs-surveys/acs/summary_file/2024/"
              "table-based-SF/data/5YRData/acsdt5y2024-b19013.dat")
DATASET_ID = "census-acs5-state-income-2024"
INDICATOR_ID = "state-median-household-income"


def project(original: bytes) -> list[dict]:
    rows = parse_acs_table_based_income(original)
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
        observations=rows,originals=[("originalData",STATIC_URL,original)],
        method=("Source: official Census 2024 ACS five-year table-based Summary File B19013; "
                "select only original 0400000USxx publisher geographies. "
                "Preserve the GEO_ID, B19013_E001 estimate and B19013_M001 "
                "margin of error, equivalent to API B19013_001E/B19013_001M. "
                "No summing state medians, recalculating uncertainty, or imputation. "
                "Reference period 2020-2024, inflation-adjusted 2024 USD."),
        warnings=("ACS 2020-2024 pooled survey estimate in 2024 inflation-adjusted USD; "
                  "not a single-year 2024 income measurement. Census B19013 published "
                  "margin of error is a 90-percent survey MOE, not a standard "
                  "deviation or a newly computed confidence interval. "
                  "Unavailable and suppressed values remain null, never zero. "
                  "State medians are not additive or household-weighted."),
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


def acquire_static() -> bytes:
    """Acquire only the official publisher-hosted immutable 2024 B19013 table file."""
    return download_official(STATIC_URL,host="www2.census.gov",limit=22_000_000)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-file",type=Path)
    parser.add_argument("--out-root",type=Path,default=ROOT)
    args=parser.parse_args()
    if args.source_file is not None:
        original=args.source_file.read_bytes()
        if len(original)>22_000_000:
            raise SystemExit("Source file exceeds approved ACS original-table limit")
    else:
        # Key-free official table-based summary download, not the authenticated API.
        original=acquire_static()
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
