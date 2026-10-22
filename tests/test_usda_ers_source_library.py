"""Offline adversarial USDA ERS original full-stream replay and provenance tests."""
import csv
from functools import lru_cache
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.usda_ers_source_library import (
    DATE_BASIS, EXPECTED_CSV, HEADERS, ORIGINAL_UNIT, RELEASE_DATE,
    RELEASE_TEXT, SERIES, SOURCE_LABEL, SOURCE_PAGE, SOURCE_URL,
    STATES, UNIT, MAX_SELECTED, USDAUnavailable, OriginalUSDARows,
    ers_records, original_path, parse_original, registry_sources,
    validate_registry, verify_original_file,
)
from tools.source_freshness import source_fingerprint
from tools.probe_usda_ers_archive import USDAProbeError


def publisher_row(year, state, dataset):
    spec=SERIES[dataset]
    return [str(year),state,spec["prefix"]+state+spec["suffix"],
            spec["label"],spec["part1"],spec["part2"],
            "-100" if state=="AK" else "123.00",ORIGINAL_UNIT,
            RELEASE_TEXT,SOURCE_LABEL,"97.089"]


def zipped(rows):
    out=StringIO(newline="")
    writer=csv.writer(out,lineterminator="\r\n")
    writer.writerow(HEADERS)
    writer.writerows(rows)
    contents=out.getvalue().encode("cp1252")
    buf=BytesIO()
    with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as archive:
        archive.writestr(EXPECTED_CSV,contents)
    return buf.getvalue()


@lru_cache(maxsize=1)
def complete_fixture():
    rows=[]
    for state in sorted(STATES):
        years=(range(1910,2027) if state=="US" else
               range(1960 if state in ("AK","HI") else 1949,2026))
        for year in years:
            for name in SERIES:
                rows.append(publisher_row(year,state,name))
    filler=["2025","US","OTHER_SOURCE","Other", "Other", "Other",
            "0","$1,000",RELEASE_TEXT,SOURCE_LABEL,"97.089"]
    rows.extend([filler]*400000)
    return zipped(rows)


