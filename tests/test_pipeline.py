"""Offline regression and provenance tests; no government endpoint required in CI."""
from __future__ import annotations
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import shapefile
from pipelines.census_state_population import (
    FIPS, YEARS, ROOT, parse_population, parse_geometry,
    build_release, fetch_source, RELEASE_PATH
)
from tools.validate import validate_publication, validate_catalog


def fixture_csv():
    buff = io.StringIO()
    columns = ["SUMLEV", "STATE", "NAME"] + [f"POPESTIMATE{y}" for y in YEARS]
    writer = csv.DictWriter(buff, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for pos, code in enumerate(sorted(FIPS)):
        row = {"SUMLEV": "040", "STATE": code, "NAME": "Example " + code}
        for y in YEARS:
            row[f"POPESTIMATE{y}"] = str(100_000 + pos * 10_000 + y - 2020)
        writer.writerow(row)
    return buff.getvalue().encode("utf-8")


def fixture_zip(include_all=True):
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    writer = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON)
    writer.field("GEOID", "C", size=2)
    writer.field("NAME", "C", size=40)
    codes = sorted(FIPS) if include_all else sorted(FIPS)[:-1]
    for index, fips in enumerate(codes):
        # Synthetic squares for testing mechanics ONLY; never published as data.
        lon = -160 + (index % 13) * 4
        lat = 20 + (index // 13) * 6
        writer.poly([[
            [lon, lat], [lon, lat + 2], [lon + 2, lat + 2],
            [lon + 2, lat], [lon, lat]
        ]])
        writer.record(fips, "Example " + fips)
    writer.close()
    buff = io.BytesIO()
    with zipfile.ZipFile(buff, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for extension, contents in (("shp", shp), ("shx", shx), ("dbf", dbf)):
            archive.writestr("cb_2025_us_state_20m." + extension, contents.getvalue())
    return buff.getvalue()


URLS = (
    "https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/state/totals/NST-EST2025-ALLDATA.csv",
    "https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_state_20m.zip"
)


class PublicationTests(unittest.TestCase):
    def test_catalog_referential_integrity(self):
        counts = validate_catalog()
        self.assertGreaterEqual(counts["publishers"], 40)
        self.assertGreaterEqual(counts["datasets"], 2)
        self.assertGreaterEqual(counts["indicators"], 1)

    def test_observations_are_official_columns_without_calculations(self):
        rows = parse_population(fixture_csv())
        self.assertEqual(len(rows), 52 * 6)
        self.assertEqual(rows[0]["fips"], sorted(FIPS)[0])
        self.assertEqual(rows[0]["year"], 2020)
        self.assertTrue(all(row["statistic"] == "published_estimate" for row in rows))

    def test_map_and_series_have_exact_fips_join(self):
        raw, shapes = fixture_csv(), fixture_zip()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = build_release(root, raw, shapes, URLS, "2026-10-16T00:00:00Z")
            stats = validate_publication(root)
            self.assertEqual(stats["verifiedAssets"], 4)
            self.assertEqual(stats["observations"], 312)
            self.assertEqual(stats["geometryFeatures"], 52)
            original = (root / RELEASE_PATH / "source-table.csv").read_bytes()
            self.assertEqual(original, raw)
            self.assertEqual(manifest["sourceFiles"][0]["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(json.loads((root / "publication/index.json").read_text())["releases"][0]["status"], "published")

    def test_corrupted_source_is_rejected(self):
        raw = fixture_csv().replace(b"100000", b"INJECT", 1)
        with self.assertRaisesRegex(ValueError, "Invalid official population"):
            parse_population(raw)

    def test_geometry_cannot_silently_drop_geography(self):
        names = {fips: "Example " + fips for fips in FIPS}
        with self.assertRaisesRegex(ValueError, "Geographic archive incomplete"):
            parse_geometry(fixture_zip(include_all=False), names)

    def test_manifest_checksums_detect_publication_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_release(root, fixture_csv(), fixture_zip(), URLS, "2026-10-16T00:00:00Z")
            path = root / RELEASE_PATH / "observations.csv"
            path.write_text(path.read_text().replace("100000", "999999", 1))
            with self.assertRaisesRegex(ValueError, "Artifact integrity mismatch"):
                validate_publication(root)

    def test_official_fetch_host_is_pinned(self):
        with self.assertRaisesRegex(ValueError, "official Census"):
            fetch_source("https://example.org/poisoned.csv", 100)


if __name__ == "__main__":
    unittest.main()
