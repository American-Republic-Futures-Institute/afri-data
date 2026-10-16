"""Strict CDC PLACES 2025 to Census 2023 county GEOID join contract.

All 3,144 Census geometry records are preserved. The 2025 CDC source has
3,143 records, omitting Loving County, TX (48301), while its 187 explicit
null-valued estimates are in Kentucky and Pennsylvania. These are THREE
distinct public visualization states: modeled value, explicit unavailable,
and no source record.

Publisher downloads and proof of exact source values belong to their own
release validators. This module validates only the cross-publisher join.
"""
from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path
import re

from pipelines.census_county_geography import STATES
from tools.release_registry import checked_path
from tools.validate_geography import checked_geography_file

GEOMETRY_PREFIX="census-county-boundaries-2023-20m-"
INDICATOR_ID="county-modeled-obesity-prevalence"
CDC_RELEASE_PREFIX="cdc-places-county-obesity-2025-"
EXPECTED_GEOMETRY=3144
EXPECTED_CDC=3143
CENSUS_ONLY="48301"
NULL_BY_STATE={"21":120,"42":67}


def _geoid(raw: object) -> str:
    if not isinstance(raw,str) or not re.fullmatch(r"[0-9]{5}",raw):
        raise ValueError("County join requires exact five-character GEOID")
    if raw[:2] not in STATES:
        raise ValueError("County join contains unapproved geographic state FIPS")
    return raw


def reconcile_counties(geometry: dict, observations: dict) -> dict:
    """Return a bounded, deterministic audit; never impute or delete records."""
    metadata=geometry.get("metadata")
    features=geometry.get("features")
    if (geometry.get("type")!="FeatureCollection"
            or not isinstance(metadata,dict)
            or metadata.get("publisher")!="U.S. Census Bureau"
            or metadata.get("joinKey")!="GEOID"
            or metadata.get("vintage")!=2023
            or not isinstance(features,list)
            or len(features)!=EXPECTED_GEOMETRY):
        raise ValueError("Unexpected approved Census county geography contract")
    shapes={}
    for feature in features:
        if not isinstance(feature,dict) or not isinstance(feature.get("properties"),dict):
            raise ValueError("Malformed county geometry feature")
        props=feature["properties"]
        geoid=_geoid(props.get("GEOID"))
        name=props.get("NAME")
        if (feature.get("id")!=geoid or props.get("STATEFP")!=geoid[:2]
                or props.get("COUNTYFP")!=geoid[2:]
                or not isinstance(name,str) or not name.strip()):
            raise ValueError("Geographic identity mismatch in source boundary")
        if geoid in shapes:
            raise ValueError("Duplicate Census county GEOID")
        shapes[geoid]=name
    rows=observations.get("observations")
    if (observations.get("schemaVersion")!="1.0.0"
            or observations.get("indicatorId")!=INDICATOR_ID
            or observations.get("geography")!="county"
            or observations.get("joinKey")!="geoid"
            or observations.get("vintage")!=2025
            or not isinstance(rows,list) or len(rows)!=EXPECTED_CDC):
        raise ValueError("Unexpected CDC PLACES source observation contract")
    seen=set()
    missing=Counter()
    available=0
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError("Invalid CDC county observation")
        geoid=_geoid(row.get("geoid"))
        if geoid in seen:
            raise ValueError("Duplicate CDC county observation GEOID")
        seen.add(geoid)
        if (row.get("year")!=2023 or row.get("publisherVintage")!=2025
                or row.get("referencePeriod")!="2023 BRFSS source for obesity measure"
                or row.get("statistic")!="model_based_estimate"
                or row.get("unit")!="percent"):
            raise ValueError("Incompatible CDC statistic or reference period")
        value=row.get("value")
        lo=row.get("lower95")
        hi=row.get("upper95")
        status=row.get("status")
        if status=="not_available":
            if value is not None or lo is not None or hi is not None or row.get("confidenceInterval95") not in (None,""):
                raise ValueError("CDC unavailable record contains a fabricated modeled value or interval")
            missing[geoid[:2]]+=1
        elif status=="available":
            if any(isinstance(v,bool) or not isinstance(v,(float,int))
                   or not math.isfinite(v) or not 0<=v<=100 for v in (value,lo,hi)):
                raise ValueError("CDC modeled prevalence or confidence interval invalid")
            if not lo<=value<=hi:
                raise ValueError("CDC modeled estimate lies outside published 95% interval")
            available+=1
        else:
            raise ValueError("Unrecognized CDC observation availability status")
    unknown=sorted(seen-shapes.keys())
    absent=sorted(shapes.keys()-seen)
    if unknown:
        raise ValueError("CDC has records with no approved county geometry: "+",".join(unknown[:10]))
    if absent!=[CENSUS_ONLY] or shapes.get(CENSUS_ONLY)!="Loving":
        raise ValueError("Unexpected Census-only county GEOIDs; explicit source review required")
    if dict(sorted(missing.items()))!=NULL_BY_STATE or available!=2956:
        raise ValueError("CDC source availability footprint changed; method review required")
    return {
        "schemaVersion":"1.0.0",
        "status":"geographic-crosswalk-verified",
        "geographySource":"U.S. Census Bureau",
        "observationSource":"CDC PLACES",
        "censusBoundaryVintage":2023,
        "cdcPublisherVintage":2025,
        "observationReferenceYear":2023,
        "geometryPolygons":len(shapes),
        "cdcSourceRows":len(seen),
        "matchedGeographies":len(seen),
        "availableModeledEstimates":available,
        "explicitlyUnavailableEstimates":sum(missing.values()),
        "unavailableByStateFips":dict(sorted(missing.items())),
        "censusOnly":[{
            "geoid":CENSUS_ONLY,
            "name":"Loving",
            "stateFips":"48",
            "reason":"no_observation_in_cdc_places_2025",
            "value":None
        }],
        "cdcOnly":[],
        "caution":"Census-only county is not a null-valued CDC record. Do not synthesize an observation or infer a value of zero.",
    }


