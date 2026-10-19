"""STAT-02A.2: source-bound, INTERNAL-ONLY Census distribution pilot.

Uses published, immutable Census values and existing StatKit primitives.
Does not create a published statistical release or grant methodology approval.
The synthetic STAT-02A artifact contract is intentionally not reused.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path

import numpy as np

from arfi_stats import METHODS, VERSION, boxplot, ecdf, histogram
from arfi_stats.artifacts import (
    ROOT, file_hash, hash_json, read_json_file, schema_check, write_output,
)
from arfi_stats.eligibility import evaluate
from tools.stat_profile_validate import (
    PROFILES_DIR, check_schema, load, verify_profile,
)

KIND = "ARFI-StatSourcePilot/1.0.0"
RELEASE = "census-state-population-v2025"
YEAR = 2025
SCOPE = "internal-source-bound-preview-not-publication-approved"
CHART_TYPES = ("histogram", "ecdf", "boxplot")
PROFILE_PATH = ROOT / PROFILES_DIR / (RELEASE + ".json")
RUNNER = Path(__file__).resolve()
NO_AUTHORITY = {
    "publicationAuthorized": False,
    "crossSourceAuthorized": False,
    "statisticalInferenceAuthorized": False,
    "causalInferenceAuthorized": False,
}


class CensusPilotError(ValueError):
    """Source-bound analytical pilot refused a request or replay."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CensusPilotError("STAT-02A.2 rejected: " + message)


def _source():
    """Admit the actual, immutable source; never accept a caller-supplied file."""
    profile = verify_profile(load(PROFILE_PATH), root=ROOT, historical=True)
    identity = profile["identity"]
    measurement = profile["measurement"]
    coverage = profile["coverage"]
    require(identity["releaseId"] == RELEASE and
            identity["indicatorId"] == "state-resident-population" and
            identity["sourceCommit"] and
            profile["reviewStatus"] == "not_independently_certified",
            "incorrect Census profile identity or review state")
    require(measurement["family"] == "population-stock" and
            measurement["unit"] == "persons" and
            measurement["valueField"] == "value" and
            measurement["geographyField"] == "fips" and
            measurement["yearField"] == "year" and
            coverage["geography"] == "state" and
            coverage["firstYear"] == 2020 and coverage["lastYear"] == YEAR and
            coverage["sourceRows"] == 312 and
            coverage["availableRows"] == 312 and
            coverage["explicitUnavailableRows"] == 0,
            "unexpected release measurement, years or coverage")
    path = ROOT / "publication" / "releases" / RELEASE / "observations.json"
    original = path.read_bytes()
    require(hashlib.sha256(original).hexdigest() ==
            identity["observationsSha256"],
            "immutable original observation bytes no longer match profile")
    document = json.loads(original)
    require(document["datasetId"] == identity["datasetId"] and
            document["indicatorId"] == identity["indicatorId"],
            "source document identity does not match the approved profile")
    chosen = [row for row in document["observations"] if row["year"] == YEAR]
    require(len(chosen) == 52 and
            len({row["fips"] for row in chosen}) == 52,
            "exactly 52 unique 2025 jurisdiction estimates are required")
    require(all(type(row["value"]) is int and 0 < row["value"] < 2**53 and
                row["unit"] == "persons" and
                row["statistic"] == "published_estimate" and
                type(row["fips"]) is str and len(row["fips"]) == 2 and
                row["fips"].isdigit()
                for row in chosen),
            "non-native, nonfinite or malformed state estimate")
    normalized = [
        {"fips": row["fips"], "year": row["year"], "value": row["value"],
         "availability": "available"}
        for row in sorted(chosen, key=lambda item: item["fips"])
    ]
    return profile, normalized


def _eligibility_request(profile: dict, chart_type: str) -> dict:
    identity = profile["identity"]
    return {
        "schemaVersion": "1.0.0",
        "releaseId": RELEASE,
        "methodId": METHODS[chart_type],
        "sourceCommit": identity["sourceCommit"],
        "observationsSha256": identity["observationsSha256"],
        "intent": "descriptive-preview",
        "x": "value",
        "y": None,
        "segment": None,
        "unitOfAnalysis": "geographic-units",
        "periodYears": [YEAR],
        "otherReleaseIds": [],
        "operations": {
            "impute": False, "sampleWeight": False, "perCapita": False,
            "shrinkage": False, "newInterval": False, "deriveRate": False,
            "excludeSourceBuckets": False, "requireUniformPeriods": False,
        },
        "acknowledgedQualifiers": list(profile["coverage"]["qualifierCodes"]),
    }


