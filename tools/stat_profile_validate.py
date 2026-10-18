"""STAT-01 immutable statistical source-profile admission (no analysis execution).

Unlike a JSON declaration alone, verifies actual published manifests,
asset SHA-256, observations, qualifications and the historical source commit.
No inference or reviewer authentication is implied by a successful check.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = Path("contracts")
PROFILES_DIR = Path("catalog/statistics/source-profiles")
REGISTRY = Path("catalog/statistics/method-applicability.json")
SOURCE_COMMIT = re.compile(r"^[a-f0-9]{40}$")
RELEASE_ID = re.compile(r"^[a-z0-9-]+$")


class StatisticalProfileError(ValueError):
    """A statistical input is not eligible to be trusted."""


def fail(message):
    raise StatisticalProfileError("STAT-01 source profile rejected: " + message)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def check_schema(record, schema_file):
    schema = load(ROOT / schema_file)
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(
        schema, format_checker=FormatChecker()).iter_errors(record),
        key=lambda e: ".".join(str(v) for v in e.absolute_path))
    if errors:
        error = errors[0]
        fail(schema_file + ": " + "/".join(str(v) for v in error.absolute_path) +
             ": " + error.message)
    return record


def git_blob_sha(payload):
    return hashlib.sha1(b"blob " + str(len(payload)).encode("ascii") +
                        b"\x00" + payload).hexdigest()


def verify_historical_manifest(root, commit, path, current_hash):
    if not SOURCE_COMMIT.fullmatch(commit):
        fail("historical source commit is not an immutable SHA")
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "show", commit + ":" + path],
            capture_output=True, check=True, timeout=15)
    except (subprocess.CalledProcessError, FileNotFoundError,
            subprocess.TimeoutExpired) as exc:
        fail("historical immutable source commit unavailable: " + type(exc).__name__)
    if git_blob_sha(result.stdout) != current_hash:
        fail("historical source manifest does not match its pinned identity")


def verify_profile(profile, *, root=ROOT, historical=True):
    """Revalidate checked-in profile and actual source bytes; do not trust callers."""
    root = Path(root)
    check_schema(profile, "contracts/statistical-source-profile.schema.json")
    identity = profile["identity"]
    release = identity["releaseId"]
    if not RELEASE_ID.fullmatch(release):
        fail("unsafe release identifier")
    required_path = "publication/releases/" + release + "/manifest.json"
    if identity["manifestPath"] != required_path:
        fail("manifest path is not the exact release path")
    publication = load(root / "publication/index.json")
    entries = [x for x in publication["releases"] if x["releaseId"] == release]
    if len(entries) != 1 or entries[0]["status"] != "published":
        fail("release is not in the approved publication index")
    entry = entries[0]
    if entry["manifestPath"] != required_path or (
            identity["indicatorId"] != entry["indicatorId"] or
            profile["coverage"]["geography"] != entry["geography"]):
        fail("indicator, geography or index does not match the profile")
    raw = (root / required_path).read_bytes()
    if git_blob_sha(raw) != identity["manifestGitBlobSha"]:
        fail("published manifest bytes changed against pinned profile")
    if historical:
        verify_historical_manifest(root, identity["sourceCommit"], required_path,
                                   identity["manifestGitBlobSha"])
    manifest = json.loads(raw)
    coverage = profile["coverage"]
    measure = profile["measurement"]
    if (manifest["releaseId"] != release or
            manifest["datasetId"] != identity["datasetId"] or
            manifest["status"] != "published" or
            manifest["geography"]["level"] != coverage["geography"] or
            manifest["geography"]["vintage"] != coverage["geographyVintage"] or
            manifest["temporalCoverage"]["firstYear"] != coverage["firstYear"] or
            manifest["temporalCoverage"]["lastYear"] != coverage["lastYear"]):
        fail("publisher manifest semantics differ from statistical source profile")
    if manifest["assets"]["observations"]["sha256"] != identity["observationsSha256"]:
        fail("publisher observation asset fingerprint differs from source profile")
    observations = (root / "publication/releases" / release /
                    manifest["assets"]["observations"]["path"]).read_bytes()
    if (hashlib.sha256(observations).hexdigest() != identity["observationsSha256"] or
            len(observations) != manifest["assets"]["observations"]["bytes"]):
        fail("publisher observations do not reproduce the approved asset SHA-256")
    document = json.loads(observations)
    records = document["observations"]
    if (document["indicatorId"] != identity["indicatorId"] or
            document["datasetId"] != identity["datasetId"] or
            len(records) != coverage["sourceRows"] or
            manifest["assets"]["observations"]["rows"] != len(records)):
        fail("observation identity or published row count changed")
    if (coverage["sourceRows"] != coverage["availableRows"] +
            coverage["explicitUnavailableRows"] or
            coverage["firstYear"] > coverage["lastYear"]):
        fail("profile availability or temporal coverage inconsistent")
    seen = set()
    counts = {"available": 0, "not_available": 0}
    for row in records:
        geo = row.get(measure["geographyField"])
        year = row.get(measure["yearField"])
        expected_length = 2 if coverage["geography"] == "state" else 5
        if (not isinstance(geo, str) or not geo.isdigit() or
                len(geo) != expected_length or
                type(year) is not int or
                not coverage["firstYear"] <= year <= coverage["lastYear"]):
            fail("observation geography or source period is malformed")
        key = (geo, year)
        if key in seen:
            fail("duplicate geography/period publisher observation")
        seen.add(key)
        if row.get("unit") != measure["unit"]:
            fail("source-native numerical unit mismatch")
        status = row.get(measure["statusField"], "available") if (
            measure["statusField"]) else "available"
        if status not in counts:
            fail("unknown publisher availability classification")
        counts[status] += 1
        value = row.get(measure["valueField"])
        if status == "available":
            if type(value) not in (int, float) or not math.isfinite(value):
                fail("available publisher value is not a finite number")
        elif value is not None:
            fail("explicitly unavailable publisher value is not null")
        bound = measure["intervalFields"]
        if bound:
            for col in (bound["lower"], bound["upper"]):
                value_bound = row.get(col)
                if status == "available" and (
                        type(value_bound) not in (int, float) or
                        not math.isfinite(value_bound)):
                    fail("source-published confidence interval bound unavailable")
                if status != "available" and value_bound is not None:
                    fail("unavailable publisher record has non-null bounds")
            if status == "available" and not (
                    row[bound["lower"]] <= value <= row[bound["upper"]]):
                fail("publisher interval does not contain the published point estimate")
        money = measure["exactAmountField"]
        if money and status == "available" and (
                not isinstance(row.get(money), str) or
                re.fullmatch(r"-?(?:0|[1-9]\d*)(?:\.\d{1,2})?",
                             row[money]) is None):
            fail("original signed decimal amount missing or altered")
    if (counts["available"] != coverage["availableRows"] or
            counts["not_available"] != coverage["explicitUnavailableRows"]):
        fail("published missingness counts do not match source observations")
    if coverage["knownOmittedSourceBuckets"]:
        excluded = manifest["assets"].get("geographyExclusions")
        if not excluded or excluded["rows"] != coverage["knownOmittedSourceBuckets"]:
            fail("geographically excluded source ledger count was suppressed")
    elif measure["family"] == "administrative-money-flow":
        fail("administrative geography exclusions have not been accounted for")
    if measure["publisherModelled"] != (
            measure["family"] == "publisher-modeled-prevalence"):
        fail("publisher statistical model classification is invalid")
    return profile


def verify_all_profiles(*, root=ROOT, historical=True):
    root = Path(root)
    publication = load(root / "publication/index.json")
    approved = {x["releaseId"] for x in publication["releases"]
                if x["status"] == "published"}
    profiles = root / PROFILES_DIR
    seen = {x.stem for x in profiles.glob("*.json")}
    if approved != seen:
        fail("published releases must match statistical profiles exactly; missing=" +
             repr(sorted(approved - seen)) + " extra=" + repr(sorted(seen - approved)))
    for release in sorted(approved):
        verify_profile(load(profiles / (release + ".json")),
                       root=root, historical=historical)
    register = load(root / REGISTRY)
    check_schema(register, "contracts/statistical-method-applicability.schema.json")
    base = load(root / "contracts/stat-method-registry.json")
    expected = {m["methodId"]: m["kind"] for m in base["methods"]}
    actual = {m["methodId"]: m["chartType"] for m in register["methods"]}
    if len(actual) != len(register["methods"]) or actual != expected:
        fail("statistical eligibility registry diverged from approved StatKit method IDs")
    if (base["publicationAuthorized"] or register["publicationAuthorized"] or
            any(m["publicationAuthorized"] or
                m["reviewStatus"] != "not_independently_certified"
                for m in register["methods"])):
        fail("statistical method registry cannot claim independent publication")
    return {"profiles": len(approved), "methods": len(actual),
            "publishedDerivedAnalysisAuthorized": False}


if __name__ == "__main__":
    print(json.dumps(verify_all_profiles(), sort_keys=True))