def validate_published_county_join(root:Path) -> dict:
    """When BOTH approved releases exist, fail closed on geographic drift.

    The current approved Census-only main has neither release. Separate
    human approval of geometry or CDC measurements does not require the
    other to be approved simultaneously.
    """
    main_index=root/"publication/index.json"
    geo_index=root/"publication/geographies/index.json"
    if not main_index.is_file():
        raise ValueError("Missing approved statistical publication index")
    stats=json.loads(main_index.read_text(encoding="utf-8"))
    statistical_releases=[
        r for r in stats["releases"]
        if r.get("indicatorId")==INDICATOR_ID and
        r.get("releaseId","").startswith(CDC_RELEASE_PREFIX)
    ]
    geometries=[]
    if geo_index.is_file():
        geodoc=json.loads(geo_index.read_text(encoding="utf-8"))
        geometries=[
            r for r in geodoc["releases"]
            if r.get("geography")=="county"
            and r.get("vintage")==2023
            and r.get("releaseId","").startswith(GEOMETRY_PREFIX)
        ]
    if not geometries or not statistical_releases:
        return {"countyJoinStatus":"waiting-for-both-approved-source-releases"}
    # Revisions are immutable but may have a changed county population. Do
    # not silently select the "latest" without a reviewed pairing contract.
    if len(geometries)!=1 or len(statistical_releases)!=1:
        raise ValueError("Multiple candidate source revisions require explicit county join review")
    g=geometries[0]["releaseId"]
    c=statistical_releases[0]["releaseId"]
    geography=json.loads(checked_geography_file(root,g,"counties.geojson").read_text(encoding="utf-8"))
    observation_file=checked_path(root,c,"observations.json")
    observations=json.loads(observation_file.read_text(encoding="utf-8"))
    return {"countyJoinStatus":"verified",
            "countyJoin":reconcile_counties(geography,observations)}


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    print(json.dumps(validate_published_county_join(args.root),sort_keys=True))


if __name__=="__main__":
    main()
