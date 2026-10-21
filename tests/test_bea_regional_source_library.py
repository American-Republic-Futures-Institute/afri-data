"""DATA-18 independent offline BEA ZIP and source partition replay regression."""
from __future__ import annotations
import copy
import csv
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

from tools.bea_regional_source_library import (
    BASE, PAGE, STATES, BEAUnavailable, SERIES, bea_records,
    member_bytes, parse_member, registry_sources, validate_registry,
)
from tools.source_library import ROOT, CATALOG, canonical, digest, refresh, validate_catalog, verify
from tools.source_freshness import source_fingerprint


def make_original(table, line="1", years=(2023, 2024), override=None,
                  missing_state=None, duplicate=False):
    fields = ["GeoFIPS", "GeoName", "Region", "TableName", "LineCode",
              "IndustryClassification", "Description", "Unit"] + [str(y) for y in years]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    data = []
    for fips in sorted(STATES):
        if fips == missing_state:
            continue
        row = {
            "GeoFIPS": fips + "000", "GeoName": "Source state " + fips,
            "Region": "1", "TableName": table, "LineCode": line,
            "IndustryClassification": "ALL", "Description": "All industries",
            "Unit": "Millions of current dollars",
            str(years[0]): "(D)" if fips == "01" else "1,234.50",
            str(years[-1]): "2,345.67",
        }
        if override and fips == "01":
            row[str(years[-1])] = override
        data.append(row)
    if duplicate:
        data.append(copy.deepcopy(data[0]))
    data.extend([{"GeoFIPS": "00000", "GeoName": "United States",
                  "Region": "0", "TableName": table, "LineCode": line,
                  "IndustryClassification": "ALL", "Description": "National total",
                  "Unit": "Millions of current dollars",
                  **{str(y): "999999" for y in years}},
                 {"GeoFIPS": "01000", "GeoName": "Alabama",
                  "Region": "1", "TableName": table, "LineCode": "12",
                  "IndustryClassification": "OTHER", "Description": "Other line",
                  "Unit": "Millions of current dollars",
                  **{str(y): "999" for y in years}}])
    writer.writerows(data)
    return buffer.getvalue().encode("utf-8")


def make_zip(archive, payloads=None, **opts):
    if payloads is None:
        payloads = {
            "SAGDP2N": make_original("SAGDP2N", **opts),
            "SAGDP9N": make_original("SAGDP9N", **opts),
        } if archive == "SAGDP" else {
            "SAINC1": make_original("SAINC1", **opts)}
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as z:
        for name, content in payloads.items():
            z.writestr(f"{name}__ALL_AREAS_2023_2024.csv", content)
    return buffer.getvalue()


def inputs(**opts):
    return {"SAGDP": make_zip("SAGDP", **opts),
            "SAINC": make_zip("SAINC", **opts)}