class USDAERSOriginalsTests(unittest.TestCase):
    def test_registry_has_exact_publisher_release_variables(self):
        cfg=json.loads((Path(__file__).resolve().parents[1]/
                         "catalog/source-library/usda-ers.json").read_text())
        validate_registry(cfg)
        specs=registry_sources()
        self.assertEqual({x["id"] for x in specs},set(SERIES))
        self.assertTrue(all(x["unit"]==UNIT and x["endpoint"]==SOURCE_URL and
                            x["sourcePage"]==SOURCE_PAGE and
                            x["dateBasis"]==DATE_BASIS and x["releaseDate"]==RELEASE_DATE
                            for x in specs))
        modified=json.loads(json.dumps(cfg))
        modified["series"][0]["variableDescription"]="Adjusted net farm income"
        with self.assertRaises(USDAProbeError):
            validate_registry(modified)

    def test_stream_all_original_member_and_keep_11_raw_cells_without_coercion(self):
        source=complete_fixture()
        for series in SERIES:
            with self.subTest(series=series):
                rows=parse_original(source,dataset=series)
                self.assertIsInstance(rows,OriginalUSDARows)
                self.assertEqual(len(rows),3945)
                self.assertEqual(len({r["State"] for r in rows}),51)
                self.assertEqual(len(rows.original_zip),len(source))
                self.assertEqual(len(rows.member_crc32),8)
                self.assertTrue(all(r["source_original_sha256"]==sha256(source).hexdigest()
                                    for r in rows))
                alaska=next(r for r in rows if r["State"]=="AK" and r["Year"]=="2025")
                self.assertEqual(alaska["Amount"],"-100")
                self.assertEqual(alaska["unit_desc"],ORIGINAL_UNIT)
                self.assertEqual(alaska["PublicationDate"],RELEASE_TEXT)
                self.assertEqual(alaska["record_date"],"2025-12-31")
                self.assertFalse(any("state_fips" in r for r in rows))

    def test_exact_original_zip_shas_and_csv_crc_replay(self):
        source=complete_fixture()
        rows=parse_original(source,dataset="usda-ers-net-farm-income")
        with tempfile.TemporaryDirectory() as tmp:
            original_sha=sha256(source).hexdigest()
            path=Path(tmp)/original_path(original_sha)
            path.parent.mkdir(parents=True)
            path.write_bytes(source)
            entry={
                "id":"usda-ers-net-farm-income",
                "provider":"usda-ers",
                "sourceVariableDescription":"Net farm income",
                "endpoint":SOURCE_URL,"sourcePage":SOURCE_PAGE,
                "dateBasis":DATE_BASIS,"releaseDate":RELEASE_DATE,"unit":UNIT,
                "originalZipPath":original_path(original_sha),
                "originalZipSha256":original_sha,"originalZipBytes":len(source),
                "originalMemberCrc32":rows.member_crc32,
                "originalMemberBytes":rows.member_bytes,
                "rowCount":len(rows),
                "partitions":[{
                    "path":"publication/source-library/data/usda-ers-net-farm-income/2025.json",
                    "sha256":"a"*64,"bytes":200,"rows":len(rows)
                }],
            }
            self.assertEqual(len(verify_original_file(tmp,entry)),len(rows))
            self.assertEqual(len(source_fingerprint(entry)),64)
            altered={**entry,"originalMemberCrc32":"00000000"}
            with self.assertRaises(USDAProbeError):
                verify_original_file(tmp,altered)
            path.write_bytes(source+b"tampered")
            with self.assertRaises(USDAProbeError):
                verify_original_file(tmp,entry)

    def test_corrupt_or_identity_swapped_publisher_zip_denied(self):
        dataset="usda-ers-net-farm-income"
        malformed=publisher_row(2025,"VA",dataset)
        malformed[7]="US dollars converted"
        with self.assertRaises(USDAProbeError):
            parse_original(zipped([malformed]),dataset=dataset)
        duplicated=publisher_row(2025,"VA",dataset)
        with self.assertRaises(USDAProbeError):
            parse_original(zipped([duplicated,duplicated]),dataset=dataset)
        unknown=publisher_row(2025,"VA",dataset)
        unknown[2]="FIAZZNTFI--P"
        with self.assertRaises(USDAProbeError):
            parse_original(zipped([unknown]),dataset=dataset)
        with self.assertRaises(USDAProbeError):
            parse_original(b"PK\x03\x04"+b"x"*500,dataset=dataset)
        with self.assertRaises(USDAProbeError):
            original_path("../../malicious.zip")


    def test_source_library_git_partition_catalog_ledger_and_original_zip_replay(self):
        from tools.source_library import BASE as TREASURY_BASE, refresh, verify
        source=complete_fixture()
        docs=registry_sources()
        catalog={"schemaVersion":"1.0.0","publisher":"U.S. Treasury",
                 "publisherApi":TREASURY_BASE,"refreshCadence":"weekly",
                 "datasetClass":"source-native-unreviewed","datasets":docs}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            result=refresh(root=root,catalog=catalog,
                loader=lambda item: parse_original(source,dataset=item["id"]),
                now="2026-10-21T20:00:00Z")
            self.assertEqual(result["datasets"],2)
            self.assertEqual(result["records"],7890)
            self.assertFalse(result["failedSources"])
            self.assertEqual(verify(root)["datasets"],2)
            idx=json.loads((root/"publication/source-library/index.json").read_text())
            self.assertEqual({x["id"] for x in idx["datasets"]},set(SERIES))
            self.assertTrue(all(len(x["partitions"])==117 for x in idx["datasets"]))
            ledger=json.loads((root/"publication/source-library/acquisition-ledger.json").read_text())
            self.assertEqual(ledger["totals"]["mirrored"],2)
            self.assertEqual(ledger["totals"]["sourceRecords"],7890)
            self.assertEqual(ledger["totals"]["registeredNotAcquired"],0)
            self.assertEqual(ledger["providers"]["usda-ers"]["succeeded"],2)
            manifest=json.loads((root/"publication/source-library/catalog/manifest.json").read_text())
            self.assertEqual(manifest["datasetCount"],2)
            retained=root/idx["datasets"][0]["originalZipPath"]
            self.assertEqual(retained.read_bytes(),source)
            retained.write_bytes(source+b"tampered")
            with self.assertRaises((ValueError,RuntimeError)):
                verify(root)


if __name__=="__main__":
    unittest.main()
