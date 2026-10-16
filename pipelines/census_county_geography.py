"""Reproducible Census 2023 county cartographic geometry, 1:20m scale.

Geography is published separately from statistical observations so CDC PLACES,
ACS and subsequent indicators can join on the same independently sourced
county GEOIDs without attributing a Census polygon to the CDC publisher.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

import shapefile

from pipelines.census_state_population import FIPS
from pipelines.evidence_publish import json_bytes
from pipelines.source_io import download_official
from tools.release_registry import valid_id

ROOT=Path(__file__).resolve().parents[1]
SOURCE_URL="https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_20m.zip"
VINTAGE=2023
EXPECTED=3143
STATES=FIPS-{"72"}
RELEASE_PREFIX="census-county-boundaries-2023-20m"
ROOT_DIR=Path("publication/geographies/releases")
INDEX_PATH=Path("publication/geographies/index.json")
EXTENSIONS=frozenset((".shp",".shx",".dbf",".prj",".cpg"))


def archive_members(raw: bytes) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            infos=z.infolist()
            if not 3<=len(infos)<=12 or sum(x.file_size for x in infos)>30_000_000:
                raise ValueError("County cartographic source archive has unsafe size/count")
            members={}
            seen=set()
            prefix="cb_2023_us_county_20m."
            shape_extensions=frozenset(("shp","shx","dbf","prj","cpg"))
            # Census places explanatory FGDC/ISO metadata XML next to SHP
            # components in its official downloads. Preserve all of those
            # original bytes inside the ZIP, but parse only shapefile data.
            metadata_extensions=frozenset((
                "shp.iso.xml","shp.ea.iso.xml","shp.xml",
            ))
            for item in infos:
                name=Path(item.filename).name
                if item.is_dir() or name != item.filename or not name.startswith(prefix):
                    raise ValueError("Unexpected county source archive member")
                suffix=name[len(prefix):]
                if suffix not in shape_extensions | metadata_extensions:
                    # Filename is attacker-controlled; never echo arbitrary
                    # text into validation logs. Fail closed on schema drift.
                    raise ValueError("Unexpected county source archive member")
                if name in seen:
                    raise ValueError("Duplicate Census county archive member")
                seen.add(name)
                if item.file_size>25_000_000 or item.flag_bits & 1:
                    raise ValueError("Unsafe/encrypted county archive member")
                if suffix in metadata_extensions:
                    # Archive retained byte-for-byte in original.zip. No XML
                    # parsing or XML-derived data enters geometry projection.
                    continue
                members["."+suffix]=z.read(item)
            if not {".shp",".shx",".dbf"}.issubset(members):
                raise ValueError("Incomplete Census county shapefile components")
            return members
    except (zipfile.BadZipFile,EOFError,RuntimeError) as exc:
        raise ValueError("Invalid Census cartographic zip") from exc


def validate_geometry_shape(geometry: dict) -> None:
    if geometry.get("type") not in ("Polygon","MultiPolygon"):
        raise ValueError("Non-polygon county shape")
    count=0
    def walk(obj):
        nonlocal count
        if (isinstance(obj,(tuple,list)) and len(obj)>=2
                and all(isinstance(v,(int,float)) and not isinstance(v,bool)
                        for v in obj[:2])):
            import math
            lon,lat=obj[:2]
            if not math.isfinite(lon) or not math.isfinite(lat) or not (-180<=lon<=180 and -90<=lat<=90):
                raise ValueError("Invalid county polygon coordinate")
            count+=1
        elif isinstance(obj,(tuple,list)):
            for part in obj:
                walk(part)
        else:
            raise ValueError("Malformed polygon coordinate")
    walk(geometry.get("coordinates"))
    if count<4:
        raise ValueError("Incomplete county polygon geometry")


def parse_county_geometries(raw_zip: bytes) -> dict:
    members=archive_members(raw_zip)
    reader=shapefile.Reader(shp=io.BytesIO(members[".shp"]),
                            shx=io.BytesIO(members[".shx"]),
                            dbf=io.BytesIO(members[".dbf"]))
    features={}
    try:
        for item in reader.iterShapeRecords():
            row=item.record.as_dict()
            state=row.get("STATEFP")
            if state not in STATES:
                continue
            code=row.get("COUNTYFP")
            geoid=row.get("GEOID")
            if (not isinstance(state,str) or not isinstance(code,str)
                    or not isinstance(geoid,str)
                    or not re.fullmatch(r"[0-9]{3}",code)
                    or not re.fullmatch(r"[0-9]{5}",geoid)
                    or geoid!=state+code):
                raise ValueError("Inconsistent county GEOID / STATEFP / COUNTYFP")
            if geoid in features:
                raise ValueError("Duplicate county FIPS in Census archive")
            name=row.get("NAME")
            if not isinstance(name,str) or not name.strip() or len(name)>180:
                raise ValueError("Missing county name")
            geom=item.shape.__geo_interface__
            validate_geometry_shape(geom)
            features[geoid]={
                "type":"Feature","id":geoid,
                "properties":{"GEOID":geoid,"NAME":name,"STATEFP":state,
                              "COUNTYFP":code,"vintage":VINTAGE},
                "geometry":geom,
            }
    finally:
        reader.close()
    observed_states={v["properties"]["STATEFP"] for v in features.values()}
    if len(features)!=EXPECTED or observed_states!=STATES:
        # Government geographic-vintage changes must be reviewed, not silently
        # removed or padded to match another publisher's statistical universe.
        counts={}
        for row in features.values():
            code=row["properties"]["STATEFP"]
            counts[code]=counts.get(code,0)+1
        # Controlled FIPS-only diagnostic: no source paths, arbitrary labels,
        # ZIP member names or untrusted data reflected into CI logs.
        raise ValueError(
            f"Census 2023 county geometry coverage mismatch: sourceCount={len(features)}, "
            f"expectedCount={EXPECTED}, observedStateCount={len(observed_states)}, "
            f"missingStateFips={sorted(STATES-observed_states)}, "
            f"unexpectedStateFips={sorted(observed_states-STATES)}, "
            f"stateFipsCounts={sorted(counts.items())}"
        )
    return {
        "type":"FeatureCollection",
        "metadata":{
            "publisher":"U.S. Census Bureau","vintage":VINTAGE,
            "cartographicScale":"1:20,000,000","joinKey":"GEOID",
            "coverage":"50 states and District of Columbia; excludes Puerto Rico and other Island Areas",
            "sourceDatum":"NAD83 (EPSG:4269); map visualization only, no surveyed/legal boundary claim",
            "purpose":"generalized thematic mapping; independent from statistical observation publishers",
        },
        "features":[features[k] for k in sorted(features)],
    }


def stage(root: Path, raw_zip: bytes) -> dict:
    if not isinstance(raw_zip,bytes) or not 1<=len(raw_zip)<=2_000_000:
        raise ValueError("Unexpected official county archive byte length")
    geom=parse_county_geometries(raw_zip)
    source_digest=sha256(raw_zip).hexdigest()
    release_id=f"{RELEASE_PREFIX}-{source_digest[:16]}"
    folder=root/ROOT_DIR/release_id
    folder.mkdir(parents=True,exist_ok=True)
    payload=json_bytes(geom)
    (folder/"counties.geojson").write_bytes(payload)
    (folder/"original.zip").write_bytes(raw_zip)
    manifest={
        "schemaVersion":"1.0.0",
        "releaseId":release_id,
        "status":"published",
        "publisher":"U.S. Census Bureau",
        "createdAt":datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z"),
        "source":{"url":SOURCE_URL,"sha256":source_digest,"bytes":len(raw_zip),
                  "path":"original.zip"},
        "geometry":{"path":"counties.geojson","sha256":sha256(payload).hexdigest(),
                    "bytes":len(payload),"features":EXPECTED,
                    "level":"county","vintage":VINTAGE,"joinKey":"GEOID",
                    "contentType":"application/geo+json"},
        "method":"Direct source-preserving transformation of Census Bureau 2023 cartographic 1:20 million county polygons to a GEOID-keyed generalized FeatureCollection, filtered to all 3,143 counties and equivalents in the 50 states and District of Columbia.",
        "limitations":"Generalized mapping geometry, not parcel, title, legal or cadastral evidence. Census 2023 boundary vintage does not automatically match all statistical program vintages; reconcile GEOID coverage before using an indicator.",
    }
    (folder/"manifest.json").write_bytes(json_bytes(manifest))
    index_file=root/INDEX_PATH
    if index_file.is_file():
        index=json.loads(index_file.read_text(encoding="utf-8"))
        if index.get("schemaVersion")!="1.0.0" or not isinstance(index.get("releases"),list):
            raise ValueError("Invalid existing geography index")
    else:
        index={"schemaVersion":"1.0.0","publicationStatus":"published",
               "publisher":"American Republic Futures Institute","releases":[]}
    entry={"releaseId":release_id,"geography":"county","vintage":VINTAGE,
           "features":EXPECTED,"status":"published",
           "manifestPath":f"{ROOT_DIR.as_posix()}/{release_id}/manifest.json",
           "geometryPath":f"{ROOT_DIR.as_posix()}/{release_id}/counties.geojson"}
    old=[r for r in index["releases"] if r["releaseId"]!=release_id]
    old.append(entry)
    index["releases"]=sorted(old,key=lambda r:r["releaseId"])
    index_file.parent.mkdir(parents=True,exist_ok=True)
    index_file.write_bytes(json_bytes(index))
    return {"releaseId":release_id,"features":EXPECTED,"sourceSha256":source_digest,
            "assetSha256":manifest["geometry"]["sha256"]}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-file",type=Path)
    ap.add_argument("--out-root",type=Path,default=ROOT)
    args=ap.parse_args()
    raw=(args.source_file.read_bytes() if args.source_file is not None
         else download_official(SOURCE_URL,host="www2.census.gov",limit=2_000_000))
    from tools.validate_geography import validate_geography
    with tempfile.TemporaryDirectory() as temp:
        working=Path(temp)
        prior=args.out_root/INDEX_PATH.parent
        if prior.is_dir():
            shutil.copytree(prior,working/INDEX_PATH.parent,dirs_exist_ok=True)
        result=stage(working,raw)
        validate_geography(working)
        src=working/ROOT_DIR/result["releaseId"]
        dst=args.out_root/ROOT_DIR/result["releaseId"]
        dst.parent.mkdir(parents=True,exist_ok=True)
        if dst.is_dir():
            shutil.rmtree(dst)
        shutil.copytree(src,dst)
        index=(working/INDEX_PATH).read_bytes()
        (args.out_root/INDEX_PATH).parent.mkdir(parents=True,exist_ok=True)
        (args.out_root/INDEX_PATH).write_bytes(index)
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
