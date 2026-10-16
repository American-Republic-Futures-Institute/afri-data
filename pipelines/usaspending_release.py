"""USAspending FY2025 award transaction obligation geography evidence.

Source: authoritative USAspending.gov /api/v2/search/spending_by_geography/
POST. This measures reported obligation transactions attributed to primary
place of performance, NOT cash outlays, program outcomes or delivery benefits.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import tempfile

from pipelines.census_state_population import FIPS
from pipelines.evidence_publish import stage_release
from pipelines.source_io import post_official_json
from tools.validate import validate_publication

ROOT=Path(__file__).resolve().parents[1]
ENDPOINT="https://api.usaspending.gov/api/v2/search/spending_by_geography/"
DATASET_ID="usaspending-state-fy2025-obligations"
INDICATOR_ID="state-federal-award-obligations"
PERIOD={"start_date":"2024-10-01","end_date":"2025-09-30"}
REQUEST={
    "filters":{
        "time_period":[PERIOD],
        "place_of_performance_scope":"domestic"
    },
    "scope":"place_of_performance",
    "geo_layer":"state",
    "spending_level":"transactions"
}
REQUEST_BYTES=(json.dumps(REQUEST,ensure_ascii=False,sort_keys=True,
    separators=(",",":"))+"\n").encode("utf-8")
USPS_TO_FIPS={
    "AL":"01","AK":"02","AZ":"04","AR":"05","CA":"06","CO":"08",
    "CT":"09","DE":"10","DC":"11","FL":"12","GA":"13","HI":"15",
    "ID":"16","IL":"17","IN":"18","IA":"19","KS":"20","KY":"21",
    "LA":"22","ME":"23","MD":"24","MA":"25","MI":"26","MN":"27",
    "MS":"28","MO":"29","MT":"30","NE":"31","NV":"32","NH":"33",
    "NJ":"34","NM":"35","NY":"36","NC":"37","ND":"38","OH":"39",
    "OK":"40","OR":"41","PA":"42","RI":"44","SC":"45","SD":"46",
    "TN":"47","TX":"48","UT":"49","VT":"50","VA":"51","WA":"53",
    "WV":"54","WI":"55","WY":"56","PR":"72"
}
EXCLUDED_TERRITORIES=frozenset(("AS","GU","MP","VI"))
assert set(USPS_TO_FIPS.values()) == FIPS and len(USPS_TO_FIPS)==52

def project(original: bytes, request: bytes=REQUEST_BYTES) -> list[dict]:
    if request != REQUEST_BYTES:
        raise ValueError("USAspending evidence request differs from approved filters")
    try:
        result=json.loads(original.decode("utf-8"),parse_float=Decimal,parse_int=Decimal)
    except (UnicodeError,ValueError) as exc:
        raise ValueError("Invalid Treasury USAspending response") from exc
    if not isinstance(result,dict):
        raise ValueError("Invalid USAspending response envelope")
    for field,value in (("scope","place_of_performance"),("geo_layer","state"),
                         ("spending_level","transactions")):
        if result.get(field)!=value:
            raise ValueError("USAspending scope or aggregation mismatch: "+field)
    entries=result.get("results")
    if not isinstance(entries,list) or not 40<=len(entries)<=90:
        raise ValueError("USAspending unexpected geographic result count")
    projected=[]
    seen=set()
    for row in entries:
        if not isinstance(row,dict):
            raise ValueError("Invalid USAspending geographic item")
        code=row.get("shape_code")
        if not isinstance(code,str) or not re.fullmatch(r"[A-Z]{2}",code):
            raise ValueError("USAspending invalid state shape code")
        if code in seen:
            raise ValueError("Duplicate USAspending state code")
        seen.add(code)
        if code in EXCLUDED_TERRITORIES:
            continue
        if code not in USPS_TO_FIPS:
            raise ValueError("Unexpected USAspending geographic code; requires source review")
        name=row.get("display_name")
        if not isinstance(name,str) or not name.strip() or len(name)>120:
            raise ValueError("Missing USAspending geographic label")
        amount=row.get("aggregated_amount")
        if isinstance(amount,bool) or amount is None:
            raise ValueError("Missing or invalid published obligation amount")
        try:
            parsed=Decimal(str(amount))
        except (ValueError,InvalidOperation) as exc:
            raise ValueError("Invalid obligation amount") from exc
        if not parsed.is_finite() or abs(parsed)>Decimal("1e17"):
            raise ValueError("Nonfinite or out-of-range obligation value")
        approximate=float(parsed)
        projected.append({
            "geoid":USPS_TO_FIPS[code],"postalCode":code,
            "name":name.strip(),"year":2025,
            "value":approximate,"reportedAmount":str(parsed),
            "unit":"USD","status":"available",
            "statistic":"reported_award_transaction_obligations",
            "referencePeriod":"FY2025 (2024-10-01 to 2025-09-30)",
            "locationBasis":"primary_place_of_performance",
            "spendingLevel":"transactions",
        })
    if len(projected)<40:
        raise ValueError("USAspending source does not cover sufficient states")
    return sorted(projected,key=lambda x:x["geoid"])

def stage(root:Path,original:bytes, request:bytes=REQUEST_BYTES)->dict:
    observations=project(original,request)
    fp=sha256(sha256(original).digest()+sha256(request).digest()).hexdigest()[:16]
    rid="usaspending-fy2025-state-obligations-"+fp
    outcome=stage_release(root,release_id=rid,
        dataset_id=DATASET_ID,indicator_id=INDICATOR_ID,
        title="FY2025 USAspending federal award transaction obligations by state",
        publisher_name="USAspending.gov / U.S. Treasury",
        geography="state",year=2025,vintage=2025,geography_vintage=2025,
        observations=observations,
        originals=[("originalData",ENDPOINT,original),("requestBody",ENDPOINT,request)],
        method=("The USAspending API groups FY2025 award federal-action "
                "transaction obligations by primary place of performance. "
                "The archived POST request pins all filters, FY action dates "
                "2024-10-01 through 2025-09-30, geography state, spending "
                "level transactions. Preserve signed obligation adjustments "
                "and full original amount precision as strings. No "
                "recipient-location inference, imputation or outlay claim."),
        warnings=("These published administrative aggregates are award "
                  "obligations, not cash outlays, economic benefits or "
                  "measured policy outcomes. USAspending reporting can be "
                  "revised and place-of-performance is a reporting attribute."),
    )
    return {"releaseId":rid,"records":len(observations),
            "sourceSha256":sha256(original).hexdigest(),
            "requestSha256":sha256(request).hexdigest(),
            "review":outcome["diff"]}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--response-file",type=Path)
    parser.add_argument("--out-root",type=Path,default=ROOT)
    args=parser.parse_args()
    response=(args.response_file.read_bytes() if args.response_file
              else post_official_json(ENDPOINT,REQUEST_BYTES,host="api.usaspending.gov",limit=1_000_000))
    if len(response)>1_000_000:raise SystemExit("Official USAspending source response too large")
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        prior=args.out_root/"publication"
        if prior.is_dir():
            shutil.copytree(prior,root/"publication",dirs_exist_ok=True)
        info=stage(root,response)
        validate_publication(root)
        source=root/"publication/releases"/info["releaseId"]
        dest=args.out_root/"publication/releases"/info["releaseId"]
        dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.is_dir():shutil.rmtree(dest)
        shutil.copytree(source,dest)
        shutil.copyfile(root/"publication/index.json",
                        args.out_root/"publication/index.json")
    print(json.dumps(info,sort_keys=True))

if __name__=="__main__":
    main()
