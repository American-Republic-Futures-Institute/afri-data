"""DATA-10F repeatable acquisition-evidence and operational source-SLO tests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.source_library import BASE, SourceLibraryError, refresh, verify
from tools.source_freshness import (
    LedgerError, report_for, source_fingerprint, verify_report,
)

AT="2026-10-21T08:00:00Z"
WEEK="2026-10-28T08:00:00Z"
LATER="2026-11-04T08:00:00Z"


def spec(id="treasury-ledger"):
    return {"id": id, "title": "Synthetic original Treasury record for test",
            "domain": "public-finance", "provider": None,
            "description": "Synthetic government source test fixture; never real government records.",
            "endpoint": "v2/accounting/od/debt_to_penny", "dateField": "record_date",
            "preferredField": "balance_amt", "unit": "USD", "maxRows": 5000,
            "sourcePage": "https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/"}


def catalog(ids=("treasury-ledger",)):
    return {"schemaVersion": "1.0.0", "publisher": "U.S. Treasury",
            "publisherApi": BASE, "refreshCadence": "weekly",
            "datasetClass": "source-native-unreviewed",
            "datasets": [spec(i) for i in ids]}


def rows(value="1200.57"):
    return [
        {"record_date":"2023-12-31","balance_amt":"999.99","kind":"A"},
        {"record_date":"2024-01-31","balance_amt":value,"kind":"B"},
    ]


def report(root):
    return json.loads((root/"publication/source-library/acquisition-ledger.json").read_text("utf-8"))


def health(root):
    return json.loads((root/"publication/source-library/health.json").read_text("utf-8"))


def index(root):
    return json.loads((root/"publication/source-library/index.json").read_text("utf-8"))


class FreshnessLedgerTests(unittest.TestCase):
    def test_new_mirror_reports_observed_time_but_never_invents_publisher_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            result=refresh(root=p,catalog=catalog(),loader=lambda _:rows(),now=AT)
            self.assertEqual(result["datasets"],1)
            led=report(p)
            self.assertEqual(led["schemaVersion"],"ARFI-SourceAcquisitionLedger/1.0.0")
            self.assertEqual(led["totals"]["newlyMirroredAtThisRefresh"],1)
            self.assertEqual(led["totals"]["changedMirroredAtThisRefresh"],0)
            self.assertEqual(led["totals"]["sourceRecords"],2)
            self.assertEqual(led["providers"]["treasury-fiscaldata"]["mirrored"],1)
            self.assertEqual(led["nextExpectedCheckAt"],WEEK)
            self.assertEqual(led["escalateIfUncheckedAt"],LATER)
            self.assertEqual(led["publicationLagMeasurementStatus"],
                "not_measurable_without_publisher_release_timestamps")
            s=led["sources"][0]
            self.assertEqual(s["status"],"verified_this_refresh")
            self.assertEqual(s["firstSeenInMirrorAt"],AT)
            self.assertEqual(s["lastChangeObservedAt"],AT)
            self.assertEqual(s["lastSuccessfulCheckAt"],AT)
            self.assertEqual(s["publisherRecordThrough"],"2024-01-31")
            self.assertEqual(s["publisherDateBasis"],"original-publisher-record-date")
            self.assertIsNone(s["publisherReleasePublishedAt"])
            self.assertIsNone(s["sourceReleaseToGitLagDays"])
            self.assertEqual(s["publisherToMirrorSlo"],
                "unmeasurable_without_verified_publisher_release_timestamp")
            self.assertEqual(verify(p)["datasets"],1)

    def test_recheck_does_not_reset_first_seen_or_material_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            refresh(root=p,catalog=catalog(),loader=lambda _:rows(),now=AT)
            original=report(p)["sources"][0]
            refresh(root=p,catalog=catalog(),loader=lambda _:list(reversed(rows())),
                now=WEEK)
            new=report(p)["sources"][0]
            self.assertEqual(new["mirrorFingerprint"],original["mirrorFingerprint"])
            self.assertEqual(new["firstSeenInMirrorAt"],AT)
            self.assertEqual(new["lastChangeObservedAt"],AT)
            self.assertEqual(new["lastSuccessfulCheckAt"],WEEK)
            self.assertEqual(report(p)["totals"]["newlyMirroredAtThisRefresh"],0)
            self.assertEqual(report(p)["totals"]["changedMirroredAtThisRefresh"],0)

    def test_changed_historical_publisher_partition_creates_revision_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            refresh(root=p,catalog=catalog(),loader=lambda _:rows(),now=AT)
            original=report(p)["sources"][0]["mirrorFingerprint"]
            refresh(root=p,catalog=catalog(),loader=lambda _:rows("4500.11"),
                    now=WEEK)
            led=report(p)
            self.assertEqual(led["totals"]["changedMirroredAtThisRefresh"],1)
            self.assertEqual(led["sources"][0]["firstSeenInMirrorAt"],AT)
            self.assertEqual(led["sources"][0]["lastChangeObservedAt"],WEEK)
            self.assertNotEqual(led["sources"][0]["mirrorFingerprint"],original)
            self.assertIsNone(led["sources"][0]["publisherReleasePublishedAt"])
            self.assertIsNone(led["sources"][0]["sourceReleaseToGitLagDays"])
            self.assertEqual(verify(p)["records"],2)

    def test_old_existing_mirror_without_ledger_keeps_older_provenance_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            refresh(root=p,catalog=catalog(),loader=lambda _:rows(),now=AT)
            (p/"publication/source-library/acquisition-ledger.json").unlink()
            refresh(root=p,catalog=catalog(),loader=lambda _:rows(),now=WEEK)
            s=report(p)["sources"][0]
            self.assertIsNone(s["firstSeenInMirrorAt"])
            self.assertIsNone(s["lastChangeObservedAt"])
            self.assertEqual(s["lastSuccessfulCheckAt"],WEEK)
            self.assertEqual(report(p)["totals"]["newlyMirroredAtThisRefresh"],0)

    def test_failed_source_retains_exact_old_partition_and_no_false_success(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            c=catalog(("treasury-ledger","treasury-other"))
            refresh(root=p,catalog=c,loader=lambda _:rows(),now=AT)
            original=index(p)
            def publisher(s):
                if s["id"]=="treasury-other":
                    raise SourceLibraryError("Official publisher temporarily unavailable")
                return rows()
            refresh(root=p,catalog=c,loader=publisher,now=WEEK)
            self.assertEqual(index(p),original)
            led=report(p)
            by_id={r["id"]:r for r in led["sources"]}
            self.assertEqual(led["totals"]["failed"],1)
            self.assertEqual(led["totals"]["retainedAfterFailure"],1)
            self.assertEqual(led["totals"]["mirrored"],2)
            self.assertEqual(by_id["treasury-other"]["status"],"retained_previous_after_failure")
            self.assertEqual(by_id["treasury-other"]["lastSuccessfulCheckAt"],AT)
            self.assertEqual(by_id["treasury-other"]["lastFailureAt"],WEEK)
            self.assertEqual(by_id["treasury-other"]["lastCheckedAt"],WEEK)
            self.assertEqual(by_id["treasury-other"]["firstSeenInMirrorAt"],AT)
            self.assertEqual(verify(p)["records"],4)

    def test_registered_new_source_can_fail_without_becoming_mirrored(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            refresh(root=p,catalog=catalog(),loader=lambda _:rows(),now=AT)
            c=catalog(("treasury-ledger","treasury-other"))
            def partial(s):
                if s["id"]=="treasury-other":
                    raise SourceLibraryError("No original bytes")
                return rows()
            refresh(root=p,catalog=c,loader=partial,now=WEEK)
            led=report(p)
            s=next(v for v in led["sources"] if v["id"]=="treasury-other")
            self.assertEqual(s["status"],"registered_not_acquired")
            self.assertEqual(led["totals"]["registered"],2)
            self.assertEqual(led["totals"]["mirrored"],1)
            self.assertEqual(led["totals"]["registeredNotAcquired"],1)
            self.assertIsNone(s["firstSeenInMirrorAt"])
            self.assertIsNone(s["lastSuccessfulCheckAt"])
            self.assertIsNone(s["mirrorFingerprint"])
            refresh(root=p,catalog=c,loader=lambda _:rows(),now=LATER)
            new=next(v for v in report(p)["sources"] if v["id"]=="treasury-other")
            self.assertEqual(new["firstSeenInMirrorAt"],LATER)
            self.assertEqual(report(p)["totals"]["newlyMirroredAtThisRefresh"],1)

    def test_undeclared_removal_of_mirrored_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            c=catalog(("treasury-ledger","treasury-other"))
            refresh(root=p,catalog=c,loader=lambda _:rows(),now=AT)
            with self.assertRaisesRegex(LedgerError,"previously mirrored source disappeared"):
                refresh(root=p,catalog=catalog(),loader=lambda _:rows(),now=WEEK)

    def test_earlier_health_and_invalid_timestamps_cannot_claim_sla_compliance(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            refresh(root=p,catalog=catalog(),loader=lambda _:rows(),now=AT)
            d=report(p)
            health_doc=health(p)
            wrong=copy.deepcopy(d)
            wrong["publicationLagMeasurementStatus"]="within_7_days"
            with self.assertRaisesRegex(LedgerError,"falsely certified"):
                verify_report(wrong,index(p),health_doc)
            wrong=copy.deepcopy(d)
            wrong["sources"][0]["publisherReleasePublishedAt"]=AT
            with self.assertRaisesRegex(LedgerError,"freshness was fabricated"):
                verify_report(wrong,index(p),health_doc)
            wrong=copy.deepcopy(d)
            wrong["sources"][0]["sourceReleaseToGitLagDays"]=0
            with self.assertRaisesRegex(LedgerError,"freshness was fabricated"):
                verify_report(wrong,index(p),health_doc)
            wrong=copy.deepcopy(d)
            wrong["sources"][0]["firstSeenInMirrorAt"]="2035-01-01T00:00:00Z"
            with self.assertRaisesRegex(LedgerError,"future or malformed"):
                verify_report(wrong,index(p),health_doc)
            wrong=copy.deepcopy(d)
            wrong["totals"]["sourceRecords"]=500000
            with self.assertRaisesRegex(LedgerError,"mirror counters differ"):
                verify_report(wrong,index(p),health_doc)

    def test_modified_partitions_or_synthetic_fingerprints_do_not_pass_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            refresh(root=p,catalog=catalog(),loader=lambda _:rows(),now=AT)
            d=report(p)
            fake=copy.deepcopy(d)
            fake["sources"][0]["mirrorFingerprint"]="0"*64
            with self.assertRaisesRegex(LedgerError,"per-source fingerprint"):
                verify_report(fake,index(p),health(p))
            stored=p/"publication/source-library/acquisition-ledger.json"
            stored.write_text(json.dumps(fake))
            with self.assertRaisesRegex(LedgerError,"per-source fingerprint"):
                verify(p)

    def test_source_fingerprint_rejects_duplicate_or_foreign_partition_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            refresh(root=p,catalog=catalog(),loader=lambda _:rows(),now=AT)
            source=index(p)["datasets"][0]
            clone=copy.deepcopy(source)
            clone["partitions"][0]["path"]="../another-dataset/2023.json"
            with self.assertRaisesRegex(LedgerError,"source partition digest"):
                source_fingerprint(clone)
            clone=copy.deepcopy(source)
            clone["partitions"].append(copy.deepcopy(clone["partitions"][0]))
            with self.assertRaisesRegex(LedgerError,"source partition digest"):
                source_fingerprint(clone)


if __name__=="__main__":
    unittest.main()
