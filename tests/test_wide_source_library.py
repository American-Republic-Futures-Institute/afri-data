"""DATA-22A original publisher wide-row boundaries, no column truncation."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.source_library import (
    BASE, MAX_ROW_BYTES, MAX_ROW_FIELDS, SourceLibraryError,
    pages, refresh, verify
)


def spec():
    return {
        "id":"treasury-wide-original-fixture",
        "title":"Original Treasury wide rows",
        "description":"Synthetic wide-field source fixture for publisher contract testing.",
        "domain":"public-finance","endpoint":"v2/accounting/od/debt_to_penny",
        "dateField":"record_date","preferredField":"balance_amt",
        "unit":"USD","maxRows":300,"sourcePage":
        "https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/"
    }


def row(width):
    return {
        "record_date":"2025-01-31","balance_amt":"-1234.005",
        **{f"source_field_{i:03d}":str(i) for i in range(width-2)}
    }


def fetch_from(value):
    return {"data":[value],"meta":{"total-count":1}}


class WideTreasurySourceTests(unittest.TestCase):
    def test_exact_161_and_256_original_fields_survive_source_fetch(self):
        for width in (161,256):
            with self.subTest(width=width),patch(
                    "tools.source_library.acquire",return_value=fetch_from(row(width))):
                got=pages(spec())
                self.assertEqual(len(got),1)
                self.assertEqual(got[0],row(width))
                self.assertEqual(len(got[0]),width)
                self.assertEqual(got[0]["balance_amt"],"-1234.005")

    def test_exceeding_reviewed_width_is_rejected_not_silently_trimmed(self):
        for width in (0,257,512):
            malformed=row(width) if width else {}
            with self.subTest(width=width),patch(
                    "tools.source_library.acquire",return_value=fetch_from(malformed)):
                with self.assertRaisesRegex(SourceLibraryError,"Malformed original publisher record"):
                    pages(spec())

    def test_192_kib_row_budget_and_reject_hostile_original_field_names(self):
        examples=[
            {**row(161),"unsafe-field!":"present"},
            {**row(161),"source_field_000":"x"*(MAX_ROW_BYTES+1)},
        ]
        for original in examples:
            with self.subTest(reason=next(reversed(original))),patch(
                    "tools.source_library.acquire",return_value=fetch_from(original)):
                with self.assertRaisesRegex(SourceLibraryError,"Malformed original publisher record"):
                    pages(spec())

    def test_git_archive_256_fields_replays_and_detects_digest_tampering(self):
        source=row(MAX_ROW_FIELDS)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            catalog={
                "schemaVersion":"1.0.0","publisher":"U.S. Treasury",
                "publisherApi":BASE,"refreshCadence":"weekly",
                "datasetClass":"source-native-unreviewed",
                "datasets":[spec()]
            }
            output=refresh(root=root,catalog=catalog,
                           loader=lambda _: [source.copy()],
                           now="2026-10-21T20:00:00Z")
            self.assertEqual(output["failedSources"],{})
            self.assertEqual(verify(root)["records"],1)
            index=json.loads((root/"publication/source-library/index.json").read_text())
            item=index["datasets"][0]
            annual=root/item["partitions"][0]["path"]
            doc=json.loads(annual.read_text())
            self.assertEqual(doc["records"][0],source)
            self.assertEqual(len(doc["records"][0]),MAX_ROW_FIELDS)
            annual.write_bytes(annual.read_bytes()+b"\\n")
            with self.assertRaisesRegex(SourceLibraryError,"digest mismatch"):
                verify(root)


if __name__=="__main__":
    unittest.main()
