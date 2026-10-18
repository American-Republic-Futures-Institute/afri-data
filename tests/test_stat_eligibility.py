"""STAT-01 deterministic, negative and source-identity acceptance tests.

No publisher data is modified and no independently certified model is emitted.
"""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from arfi_stats.eligibility import evaluate, quality_report
from tools.stat_profile_validate import (
    ROOT, PROFILES_DIR, StatisticalProfileError, check_schema,
    load, verify_all_profiles, verify_profile
)

RELEASES = {
    "census": "census-state-population-v2025",
    "bls": "bls-laus-state-unemployment-2025-e1625280119b26c3",
    "treasury": "usaspending-fy2025-state-obligations-775e56a13e40db59",
    "cdc": "cdc-places-county-obesity-2025-ec00ab31716eccca",
}
METHODS = {
    "histogram": "numpy.histogram/1",
    "ecdf": "numpy.unique-cumsum/1",
    "boxplot": "numpy.quantile-linear-tukey/1",
    "frequency": "categorical-count/1",
    "scatter": "source-paired-points/1",
    "time-series": "source-period-points/1",
    "interval": "publisher-supplied-bounds/1",
}
EMPTY_OPS = {
    "impute": False, "sampleWeight": False, "perCapita": False,
    "shrinkage": False, "newInterval": False, "deriveRate": False,
    "excludeSourceBuckets": False, "requireUniformPeriods": False,
}


def profile(name):
    release = RELEASES[name]
    return load(ROOT / PROFILES_DIR / (release + ".json"))


def request(name, chart, *, years=None, segment=None, x=None, y=None):
    p = profile(name)
    fields = {
        "frequency": ("availability", None),
        "time-series": ("year", "value"),
        "interval": (p["measurement"]["geographyField"], "value"),
    }
    X, Y = fields.get(chart, ("value", None))
    return {
        "schemaVersion": "1.0.0",
        "releaseId": p["identity"]["releaseId"],
        "methodId": METHODS[chart],
        "sourceCommit": p["identity"]["sourceCommit"],
        "observationsSha256": p["identity"]["observationsSha256"],
        "intent": "descriptive-preview",
        "x": x or X, "y": y if y is not None else Y,
        "segment": segment, "unitOfAnalysis": "geographic-units",
        "periodYears": years or [p["coverage"]["lastYear"]],
        "otherReleaseIds": [], "operations": copy.deepcopy(EMPTY_OPS),
        "acknowledgedQualifiers": p["coverage"]["qualifierCodes"].copy(),
    }


def decide(value):
    result = evaluate(value)
    check_schema(result, "contracts/statistical-eligibility-decision.schema.json")
    assert result["publicationAuthorized"] is False
    assert result["crossSourceAuthorized"] is False
    assert result["causalInferenceAuthorized"] is False
    assert result["statisticalInferenceAuthorized"] is False
    return result


