"""Offline ACS original-source and key-security regression tests."""
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipelines.census_acs_release import PUBLIC_URL,acquire,project,stage
from pipelines.census_state_population import FIPS,build_release
from test_pipeline import fixture_csv,fixture_zip,URLS
from tools.validate import validate_publication


def fixture_acs(codes=FIPS):
    return json.dumps([
        ["NAME","B19013_001E","B19013_001M","state"],
        *[[f"Test area {code}", "65000", "1500", code] for code in sorted(codes)]
    ]).encode("utf-8")


class ACSPublicationTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        build_release(self.root,fixture_csv(),fixture_zip(),URLS,"2026-10-16T00:00:00Z")

    def test_acs_source_original_archive_and_replay(self):
        raw=fixture_acs()
        info=stage(self.root,raw)
        release=self.root/"publication/releases"/info["releaseId"]
        manifest=json.loads((release/"manifest.json").read_text())
        self.assertEqual(gzip.decompress((release/"originalData.gz").read_bytes()),raw)
        self.assertEqual(manifest["sourceFiles"][0]["sha256"],hashlib.sha256(raw).hexdigest())
        self.assertNotIn("key=",manifest["sourceFiles"][0]["url"].lower())
        self.assertEqual(validate_publication(self.root)["releases"],2)

    def test_reject_missing_geography(self):
        with self.assertRaisesRegex(ValueError,"coverage differs"):
            project(fixture_acs(set(FIPS)-{"72"}))

    def test_secure_api_key_transport_not_published(self):
        raw=fixture_acs()
        def stub(url,*,host,limit):
            self.assertEqual(host,"api.census.gov")
            self.assertTrue(url.startswith(PUBLIC_URL))
            self.assertIn("key=privateKey123",url)
            return raw
        with patch("pipelines.census_acs_release.download_official",side_effect=stub):
            downloaded=acquire("privateKey123")
        self.assertEqual(downloaded,raw)
        info=stage(self.root,downloaded)
        manuscript=(self.root/"publication/releases"/info["releaseId"]/"manifest.json").read_text()
        self.assertNotIn("privateKey123",manuscript)

    def test_key_with_linebreak_and_url_injection_rejected(self):
        for value in ("", "test\nX-Test:yes", "fake&host=evil", "fake?key=x"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError,"CENSUS_API_KEY"):
                    acquire(value)

    def test_consistent_rehashed_value_tampering_fails_source_replay(self):
        info=stage(self.root,fixture_acs())
        directory=self.root/"publication/releases"/info["releaseId"]
        path=directory/"observations.json"
        data=json.loads(path.read_text())
        data["observations"][0]["value"]=123456789
        raw=(json.dumps(data,sort_keys=True,separators=(",",":"))+"\n").encode()
        path.write_bytes(raw)
        manifest_path=directory/"manifest.json"
        manifest=json.loads(manifest_path.read_text())
        manifest["assets"]["observations"]["sha256"]=hashlib.sha256(raw).hexdigest()
        manifest["assets"]["observations"]["bytes"]=len(raw)
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,"not reproducible"):
            validate_publication(self.root)
