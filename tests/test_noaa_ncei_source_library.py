"""Offline adversarial NOAA climate-division original-byte and weekly replay tests."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from tools.noaa_ncei_source_library import (
    BASE, README_URL, KINDS, MAX_ROWS, NOAAUnavailable, OriginalNOAARows,
    NoRedirects, discover_filenames, original_path, parse_original, parse_readme,
    registry_sources, source_url, validate_registry, noaa_records,
)
from tools.source_library import BASE as TREASURY_BASE, refresh, verify, validate_catalog
from tools.source_freshness import source_fingerprint


def registry():
    return json.loads((Path(__file__).resolve().parents[1] /
                       "catalog/source-library/noaa-ncei.json").read_text())


def synthetic_rows():
    return b"".join(
        (f"{state:02d}0102{year} " + " ".join(
            ["1.20", "3.14", "-99.99", "5.04", "2.00", "0.00",
             "1.31", "9.81", "0.45", "7.07", "3.32", "1.12"]) + "\n").encode("ascii")
        for year in range(1895, 2027) for state in range(1, 11))


def original_single():
    return (b"0101021895 1.20 3.14 -99.99 5.04 2.00 0.00 1.31 9.81 0.45 7.07 3.32 1.12\n"
            b"0101022026 1.22 2.33 -99.99 5.04 2.00 0.00 1.31 9.81 0.45 7.07 3.32 1.12\n")


def official_readme():
    return (b"NOAA NCEI nClimDiv divisional original data file README.\n"
            b"All precipitation and temperature observations are keyed by climate division.\n"
            b"Data begin in 1895 with twelve monthly reported data values.\n" + b" " * 110)


def listing():
    return ("<html><body>" + " ".join(
        f'<a href="climdiv-{kind}-v1.0.0-{date}">source</a>'
        for kind in KINDS for date in ("20260904", "20261006"))
        + ("<a href='https://attacker.example/climdiv-pcpndv-v1.0.0-20271006'>evil</a>" * 2)
        + "<div>Official NCEI files</div></body></html>").encode()


class MockResponse:
    status = 200
    def __init__(self, url, body, mime="text/plain"):
        self.url, self.body = url, body
        self.headers = {"Content-Type": mime, "Content-Length": str(len(body)),
                        "Last-Modified": "Tue, 06 Oct 2026 04:58:04 GMT"}
    def geturl(self): return self.url
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, n): return self.body[:n]


class MockOpener:
    def __init__(self, payloads): self.payloads, self.calls = payloads, []
    def open(self, req, timeout):
        self.calls.append(req.full_url)
        return self.payloads[req.full_url]


class NOAAOriginalTests(unittest.TestCase):
    def test_publisher_registry_creates_two_complete_division_series(self):
        validate_registry(registry())
        specs=registry_sources()
        self.assertEqual([s["id"] for s in specs],
                         ["noaa-ncei-climdiv-pcpndv", "noaa-ncei-climdiv-tmpcdv"])
        self.assertTrue(all(s["maxRows"] == MAX_ROWS for s in specs))
        self.assertTrue(all(s["dateField"] == "record_date" for s in specs))
        self.assertTrue(all("20261006" in s["endpoint"] for s in specs))

    def test_strict_original_directory_date_discovery(self):
        urls=discover_filenames(listing())
        self.assertEqual(urls["pcpndv"],"climdiv-pcpndv-v1.0.0-20261006")
        self.assertEqual(urls["tmpcdv"],"climdiv-tmpcdv-v1.0.0-20261006")
        self.assertEqual(len(registry_sources(discover=True,listing=listing())),2)
        for x in (b"<html><body></body></html>"+b"x"*100,
                  b"<html><body><a href='climdiv-pcpndv-v1.0.0-20261306'>x</a>"
                  b"<a href='climdiv-tmpcdv-v1.0.0-20261006'>x</a></body></html>"):
            with self.assertRaises(NOAAUnavailable):
                discover_filenames(x)

    def test_refuse_unsafe_source_filename_and_host(self):
        for val in ("climdiv-tmpcdv-v1.0.0-20261006",
                    "climdiv-pcpndv-v1.0.0-20261306",
                    "climdiv-pcpndv-v1.0.0-20261006?redirect=evil",
                    "https://evil.example/climdiv-pcpndv-v1.0.0-20261006"):
            with self.subTest(val=val), self.assertRaises((NOAAUnavailable,ValueError)):
                source_url("pcpndv",val)
        with self.assertRaises(NOAAUnavailable):
            NoRedirects().redirect_request(None,None,302,"Moved",None,"https://bad.example")

    def test_preserve_raw_month_tokens_no_imputation_or_fips_inference(self):
        rows=parse_original(original_single(),kind="pcpndv")
        self.assertEqual(rows[0]["record_date"],"1895-12-31")
        self.assertEqual(rows[0]["ncei_source_code"],"010102")
        self.assertEqual(rows[0]["month_01"],"1.20")
        self.assertEqual(rows[0]["month_03"],"-99.99")
        self.assertEqual(rows[0]["month_06"],"0.00")
        self.assertNotIn("state_fips",rows[0])
        self.assertEqual(len(rows),2)

    def test_decode_original_violations(self):
        original=original_single()
        mutations=[
            b"not NOAA"*100,
            original.replace(b"0101022026",b"0101021895"),
            original.replace(b"3.14",b"NaN"),
            original.replace(b"-99.99",b""),
            original.replace(b"0101022026",b"010102209"),
            original.replace(b"0101021895",b"0101021850"),
            original+b"not-a-row\n",
            original+b"a"*200,
        ]
        for raw in mutations:
            with self.subTest(raw=raw[:60]),self.assertRaises(NOAAUnavailable):
                parse_original(raw,kind="pcpndv")
        with self.assertRaises(NOAAUnavailable):
            parse_readme(b"x"*400)

    def test_end_to_end_official_response_preserves_publisher_readme_and_sha(self):
        original=synthetic_rows()
        spec=registry_sources()[0]
        self.assertGreater(len(original),100_000)
        def fetch(url, ceiling, mime=None):
            if url==README_URL:return official_readme(),None
            self.assertEqual(url,spec["endpoint"])
            return original,"Tue, 06 Oct 2026 04:58:04 GMT"
        rows=noaa_records(spec,fetch=fetch)
        self.assertIsInstance(rows,OriginalNOAARows)
        self.assertEqual(rows.original_text,original)
        self.assertEqual(rows.original_readme,official_readme())
        self.assertGreater(len(rows),1000)
        self.assertEqual(rows.source_last_modified,"Tue, 06 Oct 2026 04:58:04 GMT")
        self.assertEqual(rows[-1]["record_date"],"2026-12-31")

    def test_noaa_library_archive_replay_source_hash_and_tampering(self):
        spec=registry_sources()[0]
        original=synthetic_rows()
        readme=official_readme()
        def loader(x):
            return OriginalNOAARows(parse_original(original,kind=x["sourceKind"],
                          min_rows=1000),original,readme,
                          x["endpoint"][len(BASE):],None)
        treasury={
            "schemaVersion":"1.0.0","publisher":"U.S. Treasury",
            "publisherApi":TREASURY_BASE,"refreshCadence":"weekly",
            "datasetClass":"source-native-unreviewed","datasets":[spec]}
        validate_catalog(treasury)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            catalog_path=root/"catalog/source-library"
            catalog_path.mkdir(parents=True)
            (catalog_path/"noaa-ncei.json").write_text(json.dumps(registry()))
            result=refresh(root=root,catalog=treasury,loader=loader,
                     now="2026-10-21T17:00:00Z")
            self.assertEqual(result["succeeded"],1)
            self.assertEqual(verify(root)["datasets"],1)
            index=json.loads((root/"publication/source-library/index.json").read_text())
            record=index["datasets"][0]
            self.assertEqual(record["provider"],"noaa-ncei")
            self.assertEqual(record["publisherPublishedAt"],None)
            self.assertEqual(record["sourceFilename"],"climdiv-pcpndv-v1.0.0-20261006")
            self.assertEqual(record["rowCount"],1320)
            self.assertEqual(len(record["partitions"]),132)
            self.assertEqual(record["partitions"][0]["year"],1895)
            self.assertEqual(record["partitions"][-1]["year"],2026)
            fingerprint=source_fingerprint(record)
            self.assertEqual(len(fingerprint),64)
            original_pathname=root/record["originalTxtPath"]
            raw=original_pathname.read_bytes()
            original_pathname.write_bytes(raw+b"corrupt")
            with self.assertRaises((ValueError,RuntimeError)):
                verify(root)
            original_pathname.write_bytes(raw)
            doc_path=root/record["partitions"][0]["path"]
            doc_path.write_bytes(doc_path.read_bytes()+b"\n")
            with self.assertRaises((ValueError,RuntimeError)):
                verify(root)


if __name__=="__main__":
    unittest.main()
