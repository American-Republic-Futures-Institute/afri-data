"""Immutable source-replay validation for non-statistical Census geography releases."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from pipelines.census_county_geography import (
    SOURCE_URL,VINTAGE,EXPECTED,ROOT_DIR,INDEX_PATH,
    parse_county_geometries,
)
from tools.release_registry import valid_id


ROOT=Path(__file__).resolve().parents[1]


def checked_geography_file(root:Path,release_id:str,name:str)->Path:
    if not valid_id(release_id) or name not in ("manifest.json","counties.geojson","original.zip"):
        raise ValueError("Unsafe geography archive or manifest path")
    path=root/ROOT_DIR/release_id/name
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise ValueError("Invalid geography artifact path or symlink")
    return path


def validate_geography(root:Path=ROOT)->dict:
    index_file=root/INDEX_PATH
    if not index_file.exists():
        return {"geographyReleases":0,"countyFeatures":0}
    index=json.loads(index_file.read_text(encoding="utf-8"))
    if (index.get("schemaVersion")!="1.0.0"
            or index.get("publicationStatus")!="published"
            or not isinstance(index.get("releases"),list)
            or not 1<=len(index["releases"])<=30):
        raise ValueError("Invalid approved geography release index")
    seen=set()
    total=0
    for entry in index["releases"]:
        rid=entry.get("releaseId")
        if not valid_id(rid) or rid in seen:
            raise ValueError("Unsafe/duplicate geography release identity")
        seen.add(rid)
        if (entry.get("status")!="published" or entry.get("geography")!="county"
                or entry.get("vintage")!=VINTAGE or entry.get("features")!=EXPECTED
                or entry.get("manifestPath")!=f"{ROOT_DIR.as_posix()}/{rid}/manifest.json"
                or entry.get("geometryPath")!=f"{ROOT_DIR.as_posix()}/{rid}/counties.geojson"):
            raise ValueError("Unapproved or inconsistent geography entry")
        manifest_path=checked_geography_file(root,rid,"manifest.json")
        if not manifest_path.is_file():
            raise ValueError("Missing county geography manifest")
        manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
        if (manifest.get("releaseId")!=rid or manifest.get("status")!="published"
                or manifest.get("schemaVersion")!="1.0.0"
                or manifest.get("publisher")!="U.S. Census Bureau"):
            raise ValueError("Unapproved county geography manifest")
        source=manifest.get("source")
        geometry=manifest.get("geometry")
        if not isinstance(source,dict) or not isinstance(geometry,dict):
            raise ValueError("Incomplete geographic provenance contract")
        if (source.get("url")!=SOURCE_URL or source.get("path")!="original.zip"
                or geometry.get("path")!="counties.geojson"
                or geometry.get("level")!="county" or geometry.get("vintage")!=VINTAGE
                or geometry.get("features")!=EXPECTED or geometry.get("joinKey")!="GEOID"
                or geometry.get("contentType")!="application/geo+json"):
            raise ValueError("Unexpected Census county source/methodology contract")
        source_file=checked_geography_file(root,rid,"original.zip")
        asset_file=checked_geography_file(root,rid,"counties.geojson")
        if not source_file.is_file() or not asset_file.is_file():
            raise ValueError("Missing immutable county geometry artifact")
        original=source_file.read_bytes()
        asset=asset_file.read_bytes()
        if (len(original)!=source["bytes"] or sha256(original).hexdigest()!=source["sha256"]
                or len(asset)!=geometry["bytes"] or sha256(asset).hexdigest()!=geometry["sha256"]):
            raise ValueError("Census county geometry artifact fingerprint mismatch")
        if not 0<len(original)<=2_000_000 or not 0<len(asset)<=25_000_000:
            raise ValueError("Unbounded county geometry asset")
        expected=parse_county_geometries(original)
        actual=json.loads(asset.decode("utf-8"))
        if actual!=expected:
            raise ValueError("Census county cartographic geometry cannot be replayed from original source")
        if len(actual["features"])!=EXPECTED:
            raise ValueError("Incomplete 2023 Census county geography coverage")
        total+=EXPECTED
    return {"geographyReleases":len(seen),"countyFeatures":total}
