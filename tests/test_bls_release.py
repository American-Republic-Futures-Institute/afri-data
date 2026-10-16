"""Verified BLS publication tests. All newly constructed records are synthetic."""
from __future__ import annotations
import csv
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest

from pipelines.bls_laus_release import parse_authoritative_annual, stage
from pipelines.census_state_population import FIPS,build_release
from test_pipeline import fixture_csv,fixture_zip,URLS
from tools.validate import validate_publication


def mock_bls_sources(fips=None):
    codes = sorted(fips if fips is not None else FIPS)
    data = io.StringIO()
    series = io.StringIO()
    areas = io.StringIO()
    data.write("series_id\tyear\tperiod\tvalue\tfootnote_codes\n")
    series.write("series_id\tarea_type_code\tarea_code\tmeasure_code\tseasonal\n")
    areas.write("area_type_code\tarea_code\tarea_text\n")
    for code in codes:
        area = "ST" + code + "0"*11
        series_id = "LAU"+area+"03"
        data.write(f"{series_id}\t2025\tM13\t4.2\t\n")
        data.write(f"{series_id}\t2025\tM01\t7.0\t\n")
        data.write(f"LAS{area}03\t2025\tM01\t9.0\t\n")
        series.write(f"{series_id}\tA\t{area}\t03\tU\n")
        areas.write(f"A\t{area}\tTest region {code}\n")
    return (data.getvalue().encode(),series.getvalue().encode(),areas.getvalue().encode())


class BLSReleaseTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        build_release(self.root,fixture_csv(),fixture_zip(),URLS,"2026-10-16T00:00:00Z")
        self.originals=mock_bls_sources()

    def test_official_format_crosswalk_and_complete_coverage(self):
        rows=parse_authoritative_annual(*self.originals)
        self.assertEqual(len(rows),52)
        self.assertEqual(rows[0]["geoid"],"01")
        self.assertEqual(rows[-1]["geoid"],"72")
        self.assertEqual(rows[0]["value"],4.2)
        self.assertEqual(rows[0]["seasonalAdjustment"],"not_seasonally_adjusted")

    def test_source_archives_reproduce_exact_publisher_bytes(self):
        result=stage(self.root,*self.originals)
        release=result["releaseId"]
        folder=self.root/"publication/releases"/release
        m=json.loads((folder/"manifest.json").read_text())
        for source in m["sourceFiles"]:
            raw=gzip.decompress((folder/(source["role"]+".gz")).read_bytes())
            index=["originalData","originalSeries","originalAreas"].index(source["role"])
            self.assertEqual(raw,self.originals[index])
        stats=validate_publication(self.root)
        self.assertEqual(stats["releases"],2)
        self.assertEqual(stats["observations"],364)
        self.assertTrue((self.root/"publication/releases/census-state-population-v2025/manifest.json").exists())

    def test_missing_geography_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"coverage mismatch"):
            parse_authoritative_annual(*mock_bls_sources(set(FIPS)-{"72"}))

    def test_modified_source_archive_detected(self):
        result=stage(self.root,*self.originals)
        file=self.root/"publication/releases"/result["releaseId"]/"originalData.gz"
        file.write_bytes(gzip.compress(b"altered"))
        with self.assertRaisesRegex(ValueError,"integrity mismatch"):
            validate_publication(self.root)

    def test_duplicate_source_series_rejected(self):
        a,b,c=self.originals
        rows=b.decode().splitlines()
        with self.assertRaisesRegex(ValueError,"Duplicate BLS series"):
            parse_authoritative_annual(a,(b.decode()+"\n"+rows[1]+"\n").encode(),c)

    def test_edited_projection_rejected_even_with_consistent_asset_hash(self):
        import hashlib
        result=stage(self.root,*self.originals)
        folder=self.root/"publication/releases"/result["releaseId"]
        file=folder/"observations.json"
        content=json.loads(file.read_text())
        content["observations"][0]["value"]=99.9
        raw=(json.dumps(content,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
        file.write_bytes(raw)
        manifest_path=folder/"manifest.json"
        manifest=json.loads(manifest_path.read_text())
        manifest["assets"]["observations"]["sha256"]=hashlib.sha256(raw).hexdigest()
        manifest["assets"]["observations"]["bytes"]=len(raw)
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,"not reproducible"):
            validate_publication(self.root)

    def test_revision_is_new_identity_with_changed_source(self):
        first=stage(self.root,*self.originals)
        data=self.originals[0].replace(b"4.2",b"4.3",1)
        second=stage(self.root,data,*self.originals[1:])
        self.assertNotEqual(first["releaseId"],second["releaseId"])
        self.assertEqual(second["review"]["revised"],1)
        self.assertEqual(validate_publication(self.root)["releases"],3)
