"""DATA-22 audit verifies complete signed-partition field distribution."""
import json
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from tools.audit_source_field_widths import FieldInventoryError, audit, publisher_family


def raw(obj):
    return (json.dumps(obj,sort_keys=True,separators=(",",":"))+"\n").encode()


def example(root):
    key="treasury-fixture-wide"
    row={"record_date":"2025-12-31"}
    row.update({f"source_col_{i:03d}":str(i) for i in range(255)})
    path="publication/source-library/data/"+key+"/2025.json"
    blob=raw({"schemaVersion":"1.0.0","sourceClass":"official-raw-values",
              "datasetId":key,"dateField":"record_date","year":2025,"records":[row]})
    target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(blob)
    meta={"schemaVersion":"1.0.0","sourceClass":"automated-official-source-copy",
          "datasets":[{"id":key,"provider":"treasury-fiscaldata","rowCount":1,
                       "partitions":[{"path":path,"bytes":len(blob),
                                      "sha256":sha256(blob).hexdigest(),"rows":1}]}]}
    base=root/"publication/source-library"
    (base/"index.json").write_bytes(raw(meta))
    (base/"acquisition-ledger.json").write_bytes(raw({
        "checkedAt":"2026-10-21T20:00:00Z",
        "totals":{"mirrored":1,"sourceRecords":1,"sourcePartitions":1}}))
    return target


class SourceFieldWidthsTests(unittest.TestCase):
    def test_one_256_column_original_partition_is_sha_verified_not_truncated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            original=example(root)
            result=audit(root)
            self.assertEqual(result["originalDatasets"],1)
            self.assertEqual(result["originalRecords"],1)
            self.assertEqual(result["shaVerifiedPartitions"],1)
            self.assertEqual(result["maxObservedFields"],256)
            self.assertEqual(result["rowsWithMoreThan160Fields"],1)
            self.assertEqual(result["rowFieldDistribution"]["256"],1)
            self.assertFalse(result["changesPublished"])
            original.write_bytes(original.read_bytes()+b"tampered")
            with self.assertRaises(FieldInventoryError):
                audit(root)

    def test_legacy_source_family_classification_is_not_mislabeled_treasury(self):
        expected={
            "bls-qcew-all-industry": "bls-qcew",
            "cdc-places-county-obesity-2024": "cdc-places",
            "census-acs5-b19013-2024": "census-acs5",
            "bea-state-gdp-nominal": "bea-regional",
            "treasury-debt-to-penny": "treasury-fiscaldata",
            "eia-seds-total-consumption": "eia-seds",
            "usda-ers-net-farm-income": "usda-ers",
        }
        for key,provider in expected.items():
            with self.subTest(dataset=key):
                self.assertEqual(publisher_family({"id":key}),provider)
        with self.assertRaises(FieldInventoryError):
            publisher_family({"id":"nondescript-invented"})
        with self.assertRaises(FieldInventoryError):
            publisher_family({"id":"bls-qcew-all-industry","provider":"treasury-fiscaldata"})

    def test_source_ledger_count_mismatch_blocks_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);example(root)
            ledger=root/"publication/source-library/acquisition-ledger.json"
            doc=json.loads(ledger.read_bytes())
            doc["totals"]["sourceRecords"]=0
            ledger.write_bytes(raw(doc))
            with self.assertRaisesRegex(FieldInventoryError,"disagrees"):
                audit(root)


if __name__=="__main__":
    unittest.main()
