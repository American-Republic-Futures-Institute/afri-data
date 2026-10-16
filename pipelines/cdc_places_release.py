"""Reproducible, source-fingerprinted CDC PLACES 2025 county obesity release.

The 2025 publisher vintage contains model-based prevalence from 2023 BRFSS
inputs. This is descriptive evidence, not policy impact or causal inference.
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
from urllib.parse import urlencode

from pipelines.evidence_publish import stage_release
from pipelines.source_io import download_official
from tools.validate import validate_publication

ROOT=Path(__file__).resolve().parents[1]
DATASET_ID="cdc-places-2025-county-obesity"
INDICATOR_ID="county-modeled-obesity-prevalence"
YEAR=2023
VINTAGE=2025
COUNT=3143
FIELDS=("countyfips","countyname","stateabbr","obesity_crudeprev","obesity_crude95ci")
BASE="https://data.cdc.gov/resource/i46a-9kgh.json"
SOURCE_URL=BASE+"?"+urlencode({
    "$select":",".join(FIELDS),"$order":"countyfips","$limit":"4000"
})
CI=re.compile(r"^\s*\(?\s*(\d+(?:\.\d+)?)\s*[,;-]\s*(\d+(?:\.\d+)?)\s*\)?\s*$")

def numeric(raw, label):
    if raw is None or raw=="":
        return None
    try:
        n=Decimal(str(raw))
        if not n.is_finite() or n<0 or n>100:
            raise ValueError("Out-of-range PLACES "+label)
        return float(n)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Invalid PLACES "+label) from exc

def parse_places(original:bytes) -> list[dict]:
    try:
        source=json.loads(original.decode("utf-8"))
    except (UnicodeError,ValueError) as exc:
        raise ValueError("Invalid original PLACES response") from exc
    if not isinstance(source,list) or len(source)!=COUNT:
        raise ValueError("Unexpected PLACES published county coverage")
    output=[]
    seen=set()
    for src in source:
        if not isinstance(src,dict) or not {"countyfips","countyname","stateabbr"}.issubset(src):
            raise ValueError("PLACES source schema drift (missing geographic identity)")
        # Socrata JSON can omit an individual field entirely when its source
        # value is null. An omitted measurement means unavailable, not zero.
        geoid=src["countyfips"]
        if not isinstance(geoid,str) or not re.fullmatch(r"[0-9]{5}",geoid) or geoid in seen:
            raise ValueError("Invalid or duplicate county FIPS")
        seen.add(geoid)
        state=src["stateabbr"]
        if not isinstance(state,str) or not re.fullmatch(r"[A-Z]{2}",state):
            raise ValueError("Invalid county state abbreviation")
        name=src["countyname"]
        if not isinstance(name,str) or not name.strip():
            raise ValueError("Empty county description")
        value=numeric(src.get("obesity_crudeprev"),"prevalence")
        interval=src.get("obesity_crude95ci")
        lower=upper=None
        if interval not in (None,""):
            if not isinstance(interval,str) or not (m:=CI.fullmatch(interval)):
                raise ValueError("Unsupported CDC model confidence interval notation")
            lower=numeric(m.group(1),"CI lower")
            upper=numeric(m.group(2),"CI upper")
            if lower>upper or (value is not None and not lower<=value<=upper):
                raise ValueError("CDC confidence interval excludes modeled prevalence")
        if value is None and (lower is not None or upper is not None):
            raise ValueError("Model interval without a modeled measurement")
        output.append({
            "geoid":geoid,"name":name,"stateAbbr":state,
            "year":YEAR,"value":value,"unit":"percent",
            "statistic":"model_based_estimate","status":"available" if value is not None else "not_available",
            "confidenceInterval95":interval,
            "lower95":lower,"upper95":upper,
            "referencePeriod":"2023 BRFSS source for obesity measure",
            "publisherVintage":VINTAGE,
        })
    if len(seen)!=COUNT:
        raise ValueError("County FIPS coverage incomplete")
    return sorted(output,key=lambda x:x["geoid"])

def stage(root:Path,original:bytes)->dict:
    observations=parse_places(original)
    release_id="cdc-places-county-obesity-2025-"+sha256(original).hexdigest()[:16]
    result=stage_release(root,release_id=release_id,
        dataset_id=DATASET_ID,indicator_id=INDICATOR_ID,
        title="CDC PLACES 2025 model-based county adult obesity prevalence (2023 inputs)",
        publisher_name="Centers for Disease Control and Prevention",
        geography="county",year=YEAR,vintage=VINTAGE,geography_vintage=2023,
        observations=observations,originals=[("originalData",SOURCE_URL,original)],
        method=("Use CDC PLACES 2025 GIS-friendly county source for the "
                "unadjusted adult obesity crude modeled prevalence and reported "
                "95-percent model confidence interval. The obesity estimate "
                "uses 2023 BRFSS source responses. No county-wide survey "
                "count, interpolation or causal effect is inferred."),
        warnings=("CDC PLACES uses small-area statistical models; these "
                  "values are not direct county measurements and must not "
                  "be used to evaluate the impact of a local intervention. "
                  "2025 is the publisher dataset release, not the modeled "
                  "2023 health reference year."),
    )
    return {"releaseId":release_id,"records":len(observations),
            "sourceSha256":sha256(original).hexdigest(),"review":result["diff"]}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-file",type=Path)
    ap.add_argument("--out-root",type=Path,default=ROOT)
    args=ap.parse_args()
    original=(args.source_file.read_bytes() if args.source_file
              else download_official(SOURCE_URL,host="data.cdc.gov",limit=3_500_000))
    if len(original)>3_500_000: raise SystemExit("CDC response exceeds approved size")
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        previous=args.out_root/"publication"
        if previous.is_dir():
            shutil.copytree(previous,root/"publication",dirs_exist_ok=True)
        info=stage(root,original)
        validate_publication(root)
        source=root/"publication/releases"/info["releaseId"]
        target=args.out_root/"publication/releases"/info["releaseId"]
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.is_dir():shutil.rmtree(target)
        shutil.copytree(source,target)
        shutil.copyfile(root/"publication/index.json",args.out_root/"publication/index.json")
    print(json.dumps(info,sort_keys=True))

if __name__=="__main__":main()
