"""STAT-07A: source-preserving, deterministic cross-release candidate admission.

This module authorizes neither statistical derivation nor public publication.
A join recipe must first carry a compatible, immutable, lossless source contract.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


class CurationError(ValueError):
    pass


def canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def validate_schema(value, name):
    schema = json.loads((ROOT / "contracts" / name).read_text("utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(value),
                    key=lambda e: tuple(str(p) for p in e.path))
    if errors:
        raise CurationError("STAT-07A invalid " + name + ": " + errors[0].message)


def validate_recipe(recipe, source_index, release_manifests):
    """Verify declared inputs against published release identities and constraints.

    release_manifests keys are release IDs, values are pairs (manifest, immutable
    observations bytes). Historical git identity must be verified separately
    by the source-profile publication pipeline.
    """
    validate_schema(recipe, "data-product-recipe.schema.json")
    if source_index.get("publicationStatus") != "published":
        raise CurationError("Publisher release index is not published")
    entries = {e["releaseId"]: e for e in source_index.get("releases", [])
               if e.get("status") == "published"}
    if len(entries) != len([e for e in source_index.get("releases", [])
                           if e.get("status") == "published"]):
        raise CurationError("Duplicate publisher release identity")
    ids = [i["releaseId"] for i in recipe["inputs"]]
    if len(set(ids)) != len(ids):
        raise CurationError("Duplicate input release is not independent evidence")
    vintages = []
    geographies = set()
    for source in recipe["inputs"]:
        release = source["releaseId"]
        if release not in entries or release not in release_manifests:
            raise CurationError("Unpublished or unresolved input: " + release)
        manifest, observations = release_manifests[release]
        if manifest.get("releaseId") != release or manifest.get("status") != "published":
            raise CurationError("Input manifest identity mismatch")
        if entries[release].get("indicatorId") is None:
            raise CurationError("Input indicator identity missing")
        expected_hash = manifest.get("assets", {}).get("observations", {}).get("sha256")
        if (hashlib.sha256(observations).hexdigest() != expected_hash or
                expected_hash != source["observationsSha256"]):
            raise CurationError("Input immutable observation SHA-256 mismatch")
        doc = json.loads(observations)
        if (doc.get("indicatorId") != entries[release]["indicatorId"] or
                doc.get("joinKey") != source["geographyKey"]):
            raise CurationError("Input indicator or join key mismatch")
        if manifest.get("geography", {}).get("level") != recipe["compatibility"]["geographyLevel"]:
            raise CurationError("Incompatible geography levels")
        vintages.append(manifest["geography"]["vintage"])
        geographies.add(doc.get("geography"))
        for r in doc.get("observations", []):
            if (r.get("unit") != source["measurementUnit"] or
                    r.get("status", "available") not in ("available", "not_available")):
                raise CurationError("Source unit or missingness contract mismatch")
        keys = [r.get(source["geographyKey"]) for r in doc.get("observations", [])]
        if not all(isinstance(k, str) and k.isdigit() and
                   len(k) == (2 if doc["geography"] == "state" else 5) for k in keys):
            raise CurationError("Invalid source geography keys")
        if len(set(keys)) != len(keys):
            raise CurationError("Input is not one observation per geography")
    if vintages != recipe["compatibility"]["boundaryVintages"] or len(geographies) != 1:
        raise CurationError("Source geography vintages or levels mismatched")
    if recipe["compatibility"]["temporalAlignment"] == "matched-source-periods":
        if len({tuple((s["temporalInterpretation"],) for s in recipe["inputs"])}) != 1:
            raise CurationError("Source periods not independently verified as equivalent")
    return {"recipeSha256": hashlib.sha256(canonical_bytes(recipe)).hexdigest(),
            "inputReleaseIds": ids, "candidateOnly": True,
            "publicPublicationAuthorized": False,
            "statisticalDerivationAuthorized": False}


def validate_candidate(recipe, product):
    validate_schema(recipe, "data-product-recipe.schema.json")
    validate_schema(product, "derived-data-product.schema.json")
    expected = hashlib.sha256(canonical_bytes(recipe)).hexdigest()
    if expected != product["recipeSha256"] or recipe["productId"] != product["productId"]:
        raise CurationError("Candidate is not bound to the exact deterministic recipe")
    expected_sources = [(i["releaseId"], i["sourceCommit"], i["observationsSha256"])
                        for i in recipe["inputs"]]
    actual_sources = [(i["releaseId"], i["sourceCommit"], i["observationsSha256"])
                      for i in product["inputIdentities"]]
    if actual_sources != expected_sources or len(set(actual_sources)) != len(actual_sources):
        raise CurationError("Candidate provenance differs from pinned input sources")
    return {"candidateOnly": True, "publicPublicationAuthorized": False}
