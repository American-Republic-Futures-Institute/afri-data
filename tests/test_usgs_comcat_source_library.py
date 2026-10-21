"""Offline USGS ComCat annual original-source and mirror-replay adversarial tests."""
from __future__ import annotations
import copy
import csv
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError

from tools.source_library import BASE as TREASURY_BASE, SourceLibraryError, refresh, verify, validate_catalog
from tools.source_freshness import source_fingerprint
from tools.usgs_comcat_source_library import (
    FIELDS, MAX_CSV_BYTES, MAX_EVENTS_PER_YEAR, NoRedirects,
    OriginalUSGSRows, USGSUnavailable, source_url, parse_original,
    registry_sources, validate_registry, original_path, usgs_records,
    publisher_count, _no_redirect, verify_original_file, SOURCE_PAGE
)


def publisher(year="2024", suffix="a", **replacements):
    r = dict.fromkeys(FIELDS, "")
    r.update({
        "time": f"{year}-07-07T11:12:13.250Z",
        "latitude": "34.4000", "longitude": "-120.5000",
        "depth": "12.50", "mag": "6.40", "magType": "mww",
        "nst": "103", "gap": "24.0", "dmin": "1.240",
        "rms": "0.75", "net": "us", "id": f"us123456{suffix}",
        "updated": "2026-10-20T18:25:00.000Z",
        "place": "50 km SW of Fresno, California", "type": "earthquake",
        "horizontalError": "6", "depthError": "1.3", "magError": "0.04",
        "magNst": "99", "status": "reviewed",
        "locationSource": "us", "magSource": "us",
    })
    r.update(replacements)
    return r


def original(rows=None, *, field_names=FIELDS):
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=field_names, lineterminator="\n")
    writer.writeheader()
    for row in rows or [publisher(), publisher(suffix="b", place="Pacific, south of Hawaii")]:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


def government_spec(year=2024):
    return next(s for s in registry_sources()
                if s["id"] == f"usgs-comcat-m6-{year}")


def synthetic_catalog(*specs):
    return {"schemaVersion": "1.0.0",
            "publisher": "U.S. Department of the Treasury, Bureau of the Fiscal Service",
            "publisherApi": TREASURY_BASE,
            "refreshCadence": "weekly",
            "datasetClass": "source-native-unreviewed",
            "datasets": list(specs)}


