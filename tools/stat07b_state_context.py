"""STAT-07B deterministic, source-preserving state-context candidate builder.

Builds a third immutable *candidate* from two independently published sources.
This tool never writes publication/index.json or grants review approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from tools.stat07_curation import (
    CurationError, ROOT, canonical_bytes, validate_candidate, validate_recipe,
)

RECIPE = "catalog/curation/state-population-income-context-2025-2024.recipe.json"
CANDIDATE = "publication/candidates/state-population-income-context-2025-2024"
NO_AUTHORITY = {"status": "unreviewed-candidate",
                "publicPublicationAuthorized": False,
                "statisticalInferenceAuthorized": False,
                "causalInferenceAuthorized": False}


def build(root=ROOT):
    root = Path(root)
    recipe = json.loads((root / RECIPE).read_text("utf-8"))
    index = json.loads((root / "publication/index.json").read_text("utf-8"))
    snapshots = {}
    for source in recipe["inputs"]:
        release = source["releaseId"]
        folder = root / "publication/releases" / release
        manifest = json.loads((folder / "manifest.json").read_text("utf-8"))
        observations = (folder / "observations.json").read_bytes()
        # Historical source commit and manifest SHA are independently pinned in
        # the verified immutable source statistical profiles.
        profile_path = root / "catalog/statistics/source-profiles" / (release + ".json")
        profile = json.loads(profile_path.read_text("utf-8"))
        identity = profile["identity"]
        if (identity["releaseId"] != release or
                identity["sourceCommit"] != source["sourceCommit"] or
                identity["observationsSha256"] != source["observationsSha256"] or
                identity["manifestPath"] !=
                "publication/releases/" + release + "/manifest.json" or
                not identity.get("manifestGitBlobSha")):
            raise CurationError("Source identity not backed by immutable verified profile")
        snapshots[release] = (manifest, observations)
    admitted = validate_recipe(recipe, index, snapshots)
    if recipe["productId"] != "state-population-income-context-2025-2024":
        raise CurationError("Unexpected candidate product identity")
    psrc, asrc = recipe["inputs"]
    if (psrc["releaseId"] != "census-state-population-v2025" or
            psrc["selectionYear"] != 2025 or
            asrc["releaseId"] !=
            "census-acs5-state-income-2024-b25a176b0e6c339b" or
            asrc["selectionYear"] != 2024 or
            recipe["operation"]["joinType"] != "inner" or
            recipe["compatibility"]["temporalAlignment"] !=
            "separate-source-native-periods"):
        raise CurationError("The approved candidate recipe cannot change source semantics")
    population = json.loads(snapshots[psrc["releaseId"]][1])
    income = json.loads(snapshots[asrc["releaseId"]][1])
    p = {r["fips"]: r for r in population["observations"] if r["year"] == 2025}
    a = {r["geoid"]: r for r in income["observations"] if r["year"] == 2024}
    if len(p) != 52 or len(a) != 52 or set(p) != set(a):
        raise CurationError("Exact 52-geography FIPS parity required: no silent omissions")
    output = []
    for fips in sorted(p):
        left, right = p[fips], a[fips]
        if (left.get("name") != right.get("name") or
                left.get("unit") != "persons" or
                right.get("unit") != "USD" or
                left.get("statistic") != "published_estimate" or
                right.get("statistic") != "survey_estimate" or
                right.get("referencePeriod") != "2020-2024 five-year ACS" or
                right.get("sourceVariables") != ["B19013_E001", "B19013_M001"] or
                not isinstance(left.get("value"), int) or
                isinstance(left.get("value"), bool) or left["value"] <= 0):
            raise CurationError("Source geography, period or measurement contract mismatched")
        status = right.get("status")
        available = status == "available"
        if status not in ("available", "not_available") or (
            available and
            (type(right.get("value")) is not int or right["value"] <= 0 or
             type(right.get("marginOfError")) is not int or right["marginOfError"] < 0)
        ) or (not available and
               (right.get("value") is not None or right.get("marginOfError") is not None)):
            raise CurationError("Published income status and paired 90-percent MOE invalid")
        output.append({
            "fips": fips, "name": left["name"],
            "population": {
                "sourceReleaseId": psrc["releaseId"],
                "sourceCommit": psrc["sourceCommit"],
                "sourceObservationsSha256": psrc["observationsSha256"],
                "sourceRow": left, "sourceYear": 2025,
                "referencePeriod": "July 1, 2025",
                "measurement": "resident-population-estimate",
            },
            "income": {
                "sourceReleaseId": asrc["releaseId"],
                "sourceCommit": asrc["sourceCommit"],
                "sourceObservationsSha256": asrc["observationsSha256"],
                "sourceRow": right, "sourceYear": 2024,
                "referencePeriod": "2020-2024 five-year ACS",
                "sourceMarginOfErrorConfidence": 0.90,
                "inflationAdjustmentYear": 2024,
                "measurement": "median-household-income",
            },
        })
    observations = {
        "schemaVersion": "1.0.0",
        "type": "ARFI-CuratedSourceContextCandidate",
        "productId": recipe["productId"],
        "geography": "state", "joinKey": "fips",
        "rowCount": len(output),
        "temporalCompatibility": "separate-source-native-periods",
        "rows": output,
        "publicationAuthorized": False,
    }
    raw = canonical_bytes(observations)
    product = {
        "schemaVersion": "1.0.0", "type": "ARFI-DerivedDataProduct",
        "productId": recipe["productId"],
        "recipeSha256": admitted["recipeSha256"],
        "inputIdentities": [
            {key: item[key] for key in
             ("releaseId", "sourceCommit", "observationsSha256")}
            for item in recipe["inputs"]
        ],
        "output": {
            "observationsSha256": hashlib.sha256(raw).hexdigest(),
            "rowCount": 52, "geographyKey": "fips",
            "lineageColumns": ["population", "income"],
        },
        "quality": {
            "unmatchedInputGeographies": [],
            "missingSourceValues": sum(r["income"]["sourceRow"]["status"] != "available"
                                       for r in output),
            "duplicateKeys": 0, "omissionLedger": [],
        },
        "authority": dict(NO_AUTHORITY),
    }
    validate_candidate(recipe, product)
    return observations, product


def validate_committed(root=ROOT):
    root = Path(root)
    observations, product = build(root)
    path = root / CANDIDATE
    if (path / "observations.json").read_bytes() != canonical_bytes(observations):
        raise CurationError("Committed candidate rows differ from deterministic replay")
    if (path / "manifest.json").read_bytes() != canonical_bytes(product):
        raise CurationError("Committed candidate manifest differs from deterministic replay")
    return product


def main(argv=None):
    parser = argparse.ArgumentParser(description="STAT-07B immutable candidate replay")
    parser.add_argument("--check", action="store_true", help="Verify committed candidate only")
    args = parser.parse_args(argv)
    if args.check:
        candidate = validate_committed()
    else:
        obs, candidate = build()
        directory = ROOT / CANDIDATE
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "observations.json").write_bytes(canonical_bytes(obs))
        (directory / "manifest.json").write_bytes(canonical_bytes(candidate))
    print(json.dumps({"productId": candidate["productId"],
                      "observationsSha256": candidate["output"]["observationsSha256"],
                      "rows": candidate["output"]["rowCount"],
                      "publicPublicationAuthorized": False}, sort_keys=True))


if __name__ == "__main__":
    main()
