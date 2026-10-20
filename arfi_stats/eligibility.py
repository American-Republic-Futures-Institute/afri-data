"""STAT-01 deterministic statistical method eligibility, never publication approval.

Validates pinned local evidence and method profiles. Computes no statistical
estimates, fetches no URLs, and has no human review signing capability.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
from jsonschema import Draft202012Validator
from tools.stat_profile_validate import (
    ROOT, PROFILES_DIR, REGISTRY, StatisticalProfileError, check_schema,
    load, verify_profile, verify_all_profiles
)

VERSION = "1.0.0"
NO_AUTHORITY = {"publicationAuthorized": False, "crossSourceAuthorized": False,
                "statisticalInferenceAuthorized": False,
                "causalInferenceAuthorized": False}
IDENTIFIER = re.compile(r"^[a-z0-9-]{6,120}$")


def fingerprint(request):
    try:
        body = json.dumps(request, ensure_ascii=True, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        body = "INVALID-NON-JSON-REQUEST"
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def evaluate(request, *, root=ROOT, historical=True):
    """permitted and qualified mean preview applicability, never approval."""
    root = Path(root)
    release = request.get("releaseId") if type(request) is dict else None
    method = request.get("methodId") if type(request) is dict else None
    out_release = release if isinstance(release, str) and len(release) < 120 else "unknown"
    out_method = method if isinstance(method, str) and len(method) < 120 else "unknown"
    denials, qualifications = [], []
    verified = False
    profile, rule = None, None

    def deny(code):
        if code not in denials:
            denials.append(code)

    def qualify(code):
        if code not in qualifications:
            qualifications.append(code)

    try:
        schema = load(ROOT / "contracts/statistical-eligibility-request.schema.json")
        if not isinstance(request, dict) or not Draft202012Validator(
                schema).is_valid(request):
            deny("INVALID_REQUEST")
    except (TypeError, ValueError, OSError):
        deny("INVALID_REQUEST")

    if not denials:
        if not IDENTIFIER.fullmatch(release):
            deny("RELEASE_NOT_REGISTERED")
        else:
            location = root / PROFILES_DIR / (release + ".json")
            if not location.is_file():
                deny("RELEASE_NOT_REGISTERED")
            else:
                try:
                    loaded = load(location)
                    if loaded.get("identity", {}).get("releaseId") != release:
                        raise StatisticalProfileError("Profile release identity does not match filename")
                    profile = verify_profile(loaded, root=root,
                                             historical=historical)
                    verified = True
                except (StatisticalProfileError, ValueError, KeyError,
                        OSError, json.JSONDecodeError):
                    deny("SOURCE_IDENTITY_NOT_VERIFIED")
        try:
            registry = load(root / REGISTRY)
            check_schema(registry,
                         "contracts/statistical-method-applicability.schema.json")
            prior = load(root / "contracts/stat-method-registry.json")
            known = {item["methodId"]: item["kind"] for item in prior["methods"]}
            rules = {item["methodId"]: item for item in registry["methods"]}
            if (len(rules) != len(registry["methods"]) or
                    len(rules) != len(known) or
                    registry["publicationAuthorized"] or prior["publicationAuthorized"] or
                    any(item["chartType"] != known.get(item["methodId"]) or
                        item["reviewStatus"] != "not_independently_certified" or
                        item["publicationAuthorized"] for item in registry["methods"])):
                deny("METHOD_REGISTRY_UNVERIFIED")
            elif method not in rules:
                deny("METHOD_NOT_REGISTERED")
            else:
                rule = rules[method]
        except (StatisticalProfileError, ValueError, TypeError, KeyError,
                OSError, json.JSONDecodeError):
            deny("METHOD_REGISTRY_UNVERIFIED")

    if verified and profile is not None and rule is not None and not denials:
        identity, measure, coverage = (
            profile["identity"], profile["measurement"], profile["coverage"])
        if (request["sourceCommit"] != identity["sourceCommit"] or
                request["observationsSha256"] != identity["observationsSha256"]):
            deny("IMMUTABLE_SOURCE_IDENTITY_MISMATCH")
            verified = False
        if request["otherReleaseIds"] or request["intent"] == "cross-source":
            deny("CROSS_RELEASE_OPERATION_DENIED")
        if request["intent"] == "public-derived-statistic":
            deny("METHODOLOGY_PUBLICATION_NOT_AUTHORIZED")
        if request["intent"] == "statistical-inference":
            deny("STATISTICAL_INFERENCE_NOT_AUTHORIZED")
        if request["intent"] == "causal":
            deny("CAUSAL_INFERENCE_NOT_AUTHORIZED")
        if request["unitOfAnalysis"] != "geographic-units":
            deny("ECOLOGICAL_SCOPE_NOT_SUPPORTED")
        ops = request["operations"]
        for key in ("impute", "sampleWeight", "perCapita", "newInterval", "deriveRate"):
            if ops[key]:
                deny("UNREVIEWED_TRANSFORMATION_" + key.upper())
        if ops["shrinkage"]:
            deny("DOUBLE_MODEL_SHRINKAGE_DENIED" if measure["publisherModelled"]
                 else "SHRINKAGE_METHOD_NOT_APPROVED")
        if ops["excludeSourceBuckets"] and coverage["knownOmittedSourceBuckets"]:
            deny("PUBLISHER_EXCLUSION_LEDGER_MUST_REMAIN")
        if ops["requireUniformPeriods"] and not coverage["sourcePeriodUniform"]:
            deny("INCOMPATIBLE_REPORTING_PERIODS")
        if request["segment"] is not None and request["segment"] not in coverage["allowedSegments"]:
            deny("UNAPPROVED_SEGMENT_COLUMN")
        years = request["periodYears"]
        if any(y < coverage["firstYear"] or y > coverage["lastYear"] for y in years):
            deny("REFERENCE_PERIOD_NOT_IN_RELEASE")
        if len(years) > 1 and rule["requires"] != "multi-year-source-series":
            if request["segment"] != "year":
                deny("REPEATED_OBSERVATION_POOLING")
            else:
                qualify("REPEATED_JURISDICTIONS_NOT_INDEPENDENT")
        if measure["family"] not in rule["supportedFamilies"]:
            deny("METHOD_INCOMPATIBLE_WITH_MEASUREMENT")
        if (len(years) < rule["minimumPublishedYears"] or
                coverage["lastYear"] - coverage["firstYear"] + 1 <
                rule["minimumPublishedYears"]):
            deny("INSUFFICIENT_TEMPORAL_COVERAGE")
        req, x, y = rule["requires"], request["x"], request["y"]
        if req == "numeric-value":
            if x != measure["valueField"] or y is not None:
                deny("UNAPPROVED_NUMERIC_FIELD")
            if measure["scale"] == "monetary-flow":
                deny("EXACT_MONEY_FLOAT_DISTRIBUTION_NOT_APPROVED")
        elif req == "categorical-availability":
            if x != "availability" or y is not None:
                deny("ONLY_COVERAGE_STATUS_FREQUENCY_ALLOWED")
        elif req == "numeric-pairs":
            deny("SECOND_NUMERIC_FIELD_NOT_REGISTERED")
        elif req == "multi-year-source-series":
            if x != measure["yearField"] or y != measure["valueField"]:
                deny("UNAPPROVED_TEMPORAL_COLUMNS")
            if request["segment"] != measure["geographyField"]:
                deny("GEOGRAPHIC_SERIES_KEY_REQUIRED")
            if not coverage["sourcePeriodUniform"]:
                deny("UNSUPPORTED_OR_MIXED_SOURCE_TIME_SERIES")
        elif req == "publisher-interval":
            if (x != measure["geographyField"] or y != measure["valueField"] or
                    measure["intervalFields"] is None):
                deny("PUBLISHER_INTERVAL_NOT_AVAILABLE")
        else:
            deny("METHOD_INPUT_CONTRACT_UNRECOGNIZED")
        if not denials and req != "categorical-availability":
            qualify("SOURCE_NATIVE_VALUES_REQUIRE_CONTEXT")
            if measure["family"] == "survey-median":
                qualify("ACS_FIVE_YEAR_POOLED_NOT_ANNUAL")
                qualify("PUBLISHER_NINETY_PERCENT_MOE_NOT_NEW_INTERVAL")
                qualify("UNWEIGHTED_STATES_NOT_HOUSEHOLDS")
            if measure["publisherModelled"]:
                qualify("PUBLISHER_MODELED_NOT_DIRECT_OBSERVATIONS")
            if not coverage["sourcePeriodUniform"]:
                qualify("NONUNIFORM_SOURCE_REPORTING_PERIODS")
            if coverage["explicitUnavailableRows"]:
                qualify("PUBLISHED_MISSINGNESS_MUST_BE_SHOWN")
            if len(years) > 1:
                qualify("REPEATED_GEOGRAPHIC_ESTIMATES_NOT_INDEPENDENT")
            if not set(coverage["qualifierCodes"]).issubset(
                    request["acknowledgedQualifiers"]):
                qualify("PUBLISHER_QUALIFICATIONS_NOT_ACKNOWLEDGED")
        elif not denials and coverage["knownOmittedSourceBuckets"]:
            qualify("GEOGRAPHIC_EXCLUSION_LEDGER_REQUIRED")
        elif not denials and coverage["explicitUnavailableRows"]:
            qualify("PUBLISHED_MISSINGNESS_MUST_BE_SHOWN")
        if not denials and measure["family"] == "population-stock" and (
                req != "categorical-availability"):
            qualify("UNWEIGHTED_JURISDICTIONS_NOT_RESIDENTS")
        if not denials and measure["family"] == "publisher-modeled-prevalence" and (
                req == "categorical-availability"):
            qualify("MODELED_SOURCE_COVERAGE_ONLY")

    status = "denied" if denials else "qualified" if qualifications else "permitted"
    return {"schemaVersion": VERSION,
            "type": "ARFI-StatisticalMethodEligibility/1.0.0",
            "releaseId": out_release, "methodId": out_method,
            "decision": status, "reasonCodes": denials + qualifications or
            ["SOURCE_NATIVE_PREVIEW_ONLY"],
            "methodApplicable": status != "denied",
            "sourceIdentityVerified": verified, **NO_AUTHORITY,
            "reviewStatus": "not_independently_certified",
            "requestFingerprint": fingerprint(request)}


def quality_report(release_id, *, root=ROOT, historical=True):
    root = Path(root)
    if not isinstance(release_id, str) or not IDENTIFIER.fullmatch(release_id):
        raise StatisticalProfileError("STAT-01: unknown statistical source identity")
    profile = verify_profile(load(root / PROFILES_DIR / (release_id + ".json")),
                             root=root, historical=historical)
    measure, coverage = profile["measurement"], profile["coverage"]
    return {"schemaVersion": VERSION,
            "type": "ARFI-StatisticalQualitySummary/1.0.0",
            "releaseId": release_id, "sourceCommit": profile["identity"]["sourceCommit"],
            "sourceIdentityVerified": True,
            "reviewStatus": "not_independently_certified",
            "publicationAuthorized": False,
            "targetPopulation": measure["targetPopulation"],
            "unitOfAnalysis": measure["observationUnit"],
            "measurementFamily": measure["family"],
            "samplingDesign": measure["samplingDesign"],
            "denominatorAvailability": measure["denominatorAvailability"],
            "publisherModelled": measure["publisherModelled"],
            "publisherIntervalAvailable": measure["intervalFields"] is not None,
            "publisherMarginOfError": measure.get("marginOfError"),
            "referencePeriodsUniform": coverage["sourcePeriodUniform"],
            "sourceRows": coverage["sourceRows"],
            "availableRows": coverage["availableRows"],
            "explicitUnavailableRows": coverage["explicitUnavailableRows"],
            "knownOmittedSourceBuckets": coverage["knownOmittedSourceBuckets"],
            "qualifierCodes": list(coverage["qualifierCodes"]),
            "caveats": list(profile["caveats"])}


def main(argv=None):
    parser = argparse.ArgumentParser(description="STAT-01 statistical eligibility")
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--request", help="JSON request file; no approval possible")
    choice.add_argument("--verify-profiles", action="store_true")
    choice.add_argument("--quality-report", help="Existing release ID")
    options = parser.parse_args(argv)
    if options.verify_profiles:
        value = verify_all_profiles()
    elif options.quality_report:
        value = quality_report(options.quality_report)
    else:
        value = evaluate(json.loads(Path(options.request).read_text("utf-8")))
        check_schema(value, "contracts/statistical-eligibility-decision.schema.json")
    print(json.dumps(value, indent=2, sort_keys=True))
    return 2 if value.get("decision") == "denied" else 0


if __name__ == "__main__":
    raise SystemExit(main())