def produce(chart_type: str) -> dict:
    """Calculate one internal preview using pinned source and eligible method."""
    require(type(chart_type) is str and chart_type in CHART_TYPES,
            "method is outside the bounded Census pilot")
    profile, rows = _source()
    request = _eligibility_request(profile, chart_type)
    decision = evaluate(request)
    check_schema(decision, "contracts/statistical-eligibility-decision.schema.json")
    require(decision["decision"] == "qualified" and
            decision["methodApplicable"] is True and
            decision["sourceIdentityVerified"] is True and
            decision["reviewStatus"] == "not_independently_certified" and
            all(decision[key] is False for key in NO_AUTHORITY) and
            "UNWEIGHTED_JURISDICTIONS_NOT_RESIDENTS" in decision["reasonCodes"],
            "STAT-01 did not qualify the exact source/method/period request")
    options = {"x": "value", "availability": "availability", "unit": "persons"}
    if chart_type == "histogram":
        chart = histogram(rows, bins="fd", scale="count", **options)
    elif chart_type == "ecdf":
        chart = ecdf(rows, **options)
    else:
        chart = boxplot(rows, **options)
    schema_check(chart, "stat-chart-preview.schema.json")
    selected = chart["selection"]
    require(selected["inputRows"] == 52 and selected["selectedRows"] == 52 and
            selected["missingness"]["available"] == 52 and
            sum(selected["missingness"].values()) == 52 and
            len(chart["series"]) == 1 and chart["series"][0]["n"] == 52 and
            chart["algorithm"]["methodId"] == METHODS[chart_type] and
            all(chart["authority"][key] is False for key in
                ("publicationAuthorized", "sourceVerified",
                 "statisticalInferenceAuthorized", "crossSourceAuthorized",
                 "causalInferenceAuthorized")),
            "statistical preview changed count, method or no-authority boundary")
    identity = profile["identity"]
    artifact = {
        "schemaVersion": "1.0.0",
        "kind": KIND,
        "status": SCOPE,
        "sourceIdentity": {
            "releaseId": RELEASE,
            "indicatorId": identity["indicatorId"],
            "sourceCommit": identity["sourceCommit"],
            "manifestGitBlobSha": identity["manifestGitBlobSha"],
            "observationsSha256": identity["observationsSha256"],
            "sourceRows": profile["coverage"]["sourceRows"],
            "selectedYear": YEAR,
            "selectedJurisdictions": len(rows),
            "selectedInputSha256": hash_json(rows),
            "sourceProfileSha256": file_hash(PROFILE_PATH),
        },
        "analysisRequest": request,
        "eligibility": decision,
        "computation": {
            "chartType": chart_type,
            "methodId": METHODS[chart_type],
            "methodVersion": "1.0.0",
            "statkitVersion": VERSION,
            "pythonVersion": platform.python_version(),
            "numpyVersion": np.__version__,
            "coreSha256": file_hash(ROOT / "arfi_stats/core.py"),
            "eligibilitySha256": file_hash(ROOT / "arfi_stats/eligibility.py"),
            "validatorSha256": file_hash(ROOT / "tools/stat_profile_validate.py"),
            "runnerSha256": file_hash(RUNNER),
            "requirementsSha256": file_hash(ROOT / "requirements.txt"),
            "methodRegistrySha256": file_hash(
                ROOT / "contracts/stat-method-registry.json"),
            "methodApplicabilitySha256": file_hash(
                ROOT / "catalog/statistics/method-applicability.json"),
            "chartSha256": hash_json(chart),
        },
        "chart": chart,
        "quality": {
            "unitOfAnalysis": "state-equivalent-jurisdiction",
            "targetPopulation": profile["measurement"]["targetPopulation"],
            "denominator": "52 state-equivalent estimates, not individual residents",
            "publisherUncertaintyAvailable": False,
            "sourcePeriod": "July 1, 2025",
            "sourceCaveats": list(profile["caveats"]),
            "limitations": [
                "Every observation is a Census published demographic estimate, not an exact enumeration.",
                "The distribution gives each jurisdiction one observation regardless of the resident population.",
                "Neither individual-resident population inference nor policy performance rankings are supported.",
                "Statistical method eligibility and exact replay do not establish independent methodological approval.",
            ],
        },
        "authority": {
            **NO_AUTHORITY,
            "sourceIdentityVerified": True,
            "independentReviewStatus": "not_independently_certified",
        },
    }
    artifact["artifactSha256"] = hash_json(artifact)
    schema_check(artifact, "stat-source-pilot-artifact.schema.json")
    return artifact


def replay(artifact: dict) -> dict:
    """Verify both exact artifact contents and live source-bound recomputation."""
    schema_check(artifact, "stat-source-pilot-artifact.schema.json")
    require(artifact["kind"] == KIND and artifact["status"] == SCOPE,
            "not a supported, internal-only Census pilot artifact")
    require(artifact["artifactSha256"] == hash_json({
        key: value for key, value in artifact.items()
        if key != "artifactSha256"
    }), "artifact content checksum changed")
    kind = artifact["computation"]["chartType"]
    require(kind in CHART_TYPES, "unapproved method in recorded artifact")
    expected = produce(kind)
    require(artifact == expected,
            "source evidence, method, context, numeric output or runtime changed")
    return {
        "replay": "deterministic-match",
        "artifactSha256": artifact["artifactSha256"],
        "sourceIdentityVerified": True,
        "publicationAuthorized": False,
        "independentReviewStatus": "not_independently_certified",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only 2025 Census jurisdiction distribution pilot")
    parser.add_argument("command", choices=("produce", "replay"))
    parser.add_argument("--kind", choices=CHART_TYPES)
    parser.add_argument("--artifact", help="Existing internal-only pilot artifact")
    parser.add_argument("--output", default="-",
                        help="Exclusive new file outside repository, or '-'")
    args = parser.parse_args(argv)
    if args.command == "produce":
        if args.kind is None or args.artifact is not None:
            parser.error("produce requires --kind and refuses --artifact")
        result = produce(args.kind)
    else:
        if args.kind is not None or args.artifact is None:
            parser.error("replay requires --artifact, without --kind")
        result = replay(read_json_file(args.artifact))
    if args.output != "-":
        dest = Path(args.output).resolve()
        require(dest != ROOT and ROOT not in dest.parents,
                "internal pilot artifacts may not be written into this repository")
    write_output(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
