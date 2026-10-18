"""STAT-02A: reproducible, caller-declared synthetic chart artifacts.

Always unsigned, preview-only, and separate from STAT-01 official-source
eligibility, human methodology review, and public analytical publication.
Only dispatches to existing ARFI-StatKit operations, without new statistics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import re
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
import numpy as np

from arfi_stats import (
    CONTRACT, METHODS, VERSION, histogram, ecdf, boxplot,
    frequency, scatter, time_series, intervals,
)

ROOT = Path(__file__).resolve().parents[1]
KIND = "ARFI-StatAnalysisArtifact/1.0.0"
REQUEST_KIND = "ARFI-StatSyntheticRequest/1.0.0"
MAX_ROWS = 10_000
MAX_JSON_BYTES = 16 * 1024 * 1024
STATES = ("available", "not_available", "no_record",
          "suppressed", "not_applicable", "unknown")
FIELD = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,79}$")
RUNNER = Path(__file__).resolve()
CORE = ROOT / "arfi_stats/core.py"
INIT = ROOT / "arfi_stats/__init__.py"
REGISTRY = ROOT / "contracts/stat-method-registry.json"
LOCK = ROOT / "requirements.txt"
SOURCE_UNVERIFIED = {
    "publicationAuthorized": False,
    "sourceVerified": False,
    "statisticalInferenceAuthorized": False,
    "crossSourceAuthorized": False,
    "causalInferenceAuthorized": False,
}


class StatArtifactError(ValueError):
    """An unsigned statistical preview cannot be executed or reproduced."""


def refuse(message: str) -> None:
    raise StatArtifactError("STAT-02A rejected: " + message)


def check(condition: Any, message: str) -> None:
    if not condition:
        refuse(message)


def canonical_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                             allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError) as exc:
        raise StatArtifactError("STAT-02A rejected: non-canonical JSON input") from exc
    check(len(encoded) <= MAX_JSON_BYTES, "canonical JSON exceeds bounded preview size")
    return encoded


def hash_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_hash(file: Path) -> str:
    return hashlib.sha256(file.read_bytes()).hexdigest()


def schema_check(document: Any, name: str) -> None:
    schema = json.loads((ROOT / "contracts" / name).read_text("utf-8"))
    Draft202012Validator.check_schema(schema)
    # Resolve only exact repository-controlled contract IDs. Never fetch schema
    # references across the network or trust caller-provided definitions.
    linked = []
    for source in ("stat-analysis-request.schema.json", "stat-chart-preview.schema.json"):
        doc = json.loads((ROOT / "contracts" / source).read_text("utf-8"))
        Draft202012Validator.check_schema(doc)
        linked.append((doc["$id"], Resource.from_contents(doc)))
    registry = Registry().with_resources(linked)
    errors = sorted(Draft202012Validator(schema, registry=registry).iter_errors(document),
                    key=lambda e: ".".join(str(x) for x in e.absolute_path))
    if errors:
        error = errors[0]
        refuse(name + " at " + ".".join(str(x) for x in error.absolute_path)
               + ": " + error.message)


def validate_rows(rows: Any) -> str:
    check(type(rows) is list and len(rows) <= MAX_ROWS,
          "input must be a bounded list of caller-declared synthetic records")
    for row in rows:
        check(type(row) is dict and len(row) <= 64,
              "each synthetic record must be a bounded plain object")
        for key, value in row.items():
            check(type(key) is str and FIELD.fullmatch(key) is not None,
                  "record field name is not a safe identifier")
            check(type(value) in (str, int, float, bool, type(None)),
                  "records must contain only plain JSON scalar values")
            if type(value) is str:
                check(len(value) <= 160 and
                      not any(ord(c) < 32 or ord(c) == 127 for c in value),
                      "record text must be bounded and printable")
            if type(value) in (int, float):
                check(math.isfinite(value) and abs(value) <= 2**53 - 1,
                      "unsafe or nonfinite numeric input")
        check("availability" in row and type(row["availability"]) is str and
              row["availability"] in STATES,
              "each record requires a recognized, explicit availability status")
    return hash_json(rows)


def validate_request(request: Any) -> None:
    schema_check(request, "stat-analysis-request.schema.json")
    check(request["kind"] == REQUEST_KIND and request["source"]["releaseId"] is None
          and request["source"]["sourceCommit"] is None,
          "only source-unverified synthetic fixtures are accepted")
    kind = request["method"]["chartType"]
    check(METHODS[kind] == request["method"]["methodId"],
          "method ID does not match the existing StatKit operation")
    fields, params = request["fields"], request["parameters"]
    per_method = {
        "histogram": {"bins", "scale"},
        "ecdf": set(), "boxplot": set(),
        "frequency": {"scale"},
        "scatter": {"xUnit"},
        "time-series": set(),
        "interval": {"lower", "upper", "intervalLabel"},
    }
    check(set(params) == per_method[kind],
          "only explicitly declared method-specific parameters are permitted")
    if kind == "histogram":
        bin_rule = params["bins"]
        check((type(bin_rule) is int and 1 <= bin_rule <= 64) or
              (type(bin_rule) is str and bin_rule in
               ("fd", "sturges", "sqrt", "auto")),
              "histogram bins must have a bounded named rule or integer bin count")
    if kind in ("scatter", "time-series", "interval"):
        check(fields["y"] is not None, "selected operation requires a Y field")
    else:
        check(fields["y"] is None, "selected operation is univariate")
    if kind == "frequency":
        check(fields["unit"] == "untyped",
              "categorical frequency must not imply a numeric unit")
    if kind == "interval":
        check(params["lower"] != params["upper"] and
              params["lower"] not in (fields["x"], fields["y"]) and
              params["upper"] not in (fields["x"], fields["y"]),
              "source interval bounds must use distinct declared columns")
    if kind == "scatter":
        check(fields["x"] != fields["y"],
              "paired scatter requires different source variables")
    # Reject arbitrary joins, code, filters or review authorization: these
    # do not exist in the strict synthetic request schema.
    check(request["controls"] == SOURCE_UNVERIFIED,
          "source and publication approval cannot be requested in this contract")
    lock = LOCK.read_text("utf-8")
    versions = re.findall(r"(?m)^numpy==([0-9]+(?:\.[0-9]+){2})$", lock)
    check(len(versions) == 1 and versions[0] == np.__version__,
          "installed NumPy must match the exact reviewed requirements lock")
    registry = json.loads(REGISTRY.read_text("utf-8"))
    matches = [m for m in registry["methods"]
               if m["kind"] == kind and m["methodId"] == METHODS[kind]]
    check(registry["publicationAuthorized"] is False and len(matches) == 1 and
          matches[0]["version"] == request["method"]["version"] and
          matches[0]["publicationAuthorized"] is False and
          matches[0]["independentReviewStatus"] == "pending",
          "installed statistical registry is not a preview-only approved implementation")


def statkit_call(request: dict, rows: list[dict]) -> dict:
    fields, params = request["fields"], request["parameters"]
    common = {"x": fields["x"], "segment": fields["segment"],
              "availability": fields["availability"], "where": request["filters"]}
    kind = request["method"]["chartType"]
    try:
        if kind == "histogram":
            return histogram(rows, unit=fields["unit"], bins=params["bins"],
                             scale=params["scale"], **common)
        if kind == "ecdf":
            return ecdf(rows, unit=fields["unit"], **common)
        if kind == "boxplot":
            return boxplot(rows, unit=fields["unit"], **common)
        if kind == "frequency":
            return frequency(rows, scale=params["scale"], **common)
        if kind == "scatter":
            return scatter(rows, y=fields["y"], x_unit=params["xUnit"],
                           y_unit=fields["unit"], **common)
        if kind == "time-series":
            return time_series(rows, y=fields["y"], unit=fields["unit"], **common)
        if kind == "interval":
            return intervals(rows, y=fields["y"], lower=params["lower"],
                             upper=params["upper"], unit=fields["unit"],
                             interval_label=params["intervalLabel"], **common)
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        raise StatArtifactError("STAT-02A rejected: existing StatKit method failed: "
                                + str(exc)) from exc
    refuse("unknown analysis operation")


def computation_versions(request: dict, chart: dict) -> dict:
    # File digests record exact calculation logic and dependency lockfile.
    # They establish reproducibility of the local installation, not trust in
    # the code, a source publisher or an independent human review.
    return {
        "methodId": request["method"]["methodId"],
        "methodVersion": request["method"]["version"],
        "chartType": request["method"]["chartType"],
        "statkitVersion": VERSION,
        "pythonVersion": platform.python_version(),
        "numpyVersion": np.__version__,
        "coreSha256": file_hash(CORE),
        "statkitInitSha256": file_hash(INIT),
        "runnerSha256": file_hash(RUNNER),
        "methodRegistrySha256": file_hash(REGISTRY),
        "requirementsSha256": file_hash(LOCK),
        "chartSha256": hash_json(chart),
        "chartInputFingerprint": chart["inputFingerprint"],
    }


def produce(request: dict, rows: list[dict]) -> dict:
    """Execute only approved preview *primitives* over caller-declared synthetic rows."""
    validate_request(request)
    input_sha = validate_rows(rows)
    chart = statkit_call(request, rows)
    schema_check(chart, "stat-chart-preview.schema.json")
    check(chart["kind"] == CONTRACT and chart["chartType"] ==
          request["method"]["chartType"] and
          chart["algorithm"]["methodId"] == request["method"]["methodId"] and
          chart["authority"] == SOURCE_UNVERIFIED,
          "StatKit chart did not retain unsigned method and preview identity")
    context = request["context"]
    selection = chart["selection"]
    qualifications = [
        "The input was declared synthetic by the caller and has not been authenticated as a government source.",
        "No sampling design, statistical uncertainty, population inference or causal effect has been certified.",
        *context["qualifications"],
        *chart["limitations"],
    ]
    check(len(qualifications) <= 24 and all(len(x) >= 12 for x in qualifications),
          "interpretive limitations are not fully bounded or documented")
    source = request["source"]
    artifact = {
        "schemaVersion": "1.0.0",
        "kind": KIND,
        "status": "synthetic-preview-not-approved",
        "sourceIdentity": {
            "sourceClass": "caller-declared-synthetic",
            "fixtureId": source["fixtureId"],
            "inputSha256": input_sha,
            "inputRowCount": len(rows),
            "canonicalization": "sorted-json-utf8-v1",
            "releaseId": None,
            "sourceCommit": None,
        },
        "request": request,
        "requestSha256": hash_json(request),
        "computation": computation_versions(request, chart),
        "chart": chart,
        "quality": {
            "availableRows": selection["missingness"]["available"],
            "selectedRows": selection["selectedRows"],
            "inputRows": selection["inputRows"],
            "missingness": selection["missingness"],
            "unitOfAnalysis": "synthetic-observation",
            "denominator": context["denominator"],
            "context": context,
            "publisherUncertaintyVerified": False,
            "limitations": qualifications,
        },
        "authority": {
            **SOURCE_UNVERIFIED,
            "independentReviewStatus": "not-applicable-to-synthetic-fixture",
        },
    }
    artifact["artifactSha256"] = hash_json(artifact)
    schema_check(artifact, "stat-analysis-artifact.schema.json")
    return artifact


def replay(artifact: dict, rows: list[dict]) -> dict:
    """Reject any changed inputs, computation environment or artifact bytes."""
    schema_check(artifact, "stat-analysis-artifact.schema.json")
    check(artifact["kind"] == KIND and
          artifact["sourceIdentity"]["sourceClass"] == "caller-declared-synthetic",
          "public-source and certified analytical artifacts are out of scope")
    check(artifact["artifactSha256"] == hash_json({
          k: v for k, v in artifact.items() if k != "artifactSha256"}),
          "analysis artifact fingerprint differs from its recorded contents")
    validate_request(artifact["request"])
    check(artifact["requestSha256"] == hash_json(artifact["request"]),
          "analysis request fingerprint mismatch")
    check(artifact["sourceIdentity"]["inputSha256"] == validate_rows(rows) and
          artifact["sourceIdentity"]["inputRowCount"] == len(rows),
          "synthetic input bytes or observation count changed")
    # A recomputation is mandatory; hashes alone would not verify that the
    # stored calculations came from the pinned numeric implementation.
    expected = produce(artifact["request"], rows)
    check(artifact == expected, "recomputed analysis differs from recorded result, "
          "method revision, dependencies, identity or limitations")
    return {"replay": "deterministic-match",
            "artifactSha256": artifact["artifactSha256"],
            "sourceAuthenticated": False,
            "publicationAuthorized": False}


def read_json_file(path: str) -> Any:
    file = Path(path)
    if not file.is_file() or file.stat().st_size > MAX_JSON_BYTES:
        refuse("input must be a bounded local JSON file")
    # Explicitly prevent the synthetic CLI from accidentally accepting a
    # checked-in published government evidence asset as a "fixture."
    if (ROOT / "publication") in file.resolve().parents:
        refuse("published evidence assets may not be used as synthetic CLI fixtures")
    raw = file.read_bytes()
    check(len(raw) <= MAX_JSON_BYTES, "JSON input file exceeds size limit")

    def reject_constant(token):
        refuse("JSON must not contain nonfinite numeric tokens: " + token)

    def reject_duplicates(pairs):
        item = {}
        for key, value in pairs:
            if key in item:
                refuse("duplicate JSON object key: " + key)
            item[key] = value
        return item

    try:
        return json.loads(raw.decode("utf-8"), parse_constant=reject_constant,
                          object_pairs_hook=reject_duplicates)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise StatArtifactError("STAT-02A rejected: malformed JSON file") from exc


def write_output(target: str, result: dict) -> None:
    output = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True,
                        allow_nan=False) + "\n"
    if target == "-":
        print(output, end="")
        return
    dest = Path(target).resolve()
    for name in ("publication", "governance", "catalog", "contracts"):
        check((ROOT / name) not in dest.parents,
              "analysis previews must never be written into official evidence or governance directories")
    # Exclusive creation: replay must not overwrite immutable release,
    # manuscript, existing synthetic fixture or previous analysis.
    try:
        with dest.open("x", encoding="utf-8") as handle:
            handle.write(output)
    except FileExistsError as exc:
        raise StatArtifactError("STAT-02A rejected: artifact destination already exists") from exc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Unsigned reproducible statistical preview")
    parser.add_argument("command", choices=("produce", "replay"))
    parser.add_argument("--input", required=True, help="Declared synthetic JSON observations")
    parser.add_argument("--request", help="Typed synthetic analysis request for produce")
    parser.add_argument("--artifact", help="Recorded analysis artifact for replay")
    parser.add_argument("--output", default="-", help="New JSON artifact file or stdout")
    args = parser.parse_args(argv)
    if (args.command == "produce" and (not args.request or args.artifact)) or (
            args.command == "replay" and (not args.artifact or args.request)):
        parser.error("produce needs --request; replay needs --artifact, never both")
    rows = read_json_file(args.input)
    if args.command == "produce":
        result = produce(read_json_file(args.request), rows)
    else:
        result = replay(read_json_file(args.artifact), rows)
    write_output(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
