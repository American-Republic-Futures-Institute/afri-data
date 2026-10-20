"""STAT-06A official 2024 ACS five-year B19013 state income source tests.

Only the test fixtures are synthetic. Production acquisition uses the entire
official 17.9 MB 2024 Census table-based B19013 source file.
"""
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipelines.census_acs_release import (
    STATIC_URL,PUBLIC_URL,acquire,acquire_static,project,stage
)
from pipelines.census_acs_income import (
    parse_acs_state_income,parse_acs_table_based_income
)
from pipelines.census_state_population import FIPS,build_release
from test_pipeline import fixture_csv,fixture_zip,URLS
from tools.validate import validate_publication


def fixture_acs(codes=FIPS, *, suppressed=(), value="65000", moe="1500"):
    lines=["GEO_ID|B19013_E001|B19013_M001",
           "0100000US|80734|166",
           "0500000US01001|80000|3000"]
    for code in sorted(codes):
        masked=code in suppressed
        lines.append("0400000US"+code+"|"+
            ("-666666666" if masked else value)+"|"+
            ("-666666666" if masked else moe))
    return ("\n".join(lines)+"\n").encode("utf-8")


class ACSPublicationTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        build_release(self.root,fixture_csv(),fixture_zip(),URLS,
                      "2026-10-16T00:00:00Z")

    def test_acs_source_original_archive_replay_and_exact_fips(self):
        raw=fixture_acs()
        rows=project(raw)
        self.assertEqual(len(rows),52)
        self.assertEqual({r["geoid"] for r in rows},FIPS)
        self.assertTrue(all(r["value"]==65000 and
            r["marginOfError"]==1500 for r in rows))
        self.assertTrue(all(r["status"]=="available" for r in rows))
        self.assertEqual(rows[0]["referencePeriod"],"2020-2024 five-year ACS")
        info=stage(self.root,raw)
        release=self.root/"publication/releases"/info["releaseId"]
        manifest=json.loads((release/"manifest.json").read_text())
        self.assertEqual(gzip.decompress((release/"originalData.gz").read_bytes()),raw)
        self.assertEqual(manifest["sourceFiles"][0]["sha256"],hashlib.sha256(raw).hexdigest())
        self.assertEqual(manifest["sourceFiles"][0]["url"],STATIC_URL)
        self.assertNotIn("key=",manifest["sourceFiles"][0]["url"].lower())
        self.assertEqual(manifest["geography"]["features"],52)
        self.assertEqual(manifest["assets"]["observations"]["rows"],52)
        self.assertEqual(validate_publication(self.root)["releases"],2)

    def test_actual_state_values_only_not_non_state_rows(self):
        rows=project(fixture_acs())
        self.assertEqual(len(rows),52)
        self.assertNotIn("0100000US",{r["geoid"] for r in rows})
        self.assertEqual(rows[-1]["geoid"],"72")
        self.assertEqual(rows[-1]["name"],"Puerto Rico")

    def test_reject_missing_geography_duplicate_and_wrong_header(self):
        with self.assertRaisesRegex(ValueError,"coverage differs"):
            project(fixture_acs(set(FIPS)-{"72"}))
        duplicated=fixture_acs()+b"0400000US51|65000|1500\n"
        with self.assertRaisesRegex(ValueError,"duplicate"):
            project(duplicated)
        with self.assertRaisesRegex(ValueError,"header"):
            project(fixture_acs().replace(b"B19013_M001",b"B19013_M111",1))
        with self.assertRaisesRegex(ValueError,"column width"):
            project(fixture_acs()+b"some|bad|extra|row\n")

    def test_suppressed_source_pair_is_null_never_zero(self):
        rows=project(fixture_acs(suppressed={"21","42"}))
        self.assertEqual(sum(r["status"]=="not_available" for r in rows),2)
        for code in ("21","42"):
            r=next(v for v in rows if v["geoid"]==code)
            self.assertIsNone(r["value"])
            self.assertIsNone(r["marginOfError"])
        self.assertEqual(rows[0]["unit"],"USD")
        self.assertEqual(rows[0]["year"],2024)
        with self.assertRaisesRegex(ValueError,"suppression"):
            project(fixture_acs().replace(b"65000|1500",b"-666666666|1500",1))

    def test_wrong_integer_or_sentinel_is_not_a_numeric_observation(self):
        with self.assertRaisesRegex(ValueError,"sentinel"):
            project(fixture_acs(value="-12345"))
        with self.assertRaisesRegex(ValueError,"integer"):
            project(fixture_acs(value="0"))
        with self.assertRaisesRegex(ValueError,"sentinel"):
            project(fixture_acs(moe="23.1"))
        with self.assertRaisesRegex(ValueError,"integer"):
            project(fixture_acs(moe="1000000001"))

    def test_static_acquisition_requires_only_exact_official_census_host(self):
        raw=fixture_acs()
        def stub(url,*,host,limit):
            self.assertEqual(url,STATIC_URL)
            self.assertEqual(host,"www2.census.gov")
            self.assertGreaterEqual(limit,17_917_916)
            self.assertLessEqual(limit,25_000_000)
            return raw
        with patch("pipelines.census_acs_release.download_official",side_effect=stub):
            downloaded=acquire_static()
        self.assertEqual(downloaded,raw)
        self.assertEqual(len(project(downloaded)),52)

    def test_legacy_credential_transport_never_prints_or_publishes_secret(self):
        payload=json.dumps([
            ["NAME","B19013_001E","B19013_001M","state"],
            ["Virginia","89000","1212","51"]
        ]).encode()
        def stub(url,*,host,limit):
            self.assertEqual(host,"api.census.gov")
            self.assertTrue(url.startswith(PUBLIC_URL))
            self.assertIn("key=privateKey123",url)
            return payload
        with patch("pipelines.census_acs_release.download_official",side_effect=stub):
            self.assertEqual(acquire("privateKey123"),payload)
        self.assertEqual(parse_acs_state_income(payload)[0]["value"],89000)
        for value in ("","test\nX-Test:yes","fake&host=evil","fake?key=x"):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,"CENSUS_API_KEY"):
                acquire(value)

    def test_source_only_governance_classification_cannot_assert_independent_review(self):
        from tools.review_governance import is_source_reproduced_acs_income
        info=stage(self.root,fixture_acs())
        folder=self.root/"publication/releases"/info["releaseId"]
        manifest=json.loads((folder/"manifest.json").read_text())
        index=json.loads((self.root/"publication/index.json").read_text())
        item=next(x for x in index["releases"]
                  if x["releaseId"]==info["releaseId"])
        self.assertTrue(is_source_reproduced_acs_income(item,manifest,self.root))
        import copy
        for edit in (
            lambda d:d["manifest"].update(publishedSource="Other publisher"),
            lambda d:d["manifest"]["sourceFiles"][0].update(url="https://example.org/fake.dat"),
            lambda d:d["manifest"]["sourceFiles"][0].update(sha256="a"*64),
            lambda d:d["manifest"]["geography"].update(features=51),
            lambda d:d["manifest"].update(interpretation="independently reviewed"),
            lambda d:d["item"].update(indicatorId="other-metric"),
        ):
            copies={"item":copy.deepcopy(item),"manifest":copy.deepcopy(manifest)}
            edit(copies)
            self.assertFalse(is_source_reproduced_acs_income(
                copies["item"],copies["manifest"],self.root))
        archive=folder/"originalData.gz"
        original=archive.read_bytes()
        archive.write_bytes(gzip.compress(b"untrusted source"))
        self.assertFalse(is_source_reproduced_acs_income(item,manifest,self.root))
        archive.write_bytes(original)

    def test_rehashed_value_tampering_fails_original_source_replay(self):
        info=stage(self.root,fixture_acs())
        folder=self.root/"publication/releases"/info["releaseId"]
        p=folder/"observations.json"
        doc=json.loads(p.read_text())
        doc["observations"][0]["value"]=999999
        raw=(json.dumps(doc,sort_keys=True,separators=(",",":"))+"\n").encode()
        p.write_bytes(raw)
        mp=folder/"manifest.json"
        manifest=json.loads(mp.read_text())
        manifest["assets"]["observations"]["sha256"]=hashlib.sha256(raw).hexdigest()
        manifest["assets"]["observations"]["bytes"]=len(raw)
        mp.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,"not reproducible"):
            validate_publication(self.root)

if __name__=="__main__":
    unittest.main()
