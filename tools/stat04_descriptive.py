"""STAT-04: reproducible descriptive distributions from existing government releases.

Not scientific certification, not a new publisher value, and not an implicit
cross-source comparison. Every chart is materialized as immutable numeric JSON.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from arfi_stats import METHODS, histogram, ecdf, boxplot
from arfi_stats.eligibility import evaluate
from arfi_stats.artifacts import ROOT, canonical_bytes, hash_json, schema_check
from arfi_stats.census_pilot import produce as census_pilot, STATE_EQUIVALENT_FIPS
from tools.stat_profile_validate import verify_profile, load

PUB = ROOT / "publication" / "descriptive"
KINDS = ("histogram", "ecdf", "boxplot")
DATASETS = {
    "census": {
        "releaseId": "census-state-population-v2025",
        "idPrefix": "census-2025-state-population",
        "publisher": "U.S. Census Bureau",
        "sourceYear": 2025,
        "period": "July 1, 2025",
        "unit": "persons",
        "geography": "50 states, District of Columbia and Puerto Rico",
        "unitOfAnalysis": "state-equivalent-jurisdiction",
        "limits": [
            "These are Census population estimates, not an exact census count.",
            "One observation per jurisdiction: not a distribution of individual residents.",
            "Each state-equivalent jurisdiction has equal analytical weight, not population weight.",
            "This is descriptive ARFI analysis, not independently reviewed scientific inference.",
        ],
    },
    "bls": {
        "releaseId": "bls-laus-state-unemployment-2025-e1625280119b26c3",
        "idPrefix": "bls-2025-state-unemployment",
        "publisher": "U.S. Bureau of Labor Statistics",
        "sourceYear": 2025,
        "period": "2025 11-month annual estimate (October excluded)",
        "unit": "percent",
        "geography": "50 states and District of Columbia; Puerto Rico excluded",
        "unitOfAnalysis": "state-or-dc-jurisdiction",
        "limits": [
            "BLS 2025 11-month state/DC LAUS annual unemployment rates omit October.",
            "Puerto Rico has a different 12-month annual estimate and is excluded; it is not missing or zero.",
            "Published unemployment rates are estimated rates, not individual workers or observations.",
            "Jurisdictions are equally weighted; no population weighting or new rate calculation.",
            "This is descriptive ARFI analysis, not independently reviewed scientific inference.",
        ],
    },
    "cdc": {
        "releaseId": "cdc-places-county-obesity-2025-ec00ab31716eccca",
        "idPrefix": "cdc-2023-county-obesity",
        "publisher": "Centers for Disease Control and Prevention",
        "sourceYear": 2023,
        "period": "2023 BRFSS reference; CDC PLACES 2025 model vintage",
        "unit": "percent",
        "geography": "3,143 CDC county-source records (not 3,144 Census polygons)",
        "unitOfAnalysis": "county",
        "limits": [
            "CDC PLACES 2025 obesity values are modeled adult prevalence from 2023 BRFSS, not direct county survey measurements.",
            "Exactly 187 county estimates (Kentucky 120, Pennsylvania 67) are explicitly unavailable, not zero.",
            "The additional Loving County, Texas Census boundary has no CDC source row and is outside this chart universe.",
            "Each modeled county is one unweighted observation; published 95% intervals are not recomputed.",
            "This is descriptive ARFI analysis, not independently reviewed scientific inference.",
        ],
    },
}
IDS = tuple(
    DATASETS[d]["idPrefix"] + "-" + k
    for d in DATASETS for k in KINDS
)

def require(ok, reason):
    if not ok:
        raise ValueError("STAT-04 source replay mismatch: " + reason)

def file_for(dataset, kind):
    require(dataset in DATASETS and kind in KINDS, "unknown dataset or chart")
    return PUB / (DATASETS[dataset]["idPrefix"] + "-" + kind + ".json")

def _profile_source(dataset):
    spec = DATASETS[dataset]
    root_path = ROOT / "catalog" / "statistics" / "source-profiles" / (
        spec["releaseId"] + ".json"
    )
    profile = verify_profile(load(root_path), root=ROOT, historical=True)
    require(profile["identity"]["releaseId"] == spec["releaseId"] and
            profile["measurement"]["unit"] == spec["unit"] and
            profile["measurement"]["valueField"] == "value" and
            profile["reviewStatus"] == "not_independently_certified",
            "published statistical source identity/units changed")
    path = ROOT / "publication" / "releases" / spec["releaseId"]
    raw = (path / "observations.json").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    require(digest == profile["identity"]["observationsSha256"],
            "observations SHA differs from historical source profile")
    manifest_bytes = (path / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    require(manifest["releaseId"] == spec["releaseId"] and
            manifest["assets"]["observations"]["sha256"] == digest,
            "source manifest does not bind historical observations")
    observations = json.loads(raw)["observations"]
    return profile, observations, hashlib.sha256(manifest_bytes).hexdigest()

def _bls():
    spec = DATASETS["bls"]
    profile, observations, manifest_sha = _profile_source("bls")
    require(profile["coverage"]["sourceRows"] == 52 and
            profile["coverage"]["availableRows"] == 52 and
            len(observations) == 52 and
            len({row["geoid"] for row in observations}) == 52 and
            {row["geoid"] for row in observations} == STATE_EQUIVALENT_FIPS,
            "BLS must retain exactly the 52 published state-equivalents")
    qualified = []
    excluded = 0
    for row in observations:
        require(type(row["value"]) in (int, float) and
                0 <= row["value"] <= 100 and row["status"] == "available" and
                row["unit"] == "percent" and row["year"] == 2025 and
                row["seasonalAdjustment"] == "not_seasonally_adjusted" and
                row["statistic"] == "published_estimate",
                "invalid BLS reported annual unemployment estimate")
        if row["geoid"] == "72":
            require(row["annualAverageMonths"] == 12 and
                    row["excludedMonths"] == [] and
                    row["sourcePeriodQualifier"] == "full_12_months_2025",
                    "Puerto Rico must retain its noncomparable 12-month rate")
            excluded += 1
        else:
            require(row["annualAverageMonths"] == 11 and
                    row["excludedMonths"] == ["2025-10"] and
                    row["sourcePeriodQualifier"] == "no_october_cps_2025",
                    "BLS state/DC rates must be qualified 11-month 2025 values")
            qualified.append({
                "value": row["value"], "availability": "available",
            })
    require(len(qualified) == 51 and excluded == 1, "BLS qualification count")
    return profile, qualified, manifest_sha, 52, 1, 0

def _cdc():
    profile, observations, manifest_sha = _profile_source("cdc")
    require(profile["coverage"]["sourceRows"] == 3143 and
            profile["coverage"]["availableRows"] == 2956 and
            profile["coverage"]["explicitUnavailableRows"] == 187 and
            len(observations) == 3143 and
            len({r["geoid"] for r in observations}) == 3143,
            "CDC county availability changed")
    result, missing, state_missing = [], 0, {}
    for row in observations:
        require(type(row["geoid"]) is str and len(row["geoid"]) == 5 and
                row["geoid"].isdigit() and row["year"] == 2023 and
                row["publisherVintage"] == 2025 and row["unit"] == "percent" and
                row["statistic"] == "model_based_estimate",
                "CDC geography/reference-year/measurement changed")
        status = row["status"]
        require(status in ("available", "not_available"), "unknown CDC status")
        if status == "available":
            require(type(row["value"]) in (int, float) and
                    0 <= row["value"] <= 100 and
                    type(row["lower95"]) in (int, float) and
                    type(row["upper95"]) in (int, float) and
                    0 <= row["lower95"] <= row["value"] <= row["upper95"] <= 100,
                    "invalid modeled estimate or source-supplied interval")
        else:
            require(row["value"] is None and row["lower95"] is None and
                    row["upper95"] is None and row["confidenceInterval95"] is None,
                    "an unavailable CDC estimate must not become zero")
            missing += 1
            state_missing[row["stateAbbr"]] = state_missing.get(row["stateAbbr"], 0) + 1
        result.append({"value": row["value"], "availability": status})
    require(len(result) == 3143 and missing == 187 and
            state_missing == {"KY": 120, "PA": 67} and
            "48301" not in {r["geoid"] for r in observations},
            "CDC missingness ledger or geography-only Loving County changed")
    return profile, result, manifest_sha, 3143, 0, 187

def verify_method_applicability(profile, kind):
    """Technical source/method compatibility; not a human publication approval."""
    req = {
        "schemaVersion": "1.0.0",
        "releaseId": profile["identity"]["releaseId"],
        "methodId": METHODS[kind],
        "sourceCommit": profile["identity"]["sourceCommit"],
        "observationsSha256": profile["identity"]["observationsSha256"],
        "intent": "descriptive-preview",
        "x": "value", "y": None, "segment": None,
        "unitOfAnalysis": "geographic-units",
        "periodYears": [DATASETS[
            "bls" if profile["measurement"]["family"] == "published-rate" else "cdc"
        ]["sourceYear"]],
        "otherReleaseIds": [],
        "operations": {
            "impute": False, "sampleWeight": False, "perCapita": False,
            "shrinkage": False, "newInterval": False, "deriveRate": False,
            "excludeSourceBuckets": False, "requireUniformPeriods": False,
        },
        "acknowledgedQualifiers": list(profile["coverage"]["qualifierCodes"]),
    }
    decision = evaluate(req, historical=True)
    require(decision["decision"] in ("qualified", "permitted") and
            decision["methodApplicable"] is True and
            decision["sourceIdentityVerified"] is True and
            decision["reviewStatus"] == "not_independently_certified" and
            all(decision[x] is False for x in (
                "publicationAuthorized", "statisticalInferenceAuthorized",
                "causalInferenceAuthorized", "crossSourceAuthorized"
            )), "source/method is ineligible under existing applicability registry")
    return decision


def make(dataset, kind):
    require(dataset in DATASETS and kind in KINDS, "unsupported descriptive request")
    spec = DATASETS[dataset]
    if dataset == "census":
        pilot = census_pilot(kind)
        source = pilot["sourceIdentity"]
        rows = pilot["chart"]["selection"]["selectedRows"]
        chart = pilot["chart"]
        path = ROOT / "publication/releases" / spec["releaseId"] / "manifest.json"
        manifest_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        source_commit = source["sourceCommit"]
        observation_sha = source["observationsSha256"]
        source_rows, excluded, unavailable = source["sourceRows"], 0, 0
    else:
        profile, normalized, manifest_sha, source_rows, excluded, unavailable = (
            _bls() if dataset == "bls" else _cdc()
        )
        verify_method_applicability(profile, kind)
        source_commit = profile["identity"]["sourceCommit"]
        observation_sha = profile["identity"]["observationsSha256"]
        opts = dict(x="value", availability="availability", unit="percent")
        if kind == "histogram":
            chart = histogram(normalized, bins="fd", scale="count", **opts)
        elif kind == "ecdf":
            chart = ecdf(normalized, **opts)
        else:
            chart = boxplot(normalized, **opts)
        rows = len(normalized)
        schema_check(chart, "stat-chart-preview.schema.json")
    selected = rows - unavailable
    require(chart["selection"]["inputRows"] == rows and
            chart["selection"]["selectedRows"] == rows and
            chart["selection"]["missingness"]["available"] == selected and
            chart["selection"]["missingness"]["not_available"] == unavailable and
            sum(chart["selection"]["missingness"].values()) == rows and
            len(chart["series"]) == 1 and
            chart["series"][0]["n"] == selected and
            chart["algorithm"]["methodId"] == METHODS[kind] and
            all(chart["authority"][flag] is False for flag in (
                "publicationAuthorized", "sourceVerified",
                "crossSourceAuthorized", "statisticalInferenceAuthorized",
                "causalInferenceAuthorized")),
            "StatKit output has untrusted authority, wrong method or denominator")
    if kind == "histogram":
        require(sum(p["count"] for p in chart["series"][0]["points"]) == selected,
                "histogram frequencies not equal to available source rows")
    elif kind == "ecdf" and selected:
        points = chart["series"][0]["points"]
        require(points and points[-1]["cumulative"] == 1.0 and
                sum(p["countAtX"] for p in points) == selected,
                "ECDF must terminate at all source counts")
    elif kind == "boxplot":
        stat = chart["series"][0]["statistics"]
        require(stat is not None and
                stat["min"] <= stat["q1"] <= stat["median"] <=
                stat["q3"] <= stat["max"], "boxplot quantiles invalid")
    return {
        "schemaVersion": "1.1.0",
        "type": "ARFI-ReproducibleDescriptiveChart/1.0.0",
        "id": spec["idPrefix"] + "-" + kind,
        "publicationStatus": "published-reproducible-descriptive",
        "reviewStatus": "not-independently-reviewed",
        "dataset": spec["releaseId"],
        "publisher": spec["publisher"],
        "analysisProducer": "American Republic Futures Institute",
        "geography": spec["geography"],
        "sourceYear": spec["sourceYear"],
        "sourcePeriod": spec["period"],
        "sourceCommit": source_commit,
        "sourceManifestSha256": manifest_sha,
        "observationsSha256": observation_sha,
        "chartSha256": hash_json(chart),
        "unitOfAnalysis": spec["unitOfAnalysis"],
        "populationWeighted": False,
        "sourceRows": source_rows,
        "selectedRows": rows,
        "availableRows": selected,
        "unavailableRows": unavailable,
        "excludedRows": excluded,
        "method": METHODS[kind],
        "limitations": list(spec["limits"]),
        "chart": chart,
    }

def validate_artifact(dataset, kind, data):
    require(dataset in DATASETS and kind in KINDS,
            "unsupported descriptive dataset and chart combination")
    expected = make(dataset, kind)
    require(type(data) is dict and set(data) == set(expected) and
            data == expected, "data/method/numeric mismatch for " +
            DATASETS[dataset]["idPrefix"] + "-" + kind)
    require(hash_json(data["chart"]) == data["chartSha256"],
            "embedded chart digest differs from original replay")
    return expected


def verify():
    # Retain the prior histogram as an immutable STAT-03 release.
    from tools.verify_census_descriptive import verify as verify_old
    verify_old()
    found = []
    for dataset in DATASETS:
        for kind in KINDS:
            if dataset == "census" and kind == "histogram":
                continue
            path = file_for(dataset, kind)
            require(path.is_file(), "missing versioned chart " + str(path))
            data = json.loads(path.read_bytes())
            validate_artifact(dataset, kind, data)
            found.append(data["id"])
    return {"reproducible": len(found)+1, "new": found}

def fixture():
    for dataset in DATASETS:
        for kind in KINDS:
            if dataset == "census" and kind == "histogram":
                continue
            obj = make(dataset, kind)
            print("ARFI_STAT04_FIXTURE_" + obj["id"].replace("-", "_").upper() + "=" +
                  base64.b64encode(canonical_bytes(obj)).decode("ascii"))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("fixture", "verify"))
    args = parser.parse_args()
    if args.command == "fixture":
        fixture()
    else:
        print(json.dumps(verify(), indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
