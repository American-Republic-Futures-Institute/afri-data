"""DATA-19A bounded source descriptors, integrity and no-truncation tests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.source_catalog_pages import (
    PAGE_SIZE, MAX_DATASETS, MANIFEST, MAX_PAGE_BYTES, MAX_MANIFEST_BYTES,
    CatalogPagesError, generated, write_pages, verify_pages)
from tools.source_library import canonical, validate_catalog, verify, refresh, BASE


def original(key):
    return {"id":key,"title":"Synthetic original Treasury source",
            "description":"Synthetic only: no claims about federal spending or measured values.",
            "domain":"public-finance","endpoint":"v2/accounting/od/debt_to_penny",
            "dateField":"record_date","preferredField":"balance_amt",
            "unit":"USD","maxRows":1000,
            "sourcePage":"https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/"}


def catalog(count):
    return {"schemaVersion":"1.0.0","publisher":"U.S. Treasury",
            "publisherApi":BASE,"refreshCadence":"weekly",
            "datasetClass":"source-native-unreviewed",
            "datasets":[original(f"treasury-page-{i:05d}") for i in range(count)]}


def published(count):
    datasets=[]
    for row in catalog(count)["datasets"]:
        x={"id":row["id"],"title":row["title"],"description":row["description"],
           "publisher":"U.S. Treasury","endpoint":"https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny",
           "sourcePage":row["sourcePage"],"dateField":"record_date",
           "preferredField":"balance_amt","refreshCadence":"weekly",
           "dateBasis":"original-publisher-record-date","sourceClass":"source-native-unreviewed",
           "unit":"USD","rowCount":1,"firstDate":"2024-12-31","latestDate":"2024-12-31",
           "partitions":[{"year":2024,"path":f"publication/source-library/data/{row['id']}/2024.json",
                          "sha256":"a"*64,"bytes":143,"rows":1,
                          "firstDate":"2024-12-31","lastDate":"2024-12-31"}]}
        datasets.append(x)
    return {"schemaVersion":"1.0.0","sourceClass":"automated-official-source-copy",
            "refreshCadence":"weekly","sourceSystem":"Original fixture",
            "datasets":datasets}


class CatalogPagesTests(unittest.TestCase):
    def test_501_descriptors_are_not_truncated_and_registry_exceeds_old_300_limit(self):
        validate_catalog(catalog(501))
        index=published(501)
        files=generated(index)
        manifest=json.loads(files[str(MANIFEST)])
        self.assertEqual(manifest["datasetCount"],501)
        self.assertEqual(len(manifest["pages"]),(501+PAGE_SIZE-1)//PAGE_SIZE)
        self.assertEqual(sum(page["count"] for page in manifest["pages"]),501)
        self.assertLessEqual(len(files[str(MANIFEST)]),MAX_MANIFEST_BYTES)
        self.assertTrue(all(len(payload)<=MAX_PAGE_BYTES for payload in files.values()
                            if payload is not files[str(MANIFEST)]))
        self.assertEqual(manifest["indexSha256"],__import__("hashlib").sha256(canonical(index)).hexdigest())
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(write_pages(tmp,index)["descriptors"],501)
            self.assertEqual(verify_pages(tmp,index)["datasets"],501)
            target=Path(tmp)/manifest["pages"][4]["path"]
            target.write_bytes(target.read_bytes()+b" ")
            with self.assertRaisesRegex(CatalogPagesError,"digest mismatch"):
                verify_pages(tmp,index)

    def test_manifest_tampering_and_catalog_shrink_fail_closed(self):
        index=published(71)
        with tempfile.TemporaryDirectory() as tmp:
            write_pages(tmp,index)
            path=Path(tmp)/MANIFEST
            assert path.exists()
            path.write_bytes(path.read_bytes().replace(b'"datasetCount":71',b'"datasetCount":72'))
            with self.assertRaisesRegex(CatalogPagesError,"digest mismatch"):
                verify_pages(tmp,index)
            write_pages(tmp,index)
            shrunken=copy.deepcopy(index)
            shrunken["datasets"].pop()
            with self.assertRaisesRegex(CatalogPagesError,"digest mismatch"):
                verify_pages(tmp,shrunken)

    def test_duplicate_unsorted_and_unsupported_descriptor_volumes_not_admitted(self):
        index=published(3)
        index["datasets"]=[index["datasets"][1],index["datasets"][0],index["datasets"][2]]
        with self.assertRaisesRegex(CatalogPagesError,"sorted"):
            generated(index)
        index=published(3)
        index["datasets"][2]["id"]=index["datasets"][1]["id"]
        with self.assertRaisesRegex(CatalogPagesError,"unique"):
            generated(index)
        index=published(1)
        index["datasets"]=index["datasets"]*(MAX_DATASETS+1)
        with self.assertRaisesRegex(CatalogPagesError,"excessive"):
            generated(index)

    def test_refresh_emits_and_verifies_current_catalog_pages_from_identical_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=catalog(1)
            records=[{"record_date":"2024-12-31","balance_amt":"124.00"}]
            result=refresh(root=root,catalog=source,loader=lambda _:copy.deepcopy(records))
            self.assertEqual(result["failedSources"],{})
            self.assertTrue((root/MANIFEST).is_file())
            manifest=json.loads((root/MANIFEST).read_text())
            self.assertEqual(manifest["datasetCount"],1)
            self.assertEqual(verify(root)["records"],1)
            page=root/manifest["pages"][0]["path"]
            page.write_bytes(b"tamper")
            with self.assertRaisesRegex(CatalogPagesError,"digest mismatch"):
                verify(root)


if __name__=="__main__":
    unittest.main()
