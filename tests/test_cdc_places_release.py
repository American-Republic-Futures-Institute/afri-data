"""CDC PLACES modeling, interval integrity and archived source tests."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from pipelines.cdc_places_release import parse_places,stage,COUNT
from pipelines.census_state_population import build_release
from test_pipeline import fixture_csv,fixture_zip,URLS
from tools.validate import validate_publication

def fixture(overrides=None):
    rows=[]
    for i in range(COUNT):
        rows.append({
            "countyfips":str(i+1000).zfill(5),
            "countyname":f"Test County {i}",
            "stateabbr":"VA",
            "obesity_crudeprev":"33.2",
            "obesity_crude95ci":"31.5-35.0",
        })
    if overrides:overrides(rows)
    return json.dumps(rows).encode()

class PlacesTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        build_release(self.root,fixture_csv(),fixture_zip(),URLS,"2026-10-16T00:00:00Z")

    def test_county_projection_preserves_model_and_interval(self):
        rows=parse_places(fixture())
        self.assertEqual(len(rows),3143)
        self.assertEqual(rows[0]["value"],33.2)
        self.assertEqual(rows[0]["lower95"],31.5)
        self.assertEqual(rows[0]["upper95"],35.0)
        self.assertEqual(rows[0]["statistic"],"model_based_estimate")
        self.assertEqual(rows[0]["year"],2023)
        self.assertEqual(rows[0]["publisherVintage"],2025)

    def test_duplicate_or_missing_county_rejected(self):
        with self.assertRaisesRegex(ValueError,"county coverage"):
            parse_places(json.dumps(json.loads(fixture())[:-1]).encode())
        def override(rows):rows[-1]["countyfips"]=rows[0]["countyfips"]
        with self.assertRaisesRegex(ValueError,"duplicate county"):
            parse_places(fixture(override))

    def test_bad_confidence_bounds_rejected(self):
        def override(rows):rows[0]["obesity_crude95ci"]="40.0-50.0"
        with self.assertRaisesRegex(ValueError,"confidence interval excludes"):
            parse_places(fixture(override))
        def malformed(rows):rows[0]["obesity_crude95ci"]="CI unknown"
        with self.assertRaisesRegex(ValueError,"confidence interval notation"):
            parse_places(fixture(malformed))

    def test_source_archive_and_full_release_validation(self):
        original=fixture()
        r=stage(self.root,original)
        manifest=json.loads((self.root/"publication/releases"/r["releaseId"]/"manifest.json").read_text())
        self.assertEqual(manifest["sourceFiles"][0]["sha256"],hashlib.sha256(original).hexdigest())
        totals=validate_publication(self.root)
        self.assertEqual(totals["releases"],2)
        self.assertEqual(totals["observations"],312+COUNT)

    def test_edited_projection_fails_even_if_rehashed(self):
        r=stage(self.root,fixture())
        folder=self.root/"publication/releases"/r["releaseId"]
        path=folder/"observations.json"
        doc=json.loads(path.read_text())
        doc["observations"][0]["value"]=55.0
        raw=(json.dumps(doc,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
        path.write_bytes(raw)
        manifest_path=folder/"manifest.json"
        manifest=json.loads(manifest_path.read_text())
        manifest["assets"]["observations"]["sha256"]=hashlib.sha256(raw).hexdigest()
        manifest["assets"]["observations"]["bytes"]=len(raw)
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,"not reproducible"):
            validate_publication(self.root)