class FakeResponse:
    def __init__(self, url, body, mime):
        self.url, self.body = url, io.BytesIO(body)
        self.status = 200
        self.headers = {"Content-Type": mime, "Content-Length": str(len(body))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self.url

    def read(self, n):
        return self.body.read(n)


class FakeOpener:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def open(self, request, timeout=40):
        url = request.full_url
        self.calls.append((url, timeout))
        return self.responses[url]


class USGSOriginalsTests(unittest.TestCase):
    def test_registered_27_historical_and_current_annual_government_originals(self):
        sources = registry_sources()
        self.assertEqual(len(sources), 27)
        self.assertEqual(sources[0]["releaseYear"], 2000)
        self.assertEqual(sources[-1]["releaseYear"], 2026)
        self.assertEqual(len({s["id"] for s in sources}), 27)
        self.assertTrue(all(s["provider"] == "usgs-comcat" for s in sources))
        self.assertTrue(all(s["sourcePage"] == SOURCE_PAGE for s in sources))
        self.assertTrue(all(s["dateBasis"] ==
            "usgs-earthquake-origin-utc-not-catalog-release" for s in sources))
        validate_catalog(synthetic_catalog(*sources))
        self.assertEqual(source_url(2024),
            "https://earthquake.usgs.gov/fdsnws/event/1/query?"
            "format=csv&starttime=2024-01-01&endtime=2025-01-01&"
            "minmagnitude=6&eventtype=earthquake&orderby=time-asc&"
            "limit=20000&nodata=404")

    def test_new_calendar_year_discovered_only_with_positive_official_count(self):
        date = datetime(2028, 8, 1, tzinfo=timezone.utc)
        self.assertEqual(len(registry_sources(discover=True, now=date,
                                              available=lambda y: y == 2027)), 28)
        self.assertEqual(len(registry_sources(discover=True, now=date,
                                              available=lambda y: False)), 27)
        self.assertEqual(len(registry_sources(discover=True, now=date,
                                              available=lambda y: True)), 29)

    def test_registration_fails_for_fake_source_year_or_magnitude(self):
        with self.assertRaisesRegex(USGSUnavailable, "Unapproved"):
            source_url(1999)
        with self.assertRaisesRegex(USGSUnavailable, "Unapproved"):
            source_url(2024.5)
        base = json.loads((Path(__file__).resolve().parents[1] /
                           "catalog/source-library/usgs-comcat.json").read_text())
        for key, val in [("catalogApi", "https://fake.example/"),
                         ("minimumMagnitude", "0"),
                         ("registeredThroughYear", 1999),
                         ("eventType", "quarry blast")]:
            bad = copy.deepcopy(base)
            bad[key] = val
            with self.subTest(key=key), self.assertRaises(USGSUnavailable):
                validate_registry(bad)

    def test_source_rows_retain_publisher_strings_without_aggregates(self):
        raw = original()
        rows = parse_original(raw, year=2024, expected_count=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["mag"], "6.40")
        self.assertEqual(rows[0]["latitude"], "34.4000")
        self.assertEqual(rows[0]["record_date"], "2024-07-07")
        self.assertEqual(rows[0]["time_basis"],
                         "usgs_origin_utc_not_catalog_publication")
        self.assertEqual(set(rows[0]), set(FIELDS) | {"record_date", "time_basis"})
        self.assertIn("Pacific, south of Hawaii", rows[1]["place"])
        with self.assertRaisesRegex(USGSUnavailable, "count"):
            parse_original(raw, year=2024, expected_count=3)

    def test_authoritative_csv_and_count_are_both_checked(self):
        source = government_spec()
        fake = original()
        opener = FakeOpener({
            source_url(2024): FakeResponse(source_url(2024), fake, "text/csv"),
            source_url(2024, count=True): FakeResponse(
                source_url(2024, count=True), b"2\n", "text/plain"),
        })
        self.assertEqual(_no_redirect(source_url(2024), accept="text/csv",
                                      maximum=MAX_CSV_BYTES, opener=opener), fake)
        self.assertEqual(publisher_count(2024, opener=opener), 2)
        self.assertEqual(len(opener.calls), 2)
        rows = usgs_records(source,
                            fetch=lambda url, accept, maximum: fake,
                            counter=lambda year: 2)
        self.assertIsInstance(rows, OriginalUSGSRows)
        self.assertEqual(rows.original_csv, fake)
        with self.assertRaisesRegex(USGSUnavailable, "count"):
            usgs_records(source, fetch=lambda url, accept, maximum: fake,
                         counter=lambda year: 3)

    def test_official_host_redirect_or_external_query_rejected(self):
        request_url = source_url(2024)
        with self.assertRaisesRegex(USGSUnavailable, "allowlist"):
            _no_redirect(request_url + "&callback=exfil", accept="text/csv",
                         maximum=MAX_CSV_BYTES, opener=FakeOpener({}))
        handler = NoRedirects()
        with self.assertRaisesRegex(USGSUnavailable, "redirect"):
            handler.redirect_request(None, None, 302, "moved", None,
                                     "https://example.org/earthquakes.csv")

    def test_unexpected_mime_and_url_rejected(self):
        url = source_url(2024)
        opener = FakeOpener({url: FakeResponse(url, original(), "text/html")})
        with self.assertRaisesRegex(USGSUnavailable, "MIME"):
            _no_redirect(url, accept="text/csv", maximum=MAX_CSV_BYTES,
                         opener=opener)

    def test_bad_count_metadata_is_not_treated_as_an_original_record(self):
        url = source_url(2024, count=True)
        for content in [b"20000", b"-2", b"<html>2</html>", b"NaN", b"999999"]:
            opener = FakeOpener({url: FakeResponse(url, content, "text/plain")})
            with self.subTest(body=content), self.assertRaises(USGSUnavailable):
                publisher_count(2024, opener=opener)

    def test_year_identity_and_event_field_failures(self):
        mutations = {
            "duplicate event": [publisher(), publisher()],
            "off-period event": [publisher(year="2025")],
            "other event class": [publisher(type="quarry blast")],
            "invalid depth": [publisher(depth="NaN")],
            "invalid latitude": [publisher(latitude="91")],
            "magnitude below source filter": [publisher(mag="5.99")],
            "unknown status": [publisher(status="unknown")],
            "absent identity": [publisher(id="")],
            "not UTC": [publisher(time="2024-07-07T11:12:13-04:00")],
            "invalid updated time": [publisher(updated="yesterday")],
            "very long comment": [publisher(place="A" * 6000)],
        }
        for why, data in mutations.items():
            with self.subTest(why=why), self.assertRaises(USGSUnavailable):
                parse_original(original(data), year=2024)

    def test_official_header_drift_is_not_inferred_or_silently_dropped(self):
        for head in (FIELDS[:-1], (*FIELDS, "exfiltrated"), tuple(FIELDS[:-1]) + ("time",)):
            with self.subTest(head=head), self.assertRaises(USGSUnavailable):
                parse_original(original([publisher()], field_names=head),
                               year=2024)
        with self.assertRaises(USGSUnavailable):
            parse_original(b"invalid", year=2024)
        with self.assertRaises(USGSUnavailable):
            parse_original(b"x" * (MAX_CSV_BYTES + 1), year=2024)

    def test_full_source_library_archive_replay_and_hash_tamper_rejection(self):
        source = government_spec()
        csv_bytes = original()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            catalog = synthetic_catalog(source)
            loader = lambda _: OriginalUSGSRows(
                parse_original(csv_bytes, year=2024), csv_bytes)
            result = refresh(root=root, catalog=catalog, loader=loader,
                             now="2026-10-21T15:00:00Z")
            self.assertEqual(result["datasets"], 1)
            self.assertEqual(result["records"], 2)
            self.assertEqual(result["failedSources"], {})
            self.assertEqual(verify(root)["records"], 2)
            index = json.loads((root /
                "publication/source-library/index.json").read_text())
            entry = index["datasets"][0]
            self.assertEqual(entry["provider"], "usgs-comcat")
            self.assertEqual(entry["originalCsvSha256"], sha256(csv_bytes).hexdigest())
            self.assertEqual(entry["originalCsvPath"], original_path(entry["originalCsvSha256"]))
            self.assertEqual((root / entry["originalCsvPath"]).read_bytes(), csv_bytes)
            old_fp = source_fingerprint(entry)
            original_path_disk = root / entry["originalCsvPath"]
            original_path_disk.write_bytes(csv_bytes + b"modified")
            with self.assertRaises((SourceLibraryError, USGSUnavailable)):
                verify(root)
            original_path_disk.write_bytes(csv_bytes)
            record_path = root / entry["partitions"][0]["path"]
            record_path.write_bytes(record_path.read_bytes() + b"altered")
            with self.assertRaises(SourceLibraryError):
                verify(root)
            self.assertEqual(source_fingerprint(entry), old_fp)

    def test_changed_original_bytes_are_fingerprinted_even_if_source_rows_unchanged(self):
        source = government_spec()
        base = original()
        modified = base.replace(b"\n", b"\r\n")
        self.assertEqual(parse_original(base, year=2024),
                         parse_original(modified, year=2024))
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            catalog = synthetic_catalog(source)
            def get(data):
                return lambda _: OriginalUSGSRows(parse_original(data, year=2024), data)
            refresh(root=root, catalog=catalog, loader=get(base),
                    now="2026-10-21T15:00:00Z")
            index_file = root / "publication/source-library/index.json"
            before = json.loads(index_file.read_text())["datasets"][0]
            refresh(root=root, catalog=catalog, loader=get(modified),
                    now="2026-10-21T16:00:00Z")
            after = json.loads(index_file.read_text())["datasets"][0]
            self.assertNotEqual(before["originalCsvSha256"], after["originalCsvSha256"])
            self.assertNotEqual(source_fingerprint(before), source_fingerprint(after))
            report = json.loads((root /
                "publication/source-library/acquisition-ledger.json").read_text())
            self.assertEqual(report["totals"]["changedMirroredAtThisRefresh"], 1)
            self.assertEqual(report["originalSourceReleaseTimesVerified"], 0)


if __name__ == "__main__":
    unittest.main()