class BEAOriginalTests(unittest.TestCase):
    def test_registry_is_only_four_official_dataset_line_ids(self):
        datasets = registry_sources()
        self.assertEqual(set(x["id"] for x in datasets), set(SERIES))
        for spec in datasets:
            self.assertEqual(spec["endpoint"], BASE + spec["archive"] + ".zip")
            self.assertEqual(spec["sourcePage"], PAGE)
            self.assertEqual(spec["preferredField"], "value")
            self.assertEqual(spec["dateBasis"], "bea-annual-reference-year-index")
        treasury = json.loads((ROOT / CATALOG).read_text("utf-8"))
        validate_catalog({**treasury, "datasets": treasury["datasets"] + datasets})

    def test_nonpublishers_and_substituted_series_are_rejected(self):
        inputs_ = registry_sources()
        treasury = json.loads((ROOT / CATALOG).read_text("utf-8"))
        for field, value in [
            ("endpoint", "https://evil.example/regional/zip/SAGDP.zip"),
            ("endpoint", BASE + "../../SAGDP.zip"),
            ("sourcePage", "https://evil.example"),
            ("table", "SAGDP11N"),
            ("dateBasis", "date_of_publication"),
            ("preferredField", "made_up_average"),
        ]:
            sources = copy.deepcopy(inputs_)
            sources[0][field] = value
            with self.subTest(field=field, value=value), self.assertRaisesRegex(
                    ValueError, "Unapproved BEA|Invalid source metric"):
                validate_catalog({**treasury, "datasets": sources})
        with self.assertRaises(BEAUnavailable):
            member_bytes(b"<html>fake ZIP</html>", archive="SAGDP", table="SAGDP2N")

    def test_full_publisher_strings_geography_and_archive_replay(self):
        archive = make_zip("SAGDP")
        f = lambda _name: archive
        dataset = next(s for s in registry_sources() if s["id"] == "bea-state-gdp-nominal")
        rows = bea_records(dataset, fetch=f, now=__import__("datetime").datetime(2026, 10, 21))
        self.assertEqual(len(rows), 2 * len(STATES))
        self.assertEqual(len(STATES), 51)
        row = next(x for x in rows if x["GeoFIPS"] == "01000" and
                   x["record_date"] == "2023-12-31")
        self.assertEqual(row["value"], "(D)")
        self.assertEqual(row["time_basis"], "bea_annual_reference_year_not_release_date")
        self.assertEqual(row["TableName"], "SAGDP2N")
        self.assertEqual(row["LineCode"], "1")
        self.assertEqual(row["source_archive_sha256"], sha256(archive).hexdigest())
        self.assertRegex(row["source_original_sha256"], "^[a-f0-9]{64}$")
        row_2024 = next(x for x in rows if x["GeoFIPS"] == "01000"
                        and x["record_date"] == "2024-12-31")
        self.assertEqual(row_2024["value"], "2,345.67")
        self.assertEqual(row_2024["value_year_column"], "2024")
        self.assertEqual(rows, bea_records(dataset, fetch=f,
                                           now=__import__("datetime").datetime(2026, 10, 21)))

    def test_four_series_isolated_by_exact_bea_table_and_line(self):
        bundles = inputs()
        for descriptor in registry_sources():
            with self.subTest(id=descriptor["id"]):
                rows = bea_records(descriptor, fetch=lambda a: bundles[a])
                self.assertEqual(len(rows), 102)
                self.assertTrue(all(x["TableName"] == descriptor["table"] and
                                    x["LineCode"] == descriptor["lineCode"]
                                    for x in rows))

    def test_missing_state_and_duplicate_are_not_silently_published(self):
        for tweak in [{"missing_state": "56"}, {"duplicate": True}]:
            src = make_original("SAGDP2N", **tweak)
            with self.subTest(tweak=tweak), self.assertRaisesRegex(
                    BEAUnavailable, "incomplete|duplicate"):
                parse_member(src, table="SAGDP2N", line_code="1",
                             member="SAGDP2N__ALL_AREAS_2023_2024.csv",
                             archive_sha="a" * 64)
        with self.assertRaisesRegex(BEAUnavailable, "Unrecognized publisher"):
            src = make_original("SAGDP2N", override="=cmd|'evil'")
            parse_member(src, table="SAGDP2N", line_code="1",
                         member="SAGDP2N__ALL_AREAS_2023_2024.csv",
                         archive_sha="a" * 64)

    def test_wrong_zip_member_rejected_without_falling_back_to_similar_table(self):
        with self.assertRaisesRegex(BEAUnavailable, "absent|ambiguous"):
            member_bytes(make_zip("SAGDP", {"SAGDP3N": make_original("SAGDP3N")}),
                         archive="SAGDP", table="SAGDP2N")
        with self.assertRaisesRegex(BEAUnavailable, "unsafe"):
            archive = make_zip("SAGDP", {"../SAGDP2N__ALL_AREAS_2023_2024.csv":
                                           make_original("SAGDP2N")})
            member_bytes(archive, archive="SAGDP", table="SAGDP2N")

    def test_revisions_have_verified_partition_hashes_and_remain_distinct(self):
        registry = json.loads((ROOT / CATALOG).read_text("utf-8"))
        spec = next(s for s in registry_sources() if s["id"] == "bea-state-gdp-nominal")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archives = {"SAGDP": make_zip("SAGDP")}
            catalog = {**registry, "datasets": [spec]}
            load = lambda _: bea_records(spec, fetch=lambda a: archives[a])
            first = refresh(root=root, catalog=catalog, loader=load,
                            now="2026-10-21T00:00:00Z")
            self.assertEqual(first["failedSources"], {})
            self.assertEqual(first["datasets"], 1)
            self.assertEqual(first["records"], 102)
            yearpath = root / "publication/source-library/data/bea-state-gdp-nominal/2024.json"
            before = yearpath.read_bytes()
            first_index = json.loads((root / "publication/source-library/index.json").read_text())
            self.assertEqual(verify(root)["records"], 102)
            self.assertEqual(first_index["datasets"][0]["partitions"][1]["sha256"],
                             digest(before))
            archives["SAGDP"] = make_zip("SAGDP", override="2,345.68")
            second = refresh(root=root, catalog=catalog, loader=load,
                             now="2026-10-21T01:00:00Z")
            self.assertEqual(second["failedSources"], {})
            self.assertNotEqual(before, yearpath.read_bytes())
            updated = json.loads((root / "publication/source-library/index.json").read_text())
            self.assertNotEqual(source_fingerprint(first_index["datasets"][0]),
                                source_fingerprint(updated["datasets"][0]))
            self.assertEqual(verify(root)["records"], 102)
            yearpath.write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                verify(root)


if __name__ == "__main__":
    unittest.main()
