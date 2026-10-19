"""STAT-05: immutable source-reproduced region and state descriptive cohorts.

Every numeric chart is precomputed with the existing NumPy StatKit. State-level
Census/BLS selections with one jurisdiction are SOURCE OBSERVATIONS, never
misrepresented as distributions. Source-native map links are presentation only.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
from pathlib import Path

from arfi_stats import histogram, ecdf, boxplot
from arfi_stats.artifacts import ROOT, canonical_bytes, file_hash, hash_json, schema_check
from arfi_stats.census_pilot import _source as census_source, produce as census_pilot, STATE_EQUIVALENT_FIPS
from tools.stat04_descriptive import (
    DATASETS, KINDS, _profile_source, _bls, _cdc, verify_method_applicability,
)
from tools.stat05_geography import STATE_NAMES, REGIONS, REGION_OF

DIRECTORY = ROOT / "publication" / "descriptive" / "cohorts"
BUNDLE_SCHEMA = "ARFI-DescriptiveGeographicCohorts/1.0.0"
CATALOG_SCHEMA = "ARFI-DescriptiveGeographicCatalog/1.0.0"
SHA256 = "sha256"

def require(condition, reason):
    if not condition:
        raise ValueError("STAT-05 source-bound cohort refused: " + reason)

def source_records(dataset):
    """Preserve the original publisher's observation unit, periods and nulls."""
    spec=DATASETS[dataset]
    profile, original, manifest_sha=_profile_source(dataset)
    expected_fips=set(STATE_NAMES)
    if dataset=="census":
        verified, rows=census_source()
        require(profile==verified and len(original)==312 and
                len(rows)==52 and {x["fips"] for x in rows}==expected_fips,
                "Census six-year source and 2025 jurisdiction scope changed")
        chosen=[x for x in original if x["year"]==2025]
        records=[]
        for r in chosen:
            require(r["fips"] in STATE_NAMES and
                    r["name"]==STATE_NAMES[r["fips"]] and
                    r["unit"]=="persons" and
                    r["measure"]=="resident_population_estimate" and
                    r["statistic"]=="published_estimate" and
                    type(r["value"]) is int and r["value"]>0,
                    "invalid source-native Census resident estimate")
            records.append({
                "id":r["fips"],"stateFips":r["fips"],"name":r["name"],
                "status":"available","value":r["value"],
            })
        require(len(records)==52,"incomplete 2025 Census selected observations")
        for method in KINDS:
            census_pilot(method)  # existing deterministic applicability check
    elif dataset=="bls":
        _bls()  # validates all 52 annual source records including PR's different period
        records=[]
        for r in original:
            require(r["geoid"] in expected_fips and
                    r["name"]==STATE_NAMES[r["geoid"]],
                    "BLS state identity is outside the published source universe")
            pr=r["geoid"]=="72"
            records.append({
                "id":r["geoid"],"stateFips":r["geoid"],"name":r["name"],
                "status":"excluded_noncomparable_period" if pr else "available",
                "value":r["value"],
                "sourcePeriod":"2025 full-year 12-month estimate" if pr else
                               "2025 11-month annual estimate excluding October",
            })
        require(len(records)==52 and
                sum(r["status"]=="excluded_noncomparable_period" for r in records)==1,
                "BLS Puerto Rico exclusion must not become zero or missing")
        for method in KINDS:verify_method_applicability(profile,method)
    else:
        _cdc() # validates 3,143 actual CDC source records, intervals and missingness
        records=[]
        for r in original:
            fips=r["geoid"][:2]
            require(fips in STATE_NAMES and fips!="72" and
                    r["geoid"]!="48301" and
                    r["status"] in ("available","not_available"),
                    "a CDC county identifier or source availability changed")
            records.append({
                "id":r["geoid"],"stateFips":fips,"name":r["name"],
                "status":r["status"],"value":r["value"],
                "lower95":r["lower95"],"upper95":r["upper95"],
            })
        require(len(records)==3143 and
                sum(r["status"]=="available" for r in records)==2956 and
                sum(r["status"]=="not_available" for r in records)==187,
                "original CDC publisher coverage changed")
        for method in KINDS:verify_method_applicability(profile,method)

    records.sort(key=lambda r:r["id"])
    require(len({r["id"] for r in records})==len(records),"duplicate source geography")
    return profile, records, manifest_sha

