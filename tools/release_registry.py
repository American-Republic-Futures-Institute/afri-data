"""Deterministic, review-gated index maintenance for ARFI evidence releases.

Publication manifests and assets are consumed at immutable Git commits. This
registry never authorizes an unreviewed government or third-party source.
"""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import re

ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ASSET = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")
INDEX_DEFAULTS = {
    "schemaVersion": "1.0.0",
    "publicationStatus": "published",
    "publisher": "American Republic Futures Institute",
    "sourceOfTruth": "https://github.com/American-Republic-Futures-Institute/afri-data",
}

def valid_id(value: object) -> bool:
    return isinstance(value, str) and len(value) <= 120 and bool(ID.fullmatch(value))

def valid_asset_name(value: object) -> bool:
    return (isinstance(value, str) and bool(ASSET.fullmatch(value))
            and ".." not in value and not value.endswith("."))

def exact_release_path(release_id: str, name: str) -> str:
    if not valid_id(release_id) or not valid_asset_name(name):
        raise ValueError("Unsafe release identifier or asset name")
    return f"publication/releases/{release_id}/{name}"

def checked_path(root: Path, release_id: str, name: str) -> Path:
    """Avoid lexical traversal and symlink escapes from the publication root."""
    relative = exact_release_path(release_id, name)
    target = root / PurePosixPath(relative)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("Release asset escapes publication root")
    return target

def upsert_release_entry(root: Path, entry: dict) -> dict:
    """Merge the approved release entry without removing unrelated releases."""
    release_id = entry.get("releaseId")
    if not valid_id(release_id):
        raise ValueError("Invalid release id")
    if (entry.get("manifestPath") != exact_release_path(release_id, "manifest.json")
            or entry.get("status") != "published"):
        raise ValueError("Release must reference its exact reviewed manifest")
    for field in ("observationsPath", "geometryPath"):
        if field in entry:
            path = entry[field]
            if not isinstance(path, str) or path != exact_release_path(release_id, path.rsplit("/", 1)[-1]):
                raise ValueError("Unsafe " + field)
    path = root / "publication/index.json"
    if path.exists():
        index = json.loads(path.read_text(encoding="utf-8"))
        if index.get("schemaVersion") != "1.0.0" or not isinstance(index.get("releases"), list):
            raise ValueError("Unrecognized publication index")
    else:
        index = {**INDEX_DEFAULTS, "releases": []}
    existing = index["releases"]
    if any(not valid_id(x.get("releaseId")) for x in existing):
        raise ValueError("Unsafe release in existing publication index")
    ids = [x["releaseId"] for x in existing]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate released evidence id")
    updated = [x for x in existing if x["releaseId"] != release_id]
    updated.append(entry)
    index["releases"] = sorted(updated, key=lambda x: x["releaseId"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return index
