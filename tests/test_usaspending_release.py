"""Official USAspending API contract and security regressions (synthetic only)."""
from __future__ import annotations
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipelines.usaspending_release import (
    ENDPOINT, REQUEST, REQUEST_BYTES, USPS_TO_FIPS,
    EXCLUDED_TERRITORIES, project, stage, exclusion_report,
)
from pipelines.source_io import post_official_json
from pipelines.census_state_population import build_release
from test_pipeline import fixture_csv, fixture_zip, URLS
from tools.validate import validate_publication


def fixture_response(changes=None) -> bytes:
    results=[
        {"shape_code":code,"display_name":"Synthetic "+code,
         "aggregated_amount":round(10000.13+i*101.1,2),
         "population":None,"per_capita":None}
        for i,code in enumerate(sorted(USPS_TO_FIPS))
    ]
    results.extend(
        {"shape_code":code,"display_name":"Synthetic territory "+code,
         "aggregated_amount":44.12}
        for code in sorted(EXCLUDED_TERRITORIES)
    )
    results.append({"shape_code":"","display_name":"Unattributed synthetic geography",
                    "aggregated_amount":-101.25})
    result={"scope":"place_of_performance","geo_layer":"state",
            "spending_level":"transactions","results":results,"messages":[]}
    if changes:changes(result)
    return json.dumps(result,sort_keys=True).encode()


def validate_publication_after_stage(root, original):
    stage(root, original)
    return validate_publication(root)["releases"]


class SpendingTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        build_release(self.root,fixture_csv(),fixture_zip(),URLS,"2026-10-16T00:00:00Z")

    def test_fy2025_filters_are_pinned_as_part_of_provenance(self):
        self.assertEqual(REQUEST["scope"],"place_of_performance")
        self.assertEqual(REQUEST["spending_level"],"transactions")
        self.assertEqual(REQUEST["filters"]["time_period"],
            [{"start_date":"2024-10-01","end_date":"2025-09-30"}])
        self.assertNotIn("key=",ENDPOINT)

    def test_place_of_performance_crosswalk_has_all_reference_geographies(self):
        self.assertEqual(len(USPS_TO_FIPS),52)
        assert USPS_TO_FIPS["VA"] == "51"
        assert USPS_TO_FIPS["PR"] == "72"
        assert USPS_TO_FIPS["DC"] == "11"
        records=project(fixture_response())
        self.assertEqual(len(records),52)
        self.assertEqual(records[0]["geoid"],"01")
        self.assertEqual(records[-1]["geoid"],"72")
        self.assertEqual(records[0]["statistic"],"reported_award_transaction_obligations")

    def test_negative_deobligations_not_clipped_to_zero(self):
        def change(data):data["results"][0]["aggregated_amount"]=-153.27
        records=project(fixture_response(change))
        self.assertEqual([v for v in records if v["postalCode"]=="AK"][0]["value"],-153.27)

    def test_unreported_state_not_assumed_to_be_zero(self):
        def drop(data):data["results"]=[r for r in data["results"] if r["shape_code"]!="PR"]
        with self.assertRaisesRegex(ValueError,"lacks one or more 52"):
            project(fixture_response(drop))

    def test_foreign_or_unknown_geographic_code_rejected(self):
        def extra(data):data["results"].append({"shape_code":"ZZ",
            "display_name":"Unknown synthetic area","aggregated_amount":3})
        with self.assertRaisesRegex(ValueError,"Unexpected USAspending geographic code"):
            project(fixture_response(extra))

    def test_excluded_territory_must_not_be_misassigned(self):
        records=project(fixture_response())
        self.assertEqual(len(records),52)
        self.assertNotIn("VI",{x["postalCode"] for x in records})
        report=exclusion_report(fixture_response())
        self.assertEqual(report["unmappedAndTerritoryCount"],5)
        self.assertEqual({r["sourceShapeCode"] for r in report["exclusions"]},
                         EXCLUDED_TERRITORIES | {""})
        self.assertEqual(report["referenceGeographies"],52)
        self.assertTrue(any(r["reason"]=="unattributed_blank_geography_code"
                            and r["reportedAmount"]=="-101.25"
                            for r in report["exclusions"]))

    def test_reject_wrong_spending_level_or_scope(self):
        for field,value in (("scope","recipient_location"),("spending_level","awards")):
            def bad(data):data[field]=value
            with self.assertRaisesRegex(ValueError,"aggregation mismatch"):
                project(fixture_response(bad))

    def test_lossless_request_and_response_archives_and_replay(self):
        original=fixture_response()
        result=stage(self.root,original)
        folder=self.root/"publication/releases"/result["releaseId"]
        self.assertEqual(gzip.decompress((folder/"requestBody.gz").read_bytes()),REQUEST_BYTES)
        self.assertEqual(gzip.decompress((folder/"originalData.gz").read_bytes()),original)
        counts=validate_publication(self.root)
        self.assertEqual(counts["releases"],2)
        self.assertEqual(counts["observations"],364)
        self.assertTrue((self.root/"publication/releases/census-state-population-v2025/manifest.json").exists())

    def test_exclusion_report_is_immutable_and_source_replayed(self):
        release=stage(self.root,fixture_response())["releaseId"]
        folder=self.root/"publication/releases"/release
        report=json.loads((folder/"geography-exclusions.json").read_text())
        self.assertEqual(len(report["exclusions"]),5)
        manifest_path=folder/"manifest.json"
        manifest=json.loads(manifest_path.read_text())
        self.assertEqual(manifest["assets"]["geographyExclusions"]["rows"],5)
        report["exclusions"][0]["reportedAmount"]="99999.1"
        raw=(json.dumps(report,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
        (folder/"geography-exclusions.json").write_bytes(raw)
        manifest["assets"]["geographyExclusions"]["sha256"]=hashlib.sha256(raw).hexdigest()
        manifest["assets"]["geographyExclusions"]["bytes"]=len(raw)
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,"excluded or unattributed obligations"):
            validate_publication(self.root)

    def test_null_unattributed_display_name_is_preserved_not_imputed(self):
        def missing_label(data):
            for row in data["results"]:
                if row["shape_code"] == "":
                    row["display_name"]=None
        raw=fixture_response(missing_label)
        result=exclusion_report(raw)
        unattributed=[r for r in result["exclusions"]
                      if r["sourceShapeCode"]==""][0]
        self.assertIsNone(unattributed["sourceName"])
        self.assertEqual(len(project(raw)),52)
        self.assertEqual(validate_publication_after_stage(self.root, raw),2)

    def test_unattributed_bucket_must_be_single_and_explicit(self):
        def extra(data):
            data["results"].append({"shape_code":"",
                "display_name":"duplicate unattributed","aggregated_amount":123})
        with self.assertRaisesRegex(ValueError,"Duplicate unmapped"):
            project(fixture_response(extra))

    def test_changed_request_body_rejected_even_if_source_hashes_updated(self):
        with self.assertRaisesRegex(ValueError,"approved filters"):
            project(fixture_response(),b'{"wrong":"request"}')

    def test_forged_observation_not_accepted_with_rehashed_asset(self):
        result=stage(self.root,fixture_response())
        folder=self.root/"publication/releases"/result["releaseId"]
        path=folder/"observations.json"
        envelope=json.loads(path.read_text())
        envelope["observations"][0]["value"]=3.333
        raw=(json.dumps(envelope,ensure_ascii=False,sort_keys=True,
            separators=(",",":"))+"\n").encode()
        path.write_bytes(raw)
        mp=folder/"manifest.json"
        manifest=json.loads(mp.read_text())
        manifest["assets"]["observations"].update({
            "sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)})
        mp.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,"not reproducible"):
            validate_publication(self.root)

    def test_source_client_rejects_host_credentials_and_query_injection(self):
        for url in (
            "http://api.usaspending.gov/api/v2/search/spending_by_geography/",
            "https://api.usaspending.gov.evil.test/path",
            "https://user:pass@api.usaspending.gov/path",
            "https://api.usaspending.gov/path?token=secret",
        ):
            with self.subTest(url=url):
                with self.assertRaisesRegex(ValueError,"Unapproved official POST"):
                    post_official_json(url,REQUEST_BYTES,host="api.usaspending.gov",limit=100000)

    def test_source_client_rejects_unbounded_invalid_payload(self):
        with self.assertRaisesRegex(ValueError,"size ceiling"):
            post_official_json(ENDPOINT,b"[]",host="api.usaspending.gov",limit=0)
        with self.assertRaisesRegex(ValueError,"Invalid published source request JSON"):
            post_official_json(ENDPOINT,b"[]",host="api.usaspending.gov",limit=100000)
