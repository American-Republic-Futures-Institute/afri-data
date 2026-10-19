"""STAT-02B: governed derived-analysis admission, never self-attesting.

This boundary consumes a source-bound internal preview plus independent
methodology evidence. Until D-11B institutional protection and human review
are operational, the validator fails closed. No source/preview JSON field can
grant public publication authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from arfi_stats.artifacts import ROOT, hash_json
from arfi_stats.census_pilot import produce as reproduce_census
from tools.review_governance import (
    read, validate_ledger, verify_github_approval,
)
from tools.reviewer_policy import validate_reviewer_policy

CONTRACT = "ARFI-GovernedAnalysisCandidate/1.0.0"
RESULT = "ARFI-AnalysisPublicationDecision/1.0.0"
SCHEMA = ROOT / "contracts/stat-governed-analysis-candidate.schema.json"
REASONS = {
    "SCHEMA_REJECTED", "NOT_SOURCE_BOUND", "SOURCE_REPLAY_FAILED",
    "SOURCE_REVIEW_REQUIRED", "INDEPENDENT_METHOD_APPROVAL_REQUIRED",
    "METHOD_SCOPE_MISMATCH", "PROTECTION_OR_REVIEW_UNVERIFIED",
    "REVOCATION_OR_SUPERSESSION", "PUBLICATION_NOT_AUTHORIZED",
}
REVIEW_FIELDS = ("rightsLicense", "methodology", "temporalInterpretation",
                 "geographicUniverse", "permittedPublicUses", "cautions")


class AnalysisPublicationError(ValueError):
    """Untrusted candidate cannot be promoted to a public artifact."""


def reject(reason):
    raise AnalysisPublicationError("STAT-02B rejected: " + reason)


def strict_json(path):
    file = Path(path)
    if not file.is_file() or file.stat().st_size > 8 * 1024 * 1024:
        reject("bounded JSON file required")
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                reject("duplicate JSON key: " + key)
            value[key] = item
        return value
    def finite(token):
        reject("non-finite JSON number " + token)
    try:
        return json.loads(file.read_text("utf-8"),
                          object_pairs_hook=unique, parse_constant=finite)
    except (UnicodeError, json.JSONDecodeError, OSError) as exc:
        raise AnalysisPublicationError("STAT-02B malformed JSON") from exc


def check_schema(value):
    schema = read(SCHEMA)
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema).iter_errors(value))
    if errors:
        reject("candidate contract invalid: " + errors[0].message)


def check_replay(candidate):
    """Recompute real Census pilot: digest agreement alone is insufficient."""
    source = candidate["sourcePilot"]
    method = source.get("computation", {}).get("chartType")
    if method not in ("histogram", "ecdf", "boxplot"):
        reject("unsupported source-bound pilot method")
    expected = reproduce_census(method)
    if expected != source:
        reject("candidate differs from the exact source-bound replay")
    if candidate["pilotSha256"] != hash_json(source):
        reject("source-bound pilot digest differs")
    if candidate["sourceIdentity"] != source["sourceIdentity"]:
        reject("source identity differs from source-bound pilot")
    if candidate["methodIdentity"]["methodId"] != source["computation"]["methodId"]:
        reject("method identity differs from replay")
    if candidate["methodIdentity"]["methodVersion"] != "1.0.0":
        reject("method version differs from replay")
    if candidate["methodIdentity"]["chartSha256"] != source["computation"]["chartSha256"]:
        reject("chart digest differs from source-bound preview")


def decision(candidate, *, reason, source_verified=False):
    # Never return an approval merely from a valid schema or self-declared
    # reviewer. Public output must go through a separate future signer.
    request_hash = hash_json(candidate)
    return {
        "schemaVersion": "1.0.0",
        "type": RESULT,
        "candidateSha256": request_hash,
        "decision": "denied",
        "reasonCodes": [reason],
        "sourceReplayVerified": source_verified,
        "independentMethodReviewVerified": False,
        "independentSourceReviewVerified": False,
        "publicationAuthorized": False,
        "crossSourceAuthorized": False,
        "statisticalInferenceAuthorized": False,
        "causalInferenceAuthorized": False,
        "publishableArtifact": None,
    }


def evaluate(candidate, *, root=ROOT):
    """Evidence-authenticated admission, never an author-signed approval.

    This v1 contract intentionally has a null methodApproval. Since there is
    no real D-11B-approved method event, the only legal output is a denial.
    Invalid or tampered previews are denied *before* the governance check.
    """
    try:
        check_schema(candidate)
    except (AnalysisPublicationError, KeyError, ValueError, TypeError):
        return decision(candidate, reason="SCHEMA_REJECTED")
    try:
        check_replay(candidate)
    except (AnalysisPublicationError, KeyError, ValueError, TypeError, OSError):
        return decision(candidate, reason="SOURCE_REPLAY_FAILED")

    # Source approval, even when achieved, is not approval to use a
    # statistical estimator. Never bootstrap authorization from a publisher
    # source decision or from the internal preview eligibility result.
    policy = read(Path(root) / "governance/reviewer-policy.json")
    try:
        roster = validate_reviewer_policy(policy)
    except (ValueError, OSError, KeyError):
        return decision(candidate, reason="PROTECTION_OR_REVIEW_UNVERIFIED",
                        source_verified=True)
    if (policy.get("status") != "configured" or not policy.get("approvedReviewers")
            or candidate["methodApproval"] is None):
        return decision(candidate, reason="INDEPENDENT_METHOD_APPROVAL_REQUIRED",
                        source_verified=True)
    # Future versions must carry a reviewed method packet with exact source,
    # procedure, scope and signed approval.  This version *never* upgrades a
    # caller-provided object into an approval.
    return decision(candidate, reason="PUBLICATION_NOT_AUTHORIZED",
                    source_verified=True)


def candidate_from_pilot(chart_type):
    """Build a source-verified INTERNAL candidate, without method authority."""
    pilot = reproduce_census(chart_type)
    return {
        "schemaVersion": "1.0.0",
        "type": CONTRACT,
        "status": "candidate-unapproved",
        "sourceIdentity": pilot["sourceIdentity"],
        "sourcePilot": pilot,
        "pilotSha256": hash_json(pilot),
        "methodIdentity": {
            "methodId": pilot["computation"]["methodId"],
            "methodVersion": pilot["computation"]["methodVersion"],
            "chartSha256": pilot["computation"]["chartSha256"],
        },
        "methodApproval": None,
        "interpretation": {
            "unitOfAnalysis": "state-equivalent-jurisdiction",
            "claimClass": "descriptive-only",
            "limitations": list(pilot["quality"]["limitations"]),
        },
        "publicationAuthorized": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fail-closed analysis governance gate")
    parser.add_argument("command", choices=("candidate", "verify"))
    parser.add_argument("--kind", choices=("histogram", "ecdf", "boxplot"))
    parser.add_argument("--input")
    args = parser.parse_args(argv)
    if args.command == "candidate":
        if not args.kind or args.input:
            parser.error("candidate requires --kind and no --input")
        result = candidate_from_pilot(args.kind)
    else:
        if args.kind or not args.input:
            parser.error("verify requires --input and no --kind")
        result = evaluate(strict_json(args.input))
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True,
                     allow_nan=False))
    return 2 if args.command == "verify" and result["decision"] == "denied" else 0


if __name__ == "__main__":
    raise SystemExit(main())
