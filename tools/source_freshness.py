"""DATA-10F: bounded official-source acquisition/freshness evidence ledger.

This is a repository-source mirror operations record, NOT statistical review.
Publisher record dates are not original publication/modified timestamps.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re

SCHEMA = "ARFI-SourceAcquisitionLedger/1.0.0"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{3,70}$")
MAX_FEEDS = 300


class LedgerError(ValueError):
    """An acquisition record contradicts its verified source evidence."""


def require(test, reason):
    if not test:
        raise LedgerError("ARFI source acquisition ledger rejected: " + reason)


def utc_date(value):
    require(type(value) is str and value.endswith("Z"), "non-UTC timestamp")
    try:
        stamp = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise LedgerError("ARFI source acquisition ledger rejected: invalid UTC date") from exc
    require(stamp.tzinfo is not None and stamp.utcoffset() == timedelta(0),
            "invalid timezone")
    return stamp


def utc_string(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def source_fingerprint(entry):
    """Hash the exact registered collection of verified partition digests.

    Changes to a historical publisher record change its partition digest.
    A count or publisher measurement date alone is not a release fingerprint.
    """
    require(type(entry) is dict and type(entry.get("id")) is str and
            IDENTIFIER.fullmatch(entry["id"]) is not None, "invalid source identity")
    partitions = entry.get("partitions")
    require(type(partitions) is list and 1 <= len(partitions) <= 1200,
            "empty or unbounded source partitions")
    rows = 0
    keys = set()
    payload = []
    for part in partitions:
        require(type(part) is dict and type(part.get("path")) is str and
                part["path"].startswith("publication/source-library/data/" + entry["id"] + "/") and
                type(part.get("sha256")) is str and SHA256.fullmatch(part["sha256"]) and
                type(part.get("rows")) is int and part["rows"] > 0 and
                type(part.get("bytes")) is int and 0 < part["bytes"] <= 3_000_000 and
                part["path"] not in keys, "invalid or repeated source partition digest")
        keys.add(part["path"])
        rows += part["rows"]
        payload.append([part["path"], part["sha256"], part["rows"], part["bytes"]])
    require(type(entry.get("rowCount")) is int and rows == entry["rowCount"],
            "source row count mismatch")
    return sha256((json.dumps(sorted(payload), separators=(",", ":"), ensure_ascii=True)
                   + "\n").encode("utf-8")).hexdigest()


def sources_by_id(index):
    require(type(index) is dict and
            index.get("schemaVersion") == "1.0.0" and
            index.get("sourceClass") == "automated-official-source-copy" and
            type(index.get("datasets")) is list, "invalid original source index")
    result = {}
    for entry in index["datasets"]:
        key = entry.get("id") if type(entry) is dict else None
        require(type(key) is str and key not in result, "duplicate source mirror identity")
        source_fingerprint(entry)
        result[key] = entry
    require(len(result) <= MAX_FEEDS, "source index exceeds reviewed ceiling")
    return result


def source_specs(catalog):
    require(type(catalog) is dict and type(catalog.get("datasets")) is list and
            1 <= len(catalog["datasets"]) <= MAX_FEEDS, "invalid registration inventory")
    specs = {}
    for spec in catalog["datasets"]:
        key = spec.get("id") if type(spec) is dict else None
        require(type(key) is str and IDENTIFIER.fullmatch(key) is not None and
                key not in specs, "duplicate or invalid source registration")
        specs[key] = spec
    return specs


def validate_health(health, specs):
    require(type(health) is dict and health.get("schemaVersion") == "1.0.0" and
            type(health.get("failed")) is dict and
            type(health.get("discoveryWarnings")) is dict and
            type(health.get("attempted")) is int and
            health["attempted"] == len(specs) and
            type(health.get("succeeded")) is int and
            health["succeeded"] == len(specs) - len(health["failed"]) and
            set(health["failed"]) <= set(specs) and
            all(type(v) is str and v for v in health["failed"].values()),
            "health acquisition totals or source identifiers invalid")
    utc_date(health.get("checkedAt"))


def report_for(catalog, index, health, prior_index=None, prior_report=None):
    """Build truthful source availability from a completed verified acquisition.

    A prior mirror predating this ledger has UNKNOWN first-observed time.
    We never infer publisher publication time from a survey date, a harvest
    timestamp, a commit date, or a newly downloaded source.
    """
    specs = source_specs(catalog)
    current = sources_by_id(index)
    previous = sources_by_id(prior_index) if prior_index is not None else {}
    validate_health(health, specs)
    require(set(current) <= set(specs), "unregistered mirrored source")
    require(not (set(previous) - set(current)), "previously mirrored source disappeared")
    checked = health["checkedAt"]
    previous_rows = {}
    if prior_report is not None:
        require(type(prior_report) is dict and prior_report.get("schemaVersion") == SCHEMA and
                type(prior_report.get("sources")) is list, "invalid prior ledger")
        prior_time = utc_date(prior_report.get("checkedAt"))
        require(prior_time <= utc_date(checked), "source check clock moved backwards")
        previous_rows = {x.get("id"): x for x in prior_report["sources"]
                         if type(x) is dict}
        # Some registrations legitimately failed their first download. They
        # have a ledger row but *no* source bytes or prior mirror fingerprint.
        # Permit only that explicit state; it must not invent first-seen custody.
        require(len(previous_rows) == len(prior_report["sources"]) and
                set(previous_rows) <= set(specs) and
                all(
                    (type(x.get("mirrorFingerprint")) is str and
                     SHA256.fullmatch(x["mirrorFingerprint"]) and
                     x["mirrorFingerprint"] == source_fingerprint(previous[key]))
                    if key in previous else
                    (x.get("status") == "registered_not_acquired" and
                     x.get("mirrorFingerprint") is None and
                     x.get("firstSeenInMirrorAt") is None and
                     x.get("lastSuccessfulCheckAt") is None)
                    for key, x in previous_rows.items()),
                "prior acquisition ledger is disconnected from previous source index")
    data = []
    providers = {}
    failures = health["failed"]
    for key, spec in sorted(specs.items()):
        current_row = current.get(key)
        old_row = previous.get(key)
        past = previous_rows.get(key, {})
        error = failures.get(key)
        provider = spec.get("provider") or "treasury-fiscaldata"
        require(provider in ("treasury-fiscaldata", "cdc-places", "bls-qcew", "census-acs5", "bea-regional"),
                "unknown registered provider for source coverage")
        fingerprint = source_fingerprint(current_row) if current_row else None
        old_fp = source_fingerprint(old_row) if old_row else None
        new = current_row is not None and old_row is None and not error
        changed = (current_row is not None and old_row is not None and not error and
                   fingerprint != old_fp)
        last_success = checked if error is None else past.get("lastSuccessfulCheckAt")
        first_seen = checked if new else past.get("firstSeenInMirrorAt")
        revised_at = checked if (new or changed) else past.get("lastChangeObservedAt")
        for stamp in (first_seen, revised_at, last_success):
            if stamp is not None:
                require(utc_date(stamp) <= utc_date(checked),
                        "source evidence timestamp is in the future")
        status = ("registered_not_acquired" if current_row is None else
                  "retained_previous_after_failure" if error else
                  "verified_this_refresh")
        row = {
            "id": key,
            "provider": provider,
            "status": status,
            "mirrorFingerprint": fingerprint,
            "rowCount": current_row["rowCount"] if current_row else None,
            "partitionCount": len(current_row["partitions"]) if current_row else None,
            "publisherRecordThrough": current_row.get("latestDate") if current_row else None,
            "publisherDateBasis": current_row.get("dateBasis") if current_row else None,
            "publisherReleasePublishedAt": None,
            "firstSeenInMirrorAt": first_seen,
            "lastChangeObservedAt": revised_at,
            "lastCheckedAt": checked,
            "lastSuccessfulCheckAt": last_success,
            "lastFailureAt": checked if error else past.get("lastFailureAt"),
            "sourceReleaseToGitLagDays": None,
            "publisherToMirrorSlo": "unmeasurable_without_verified_publisher_release_timestamp",
        }
        for name in ("lastFailureAt",):
            if row[name] is not None:
                require(utc_date(row[name]) <= utc_date(checked),
                        "source failure evidence in the future")
        data.append(row)
        bucket = providers.setdefault(provider, {
            "registered": 0, "mirrored": 0, "succeeded": 0, "failed": 0
        })
        bucket["registered"] += 1
        bucket["mirrored"] += int(current_row is not None)
        bucket["succeeded"] += int(error is None)
        bucket["failed"] += int(error is not None)
    totals = {
        "registered": len(specs), "mirrored": len(current),
        "attempted": health["attempted"], "succeeded": health["succeeded"],
        "failed": len(failures), "registeredNotAcquired": len(specs) - len(current),
        "retainedAfterFailure": sum(x["status"] == "retained_previous_after_failure"
                                    for x in data),
        "newlyMirroredAtThisRefresh": sum(x["firstSeenInMirrorAt"] == checked and
                                          x["id"] not in previous for x in data),
        "changedMirroredAtThisRefresh": sum(x["id"] in previous and
             x["lastChangeObservedAt"] == checked and
             x["status"] == "verified_this_refresh" and
             source_fingerprint(current[x["id"]]) != source_fingerprint(previous[x["id"]])
             for x in data if x["id"] in current),
        "sourceRecords": sum(x["rowCount"] for x in data if x["rowCount"] is not None),
        "sourcePartitions": sum(x["partitionCount"] for x in data
                                if x["partitionCount"] is not None),
    }
    return {
        "schemaVersion": SCHEMA,
        "sourceClass": "official-publisher-record-mirror-operational-evidence",
        "checkedAt": checked,
        "weeklyCheckTargetDays": 7,
        "publisherToMirrorEscalationDays": 14,
        "nextExpectedCheckAt": utc_string(utc_date(checked) + timedelta(days=7)),
        "escalateIfUncheckedAt": utc_string(utc_date(checked) + timedelta(days=14)),
        "publicationLagMeasurementStatus": "not_measurable_without_publisher_release_timestamps",
        "originalSourceReleaseTimesVerified": 0,
        "sourceFirstSeenHistoryBeforeLedger": "unknown_unless_recorded",
        "totals": totals,
        "providers": {k: providers[k] for k in sorted(providers)},
        "discoveryWarningProviders": sorted(health["discoveryWarnings"]),
        "sources": data,
    }


def verify_report(report, index, health):
    """Verify written operational report against the actual indexed source copies."""
    current = sources_by_id(index)
    require(type(report) is dict and report.get("schemaVersion") == SCHEMA and
            type(report.get("sources")) is list and
            type(report.get("totals")) is dict and
            type(report.get("providers")) is dict, "unrecognized report shape")
    require(report.get("checkedAt") == health.get("checkedAt"),
            "report/health check epoch differs")
    utc_date(report["checkedAt"])
    require(report.get("publicationLagMeasurementStatus") ==
            "not_measurable_without_publisher_release_timestamps" and
            report.get("originalSourceReleaseTimesVerified") == 0,
            "source publication delay is falsely certified")
    require(report.get("weeklyCheckTargetDays") == 7 and
            report.get("publisherToMirrorEscalationDays") == 14 and
            report.get("nextExpectedCheckAt") ==
              utc_string(utc_date(report["checkedAt"]) + timedelta(days=7)) and
            report.get("escalateIfUncheckedAt") ==
              utc_string(utc_date(report["checkedAt"]) + timedelta(days=14)),
            "freshness window or delayed escalation changed")
    values = report["sources"]
    require(len(values) == report["totals"].get("registered") and
            len({r.get("id") for r in values if type(r) is dict}) == len(values),
            "coverage source set duplicate or incomplete")
    require(set(current) <= {r["id"] for r in values},
            "mirror source omitted from coverage")
    require(report["totals"].get("mirrored") == len(current) and
            report["totals"].get("sourceRecords") ==
              sum(x["rowCount"] for x in current.values()) and
            report["totals"].get("sourcePartitions") ==
              sum(len(x["partitions"]) for x in current.values()) and
            report["totals"].get("attempted") == health.get("attempted") and
            report["totals"].get("succeeded") == health.get("succeeded") and
            report["totals"].get("failed") == len(health.get("failed", {})),
            "mirror counters differ from source records or health")
    for row in values:
        require(type(row) is dict and type(row.get("id")) is str and
                type(row.get("provider")) is str and
                row.get("publisherReleasePublishedAt") is None and
                row.get("sourceReleaseToGitLagDays") is None and
                row.get("publisherToMirrorSlo") ==
                 "unmeasurable_without_verified_publisher_release_timestamp" and
                row.get("lastCheckedAt") == health["checkedAt"],
                "source freshness was fabricated")
        entry = current.get(row["id"])
        require(row.get("mirrorFingerprint") ==
                  (source_fingerprint(entry) if entry is not None else None) and
                row.get("rowCount") == (entry["rowCount"] if entry else None) and
                row.get("partitionCount") ==
                  (len(entry["partitions"]) if entry else None) and
                row.get("publisherRecordThrough") ==
                  (entry.get("latestDate") if entry else None) and
                row.get("publisherDateBasis") ==
                  (entry.get("dateBasis") if entry else None),
                "per-source fingerprint or measurement date forged")
        for field in ("firstSeenInMirrorAt", "lastChangeObservedAt",
                      "lastSuccessfulCheckAt", "lastFailureAt"):
            if row.get(field) is not None:
                require(utc_date(row[field]) <= utc_date(report["checkedAt"]),
                        "future or malformed source timestamp")
        failed = row["id"] in health.get("failed", {})
        expected_state = ("registered_not_acquired" if entry is None else
                          "retained_previous_after_failure" if failed else
                          "verified_this_refresh")
        require(row.get("status") == expected_state,
                "source acquisition status contradicts health")
        if expected_state == "verified_this_refresh":
            require(row.get("lastSuccessfulCheckAt") == report["checkedAt"],
                    "successful source has no verified acquisition time")
    providers = {}
    for row in values:
        p = providers.setdefault(row["provider"],
            {"registered": 0, "mirrored": 0, "succeeded": 0, "failed": 0})
        p["registered"] += 1
        p["mirrored"] += int(row["status"] != "registered_not_acquired")
        p["succeeded"] += int(row["id"] not in health.get("failed", {}))
        p["failed"] += int(row["id"] in health.get("failed", {}))
    require(report["providers"] == {k: providers[k] for k in sorted(providers)} and
            report["totals"].get("registeredNotAcquired") ==
              sum(r["status"] == "registered_not_acquired" for r in values) and
            report["totals"].get("retainedAfterFailure") ==
              sum(r["status"] == "retained_previous_after_failure" for r in values) and
            report.get("discoveryWarningProviders") ==
              sorted(health.get("discoveryWarnings", {})),
            "publisher coverage summary or discovery warning misrepresented")
    return {"registered": len(values), "mirrored": len(current),
            "verifiedPartitions": report["totals"]["sourcePartitions"],
            "publisherReleaseLagMeasurable": False}

def check_cadence(report, as_of):
    """Operational last-success ages, deliberately NOT publisher-release latency."""
    now = utc_date(as_of)
    checked = utc_date(report["checkedAt"])
    require(now >= checked, "check-cadence time before source refresh")
    overdue, escalated, never_acquired = [], [], []
    for row in report["sources"]:
        if row["status"] == "registered_not_acquired":
            never_acquired.append(row["id"])
            continue
        last = row.get("lastSuccessfulCheckAt")
        if last is None:
            overdue.append(row["id"])
            continue
        age = now - utc_date(last)
        require(age >= timedelta(0), "source last-success clock in the future")
        if age > timedelta(days=14):
            escalated.append(row["id"])
        elif age > timedelta(days=7):
            overdue.append(row["id"])
    age = now - checked
    status = ("escalation_required"
              if age > timedelta(days=14) or escalated else
              "overdue_or_unacquired"
              if age > timedelta(days=7) or overdue or never_acquired else
              "within_seven_day_check_target")
    return {
        "daysSinceLatestRefreshCheck": round(age.total_seconds() / 86400, 4),
        "checkCadenceStatus": status,
        "overdueSourceIds": sorted(overdue),
        "escalatedSourceIds": sorted(escalated),
        "neverAcquiredSourceIds": sorted(never_acquired),
        "publisherReleaseLagMeasurable": False,
    }


def main():
    """Verify the Git branch's report without claiming publisher release timeliness."""
    import argparse
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--check-cadence", action="store_true")
    parser.add_argument("--as-of", help="UTC ISO8601 override for reproducible checks")
    parser.add_argument("--root", help="Source checkout directory (default: this repository)")
    args = parser.parse_args()
    if not args.verify and not args.check_cadence:
        parser.error("Select --verify and/or --check-cadence")
    if args.root:
        root = Path(args.root).resolve()
    path = root / "publication/source-library"
    index = json.loads((path / "index.json").read_text("utf-8"))
    health = json.loads((path / "health.json").read_text("utf-8"))
    ledger = json.loads((path / "acquisition-ledger.json").read_text("utf-8"))
    result = verify_report(ledger, index, health)
    if args.check_cadence:
        result.update(check_cadence(
            ledger, args.as_of or utc_string(datetime.now(timezone.utc))))
    print(json.dumps(result, sort_keys=True))
    if args.check_cadence and result["checkCadenceStatus"] != "within_seven_day_check_target":
        raise SystemExit(2 if result["checkCadenceStatus"]=="escalation_required" else 1)


if __name__ == "__main__":
    main()