class StatisticalEligibilityTests(unittest.TestCase):
    def test_exact_four_approved_profiles_and_exact_seven_methods(self):
        result = verify_all_profiles()
        self.assertEqual(result["profiles"], 4)
        self.assertEqual(result["methods"], 7)
        self.assertFalse(result["publishedDerivedAnalysisAuthorized"])
        release_ids = set(RELEASES.values())
        actual = {p.stem for p in (ROOT / PROFILES_DIR).glob("*.json")}
        self.assertEqual(actual, release_ids)
        for name in RELEASES:
            p = verify_profile(profile(name))
            self.assertEqual(p["reviewStatus"], "not_independently_certified")
            self.assertTrue(all(v is False for v in p["restrictions"].values()))
            self.assertEqual(p["identity"]["sourceCommit"],
                             "2a54ab437e083a40ef995d12f4d46366a8eb2963")

    def test_source_quality_reports_are_descriptive_and_source_bound(self):
        expected = {
            "census": (312, 312, 0, 0),
            "bls": (52, 52, 0, 0),
            "treasury": (52, 52, 0, 5),
            "cdc": (3143, 2956, 187, 0),
        }
        for name, (rows, available, unavailable, omitted) in expected.items():
            q = quality_report(RELEASES[name])
            self.assertTrue(q["sourceIdentityVerified"])
            self.assertFalse(q["publicationAuthorized"])
            self.assertEqual((q["sourceRows"], q["availableRows"],
                              q["explicitUnavailableRows"], q["knownOmittedSourceBuckets"]),
                             (rows, available, unavailable, omitted))
            self.assertEqual(q["reviewStatus"], "not_independently_certified")
            self.assertTrue(q["targetPopulation"])
            self.assertTrue(q["caveats"])
        self.assertTrue(quality_report(RELEASES["cdc"])["publisherIntervalAvailable"])
        self.assertTrue(quality_report(RELEASES["cdc"])["publisherModelled"])
        self.assertFalse(quality_report(RELEASES["bls"])["referencePeriodsUniform"])

    def test_census_preview_distribution_is_qualified_not_certified(self):
        for method in ("histogram", "ecdf", "boxplot"):
            result = decide(request("census", method))
            self.assertEqual(result["decision"], "qualified")
            self.assertTrue(result["methodApplicable"])
            self.assertTrue(result["sourceIdentityVerified"])
            self.assertIn("UNWEIGHTED_JURISDICTIONS_NOT_RESIDENTS",
                          result["reasonCodes"])
        result = decide(request("census", "frequency"))
        self.assertEqual(result["decision"], "permitted")
        self.assertEqual(result["reasonCodes"], ["SOURCE_NATIVE_PREVIEW_ONLY"])
        self.assertFalse(result["publicationAuthorized"])

    def test_within_census_multi_year_series_does_not_imply_independent_samples(self):
        value = request("census", "time-series", years=[2020, 2021, 2025])
        output = decide(value)
        self.assertEqual(output["decision"], "qualified")
        self.assertIn("REPEATED_GEOGRAPHIC_ESTIMATES_NOT_INDEPENDENT",
                      output["reasonCodes"])
        pooled = request("census", "histogram", years=[2020, 2025])
        denied = decide(pooled)
        self.assertEqual(denied["decision"], "denied")
        self.assertIn("REPEATED_OBSERVATION_POOLING", denied["reasonCodes"])
        grouped = request("census", "histogram", years=[2020, 2025],
                          segment="year")
        self.assertEqual(decide(grouped)["decision"], "qualified")

    def test_bls_nonuniform_reference_period_must_not_be_normalized_silently(self):
        a = request("bls", "histogram")
        d = decide(a)
        self.assertEqual(d["decision"], "qualified")
        self.assertIn("NONUNIFORM_SOURCE_REPORTING_PERIODS", d["reasonCodes"])
        a["operations"]["requireUniformPeriods"] = True
        denied = decide(a)
        self.assertEqual(denied["decision"], "denied")
        self.assertIn("INCOMPATIBLE_REPORTING_PERIODS", denied["reasonCodes"])
        self.assertIn("UNSUPPORTED_OR_MIXED_SOURCE_TIME_SERIES",
                      decide(request("bls", "time-series", years=[2025]))["reasonCodes"])

    def test_treasury_exact_money_distributions_and_omitted_buckets(self):
        for method in ("histogram", "ecdf", "boxplot"):
            denied = decide(request("treasury", method))
            self.assertEqual(denied["decision"], "denied")
            self.assertIn("METHOD_INCOMPATIBLE_WITH_MEASUREMENT", denied["reasonCodes"])
        coverage = decide(request("treasury", "frequency"))
        self.assertEqual(coverage["decision"], "qualified")
        self.assertIn("GEOGRAPHIC_EXCLUSION_LEDGER_REQUIRED",
                      coverage["reasonCodes"])
        req = request("treasury", "frequency")
        req["operations"]["excludeSourceBuckets"] = True
        self.assertIn("PUBLISHER_EXCLUSION_LEDGER_MUST_REMAIN",
                      decide(req)["reasonCodes"])

    def test_cdc_publisher_intervals_and_no_second_shrinkage(self):
        m = decide(request("cdc", "interval"))
        self.assertEqual(m["decision"], "qualified")
        self.assertIn("PUBLISHER_MODELED_NOT_DIRECT_OBSERVATIONS", m["reasonCodes"])
        self.assertIn("PUBLISHED_MISSINGNESS_MUST_BE_SHOWN", m["reasonCodes"])
        p = request("cdc", "interval")
        p["operations"]["shrinkage"] = True
        denied = decide(p)
        self.assertIn("DOUBLE_MODEL_SHRINKAGE_DENIED", denied["reasonCodes"])
        self.assertFalse(denied["methodApplicable"])
        self.assertIn("PUBLISHER_INTERVAL_NOT_AVAILABLE",
                      decide(request("bls", "interval"))["reasonCodes"])

    def test_deny_unauthorized_transformations_and_estimands(self):
        for operation in ("impute", "sampleWeight", "perCapita",
                          "shrinkage", "newInterval", "deriveRate"):
            req = request("census", "histogram")
            req["operations"][operation] = True
            self.assertEqual(decide(req)["decision"], "denied", operation)
        for analysis in ("public-derived-statistic", "statistical-inference",
                         "cross-source", "causal"):
            req = request("census", "histogram")
            req["intent"] = analysis
            self.assertEqual(decide(req)["decision"], "denied", analysis)
        for target in ("people", "transactions", "survey-respondents"):
            req = request("census", "histogram")
            req["unitOfAnalysis"] = target
            self.assertIn("ECOLOGICAL_SCOPE_NOT_SUPPORTED",
                          decide(req)["reasonCodes"])

    def test_reject_cross_source_hash_substitution_and_unapproved_baselines(self):
        req = request("census", "histogram")
        req["otherReleaseIds"] = [RELEASES["bls"]]
        self.assertIn("CROSS_RELEASE_OPERATION_DENIED", decide(req)["reasonCodes"])
        req = request("census", "histogram")
        req["observationsSha256"] = "f" * 64
        self.assertIn("IMMUTABLE_SOURCE_IDENTITY_MISMATCH", decide(req)["reasonCodes"])
        req = request("census", "histogram")
        req["sourceCommit"] = "f" * 40
        self.assertIn("IMMUTABLE_SOURCE_IDENTITY_MISMATCH", decide(req)["reasonCodes"])
        req = request("census", "histogram")
        req["segment"] = "sex"
        self.assertIn("UNAPPROVED_SEGMENT_COLUMN", decide(req)["reasonCodes"])
        req = request("census", "histogram")
        req["periodYears"] = [2019]
        self.assertIn("REFERENCE_PERIOD_NOT_IN_RELEASE", decide(req)["reasonCodes"])

    def test_unreviewed_statistical_methods_cannot_expand_authority(self):
        for name in RELEASES:
            for method in ("scatter", "time-series"):
                req = request(name, method)
                if method == "scatter":
                    req["y"] = "value"
                if method == "time-series" and name == "census":
                    req["periodYears"] = [2020, 2025]
                outcome = decide(req)
                if method == "scatter" or name != "census":
                    self.assertEqual(outcome["decision"], "denied", (name, method))
        req = request("census", "histogram")
        req["methodId"] = "unreviewed-bayesian-shrinkage/1"
        self.assertIn("METHOD_NOT_REGISTERED", decide(req)["reasonCodes"])

    def test_qualifier_acknowledgement_does_not_turn_a_preview_into_approval(self):
        a = request("bls", "ecdf")
        a["acknowledgedQualifiers"] = []
        no_ack = decide(a)
        self.assertIn("PUBLISHER_QUALIFICATIONS_NOT_ACKNOWLEDGED",
                      no_ack["reasonCodes"])
        a["acknowledgedQualifiers"] = profile("bls")["coverage"]["qualifierCodes"]
        acked = decide(a)
        self.assertNotIn("PUBLISHER_QUALIFICATIONS_NOT_ACKNOWLEDGED",
                         acked["reasonCodes"])
        self.assertEqual(acked["decision"], "qualified")
        self.assertFalse(acked["publicationAuthorized"])

    def test_invalid_request_and_added_fields_are_denied(self):
        for value in ({}, None, [], {"methodId": "histogram"}, "histogram"):
            self.assertIn("INVALID_REQUEST", decide(value)["reasonCodes"])
        req = request("census", "histogram")
        req["approvalGranted"] = True
        self.assertIn("INVALID_REQUEST", decide(req)["reasonCodes"])
        req = request("census", "histogram")
        req["operations"]["anything-goes"] = True
        self.assertIn("INVALID_REQUEST", decide(req)["reasonCodes"])

    def test_tampered_evidence_never_passes_only_because_json_looks_plausible(self):
        release = RELEASES["census"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = [
                "publication/index.json",
                "publication/releases/" + release + "/manifest.json",
                "publication/releases/" + release + "/observations.json",
                "catalog/statistics/source-profiles/" + release + ".json",
                "catalog/statistics/method-applicability.json",
                "contracts/stat-method-registry.json",
            ]
            for name in paths:
                dest = root / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, dest)
            p = load(root / PROFILES_DIR / (release + ".json"))
            verify_profile(p, root=root, historical=False)
            observations = root / "publication/releases" / release / "observations.json"
            observations.write_bytes(observations.read_bytes() + b" ")
            with self.assertRaisesRegex(StatisticalProfileError, "SHA-256"):
                verify_profile(p, root=root, historical=False)
            self.assertIn("SOURCE_IDENTITY_NOT_VERIFIED",
                          evaluate(request("census", "histogram"),
                                   root=root, historical=False)["reasonCodes"])
            shutil.copyfile(ROOT / paths[2], observations)
            manifest = root / paths[1]
            manifest.write_text(manifest.read_text() + " ")
            with self.assertRaisesRegex(StatisticalProfileError, "manifest bytes"):
                verify_profile(p, root=root, historical=False)
            shutil.copyfile(ROOT / paths[1], manifest)
            profile_path = root / paths[3]
            p["coverage"]["availableRows"] = 311
            profile_path.write_text(json.dumps(p))
            with self.assertRaisesRegex(StatisticalProfileError, "availability"):
                verify_profile(p, root=root, historical=False)

    def test_same_request_same_fingerprint_and_no_cross_dataset_effects(self):
        a = request("census", "histogram")
        first = decide(a)
        second = decide(copy.deepcopy(a))
        self.assertEqual(first, second)
        self.assertEqual(len(first["requestFingerprint"]), 64)
        a["periodYears"] = [2024]
        self.assertNotEqual(decide(a)["requestFingerprint"], first["requestFingerprint"])


if __name__ == "__main__":
    unittest.main()