def chart_for(records, method, unit):
    """Compute one immutable descriptive distribution, never in the browser."""
    rows=[{"value":r["value"],"availability":r["status"]}
          for r in records if r["status"] in ("available","not_available")]
    if sum(r["availability"]=="available" for r in rows)<2:
        return None
    opts={"x":"value","availability":"availability","unit":unit}
    if method=="histogram":chart=histogram(rows,bins="fd",scale="count",**opts)
    elif method=="ecdf":chart=ecdf(rows,**opts)
    else:chart=boxplot(rows,**opts)
    schema_check(chart,"stat-chart-preview.schema.json")
    available=sum(r["availability"]=="available" for r in rows)
    unavailable=sum(r["availability"]=="not_available" for r in rows)
    require(chart["selection"]["inputRows"]==len(rows) and
            chart["selection"]["selectedRows"]==len(rows) and
            chart["selection"]["missingness"]["available"]==available and
            chart["selection"]["missingness"]["not_available"]==unavailable and
            chart["series"][0]["n"]==available and
            all(chart["authority"][k] is False for k in (
                "sourceVerified","publicationAuthorized","crossSourceAuthorized",
                "statisticalInferenceAuthorized","causalInferenceAuthorized")),
            "precomputed chart scope, availability or authority changed")
    if method=="histogram":
        require(sum(p["count"] for p in chart["series"][0]["points"])==available,
                "histogram denominator did not reproduce")
    elif method=="ecdf":
        require(chart["series"][0]["points"][-1]["cumulative"]==1 and
                sum(p["countAtX"] for p in chart["series"][0]["points"])==available,
                "ECDF denominator changed")
    else:
        q=chart["series"][0]["statistics"]
        require(q is not None and q["min"]<=q["q1"]<=q["median"]<=q["q3"]<=q["max"],
                "source-specific boxplot quantiles invalid")
    return {"chartSha256":hash_json(chart),"chart":chart}

def cohort(dataset,scope,code,all_records):
    spec=DATASETS[dataset]
    require(scope in ("region","state"),"only published region/state scopes")
    if scope=="region":
        require(code in REGIONS,"unknown Census region")
        members=set(REGIONS[code]["members"])
        name=REGIONS[code]["name"]
    else:
        require(code in STATE_NAMES and (dataset!="cdc" or code!="72"),
                "unknown state or unsupported publisher geography")
        members={code}
        name=STATE_NAMES[code]
    selected=[r for r in all_records if r["stateFips"] in members]
    available=sum(r["status"]=="available" for r in selected)
    missing=sum(r["status"]=="not_available" for r in selected)
    excluded=sum(r["status"]=="excluded_noncomparable_period" for r in selected)
    require(len(selected)==available+missing+excluded and
            (dataset=="bls" or excluded==0) and
            (dataset=="cdc" or missing==0),
            "source-native status/qualification counts changed")
    if dataset=="cdc" and scope=="region":
        # For large regional views the accessible drilldown lists each state's
        # actual county source and availability counts, not synthetic mean rates.
        display=[]
        for fips in sorted(members):
            rows=[r for r in selected if r["stateFips"]==fips]
            require(len(rows)>0,"regional CDC state missing from source")
            display.append({
                "id":fips,"stateFips":fips,"name":STATE_NAMES[fips],
                "sourceRows":len(rows),
                "availableRows":sum(r["status"]=="available" for r in rows),
                "unavailableRows":sum(r["status"]=="not_available" for r in rows),
            })
        kind="state-coverage-summary"
    else:
        display=list(selected)
        kind="source-observations"
    charts=({m:chart_for(selected,m,spec["unit"]) for m in KINDS}
            if available>=2 else {})
    status=("available" if available>=2 else
            "single-observation" if available==1 else
            "excluded-period" if excluded else "unavailable")
    if dataset=="cdc" and scope=="state" and code in ("21","42"):
        require(available==0 and missing==len(selected) and
                len(selected)==(120 if code=="21" else 67) and
                charts=={} and status=="unavailable",
                "KY/PA publisher unavailable counties must not render statistics")
    return {
        "scope":scope,"code":code,"name":name,
        "stateFips":sorted(members),
        "sourceRows":len(selected),
        "selectedRows":len(selected)-excluded,
        "availableRows":available,"unavailableRows":missing,
        "excludedRows":excluded,
        "status":status,
        "sourceSliceSha256":hash_json([
            {"id":r["id"],"status":r["status"],"value":r["value"]}
            for r in selected
        ]),
        "recordType":kind,
        "records":display,
        "methods":charts,
    }

def build(dataset):
    require(dataset in DATASETS,"unknown publisher dataset")
    spec=DATASETS[dataset]
    profile,rows,manifest_sha=source_records(dataset)
    codes=list(REGIONS)
    state_codes=[s for s in STATE_NAMES if dataset!="cdc" or s!="72"]
    cohorts={}
    for code in codes:
        cohorts["region:"+code]=cohort(dataset,"region",code,rows)
    for code in state_codes:
        cohorts["state:"+code]=cohort(dataset,"state",code,rows)
    if dataset=="census":
        require(len(cohorts)==56 and
                sum(c["availableRows"] for k,c in cohorts.items()
                    if k.startswith("region:"))==51 and
                cohorts["state:72"]["availableRows"]==1,
                "Census regions omit PR while national includes PR")
    elif dataset=="bls":
        require(len(cohorts)==56 and
                sum(c["availableRows"] for k,c in cohorts.items()
                    if k.startswith("region:"))==51 and
                cohorts["state:72"]["excludedRows"]==1 and
                cohorts["state:72"]["availableRows"]==0,
                "BLS 11-month cohort must not contain Puerto Rico 12-month")
    else:
        require(len(cohorts)==55 and
                sum(c["availableRows"] for k,c in cohorts.items()
                    if k.startswith("region:"))==2956 and
                sum(c["unavailableRows"] for k,c in cohorts.items()
                    if k.startswith("region:"))==187,
                "CDC regional cohorts must exactly partition 2,956+187")
    return {
        "schemaVersion":"1.0.0","type":BUNDLE_SCHEMA,
        "dataset":dataset,"sourceReleaseId":spec["releaseId"],
        "sourceCommit":profile["identity"]["sourceCommit"],
        "sourceObservationsSha256":profile["identity"]["observationsSha256"],
        "sourceManifestSha256":manifest_sha,
        "referenceYear":spec["sourceYear"],"referencePeriod":spec["period"],
        "measurementUnit":spec["unit"],
        "publicationStatus":"published-reproducible-descriptive",
        "reviewStatus":"not-independently-reviewed",
        "sourceRows":profile["coverage"]["sourceRows"],
        "cohorts":cohorts,
    }

def catalog(bundles=None):
    bundles=bundles or {k:build(k) for k in DATASETS}
    entries={}
    for key,bundle in bundles.items():
        entries[key]={
            "bundlePath":"publication/descriptive/cohorts/"+key+".json",
            "bundleSha256":hashlib.sha256(canonical_bytes(bundle)).hexdigest(),
            "sourceReleaseId":bundle["sourceReleaseId"],
            "observationsSha256":bundle["sourceObservationsSha256"],
            "sourceRows":bundle["sourceRows"],
            "referenceYear":bundle["referenceYear"],
            "referencePeriod":bundle["referencePeriod"],
            "unit":bundle["measurementUnit"],
            "scopes":[{
                "id":ident,"scope":entry["scope"],"code":entry["code"],
                "name":entry["name"],"sourceRows":entry["sourceRows"],
                "availableRows":entry["availableRows"],
                "unavailableRows":entry["unavailableRows"],
                "excludedRows":entry["excludedRows"],
                "status":entry["status"],
            } for ident,entry in bundle["cohorts"].items()]
        }
    return {
        "schemaVersion":"1.0.0","type":CATALOG_SCHEMA,
        "publicationStatus":"published-reproducible-descriptive",
        "reviewStatus":"not-independently-reviewed",
        "regions":{key:{"name":value["name"],"states":list(value["members"])}
                   for key,value in REGIONS.items()},
        "states":STATE_NAMES,
        "datasets":entries,
    }

def validate_artifacts():
    bundles={dataset:build(dataset) for dataset in DATASETS}
    actual={}
    for dataset,expected in bundles.items():
        path=DIRECTORY/(dataset+".json")
        require(path.is_file(),"missing published geographic cohort bundle: "+dataset)
        raw=path.read_bytes()
        require(raw==canonical_bytes(expected),
                "immutable cohort bundle differs from exact source replay: "+dataset)
        actual[dataset]=len(expected["cohorts"])
    manifest=DIRECTORY/"catalog.json"
    require(manifest.is_file() and manifest.read_bytes()==canonical_bytes(catalog(bundles)),
            "cohort catalog differs from source-bound artifacts or region roster")
    return {"datasets":len(bundles),"cohorts":actual,
            "chartSets":sum(sum(bool(c["methods"]) for c in bundle["cohorts"].values())
                            for bundle in bundles.values()),
            "ky":"unavailable","pa":"unavailable","blsPuertoRico":"excluded-not-missing"}

def output_chunks(label,blob):
    # Use bounded log lines to transport exact producer output once into repo,
    # then CI operates solely on the materialized immutable published JSON.
    s=base64.b64encode(blob).decode("ascii")
    parts=[s[i:i+8000] for i in range(0,len(s),8000)]
    print("STAT05_PARTS_"+label+"="+str(len(parts)))
    for i,part in enumerate(parts):print("STAT05_"+label+"_"+str(i)+"="+part)

def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("command",choices=("fixture","verify"))
    args=cli.parse_args()
    if args.command=="fixture":
        bundles={dataset:build(dataset) for dataset in DATASETS}
        for dataset,bundle in bundles.items():
            output_chunks(dataset.upper(),canonical_bytes(bundle))
            print("STAT05_COUNTS_"+dataset.upper()+"="+str(len(bundle["cohorts"])))
        output_chunks("CATALOG",canonical_bytes(catalog(bundles)))
    else:print(json.dumps(validate_artifacts(),indent=2,sort_keys=True))

if __name__=="__main__":main()
