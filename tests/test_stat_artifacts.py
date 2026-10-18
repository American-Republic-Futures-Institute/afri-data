"""Synthetic-only STAT-02A execution and deterministic replay regression tests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from arfi_stats.artifacts import (
    ROOT, KIND, StatArtifactError, hash_json, produce, replay,
    validate_request, read_json_file, write_output, main,
)
from arfi_stats import METHODS


def fixture():
    return json.loads((ROOT / "examples/statkit-synthetic.json").read_text("utf-8"))


def request(kind):
    return json.loads((ROOT / "examples" /
        ("stat02a-" + kind + "-request.json")).read_text("utf-8"))


def synthetic_request(kind, x, y=None, segment=None, unit="untyped", params=None):
    template = request("histogram")
    template["method"] = {"chartType": kind, "methodId": METHODS[kind],
                          "version": "1.0.0"}
    template["fields"] = {"x": x, "y": y, "segment": segment,
                          "availability": "availability", "unit": unit}
    template["parameters"] = params if params is not None else {}
    return template


def rehash(artifact):
    artifact["artifactSha256"] = hash_json(
        {k: v for k, v in artifact.items() if k != "artifactSha256"})
    return artifact


class StatisticalArtifactTests(unittest.TestCase):
    def test_histogram_ecdf_and_quantiles_have_independent_reproducible_outputs(self):
        rows = fixture()
        originals = copy.deepcopy(rows)
        observed = {}
        for kind in ("histogram", "ecdf", "boxplot"):
            req = request(kind)
            original_request = copy.deepcopy(req)
            first = produce(req, rows)
            second = produce(copy.deepcopy(req), copy.deepcopy(rows))
            self.assertEqual(first, second)
            self.assertEqual(first["kind"], KIND)
            self.assertEqual(first["status"], "synthetic-preview-not-approved")
            self.assertEqual(first["chart"]["chartType"], kind)
            self.assertEqual(first["computation"]["methodId"], METHODS[kind])
            self.assertEqual(first["computation"]["chartInputFingerprint"],
                             first["chart"]["inputFingerprint"])
            self.assertEqual(first["computation"]["chartSha256"], hash_json(first["chart"]))
            self.assertEqual(first["requestSha256"], hash_json(req))
            self.assertEqual(first["sourceIdentity"]["inputSha256"], hash_json(rows))
            self.assertEqual(first["quality"]["selectedRows"], 6)
            self.assertEqual(first["quality"]["availableRows"], 5)
            self.assertEqual(first["quality"]["missingness"]["not_available"], 1)
            self.assertEqual(first["quality"]["unitOfAnalysis"], "synthetic-observation")
            self.assertFalse(first["authority"]["publicationAuthorized"])
            self.assertFalse(first["authority"]["sourceVerified"])
            self.assertEqual(first["authority"]["independentReviewStatus"],
                             "not-applicable-to-synthetic-fixture")
            self.assertTrue(any("fictional" in caveat.lower()
                                for caveat in first["quality"]["limitations"]))
            self.assertEqual(replay(first, rows), {
                "replay": "deterministic-match",
                "artifactSha256": first["artifactSha256"],
                "sourceAuthenticated": False,
                "publicationAuthorized": False})
            self.assertEqual(rows, originals)
            self.assertEqual(req, original_request)
            observed[kind] = first
        self.assertEqual(len({a["artifactSha256"] for a in observed.values()}), 3)
        self.assertEqual(sum(p["count"] for s in observed["histogram"]["chart"]["series"]
                             for p in s["points"]), 5)
        self.assertAlmostEqual(
            observed["ecdf"]["chart"]["series"][0]["points"][-1]["cumulative"], 1)
        self.assertEqual(observed["boxplot"]["chart"]["series"][0]["n"], 3)
        self.assertGreater(len(observed["boxplot"]["chart"]["series"][0]["statistics"]), 5)

    def test_provenance_and_runtime_manifests_are_complete(self):
        result = produce(request("histogram"), fixture())
        required = {"methodId", "methodVersion", "chartType",
                    "statkitVersion", "pythonVersion", "numpyVersion",
                    "coreSha256", "runnerSha256", "methodRegistrySha256",
                    "requirementsSha256", "chartSha256", "chartInputFingerprint"}
        self.assertEqual(set(result["computation"]), required)
        for name in ("coreSha256", "runnerSha256", "methodRegistrySha256",
                     "requirementsSha256"):
            self.assertRegex(result["computation"][name], r"^[a-f0-9]{64}$")
        self.assertEqual(result["sourceIdentity"]["releaseId"], None)
        self.assertEqual(result["sourceIdentity"]["sourceCommit"], None)
        self.assertEqual(result["sourceIdentity"]["canonicalization"],
                         "sorted-json-utf8-v1")

    def test_replay_rejects_changed_input_even_if_chart_looks_identical(self):
        req = request("histogram")
        rows = fixture()
        art = produce(req, rows)
        altered = copy.deepcopy(rows)
        altered[0]["auditExtra"] = "changed nonchart property"
        with self.assertRaisesRegex(StatArtifactError, "input bytes"):
            replay(art, altered)
        with self.assertRaisesRegex(StatArtifactError, "input bytes"):
            replay(art, list(reversed(rows)))
        with self.assertRaisesRegex(StatArtifactError, "input bytes"):
            replay(art, rows[:-1])

    def test_replay_rejects_any_changed_output_method_limitations_or_environment(self):
        art = produce(request("histogram"), fixture())
        for path, replacement in [
            (("chart", "series", 0, "points", 0, "count"), 400),
            (("quality", "availableRows"), 400),
            (("quality", "denominator"), "Tampered denominator label here."),
            (("sourceIdentity", "fixtureId"), "forged-identity"),
            (("computation", "numpyVersion"), "999.9.9"),
            (("computation", "coreSha256"), "f" * 64),
            (("computation", "requirementsSha256"), "f" * 64),
            (("request", "context", "interpretation"), "Fabricated interpretation with a different statement."),
        ]:
            changed = copy.deepcopy(art)
            obj = changed
            for key in path[:-1]:
                obj = obj[key]
            obj[path[-1]] = replacement
            rehash(changed)
            with self.assertRaises(StatArtifactError, msg=str(path)):
                replay(changed, fixture())
        changed = copy.deepcopy(art)
        changed["artifactSha256"] = "f" * 64
        with self.assertRaisesRegex(StatArtifactError, "artifact fingerprint"):
            replay(changed, fixture())
        with patch("arfi_stats.artifacts.computation_versions",
                   return_value={**art["computation"], "pythonVersion": "1.2.3"}):
            with self.assertRaisesRegex(StatArtifactError, "recomputed"):
                replay(art, fixture())

    def test_fail_closed_on_public_source_claims_cross_source_and_inference(self):
        illegal = [
            (("source", "sourceClass"), "official-source"),
            (("source", "releaseId"), "census-state-population-v2025"),
            (("source", "sourceCommit"), "f" * 40),
            (("controls", "publicationAuthorized"), True),
            (("controls", "sourceVerified"), True),
            (("controls", "statisticalInferenceAuthorized"), True),
            (("controls", "crossSourceAuthorized"), True),
            (("controls", "causalInferenceAuthorized"), True),
            (("method", "methodId"), "unreviewed-shrinkage/1"),
            (("method", "version"), "999.0.0"),
        ]
        for path, replacement in illegal:
            req = request("histogram")
            obj = req
            for key in path[:-1]:
                obj = obj[key]
            obj[path[-1]] = replacement
            with self.assertRaises(StatArtifactError, msg=str(path)):
                produce(req, fixture())
        for key in ("otherReleaseIds", "referenceBaseline", "targetModel",
                    "arbitraryFormula", "reviewDecision", "approve"):
            req = request("histogram")
            req[key] = "malicious"
            with self.assertRaises(StatArtifactError, msg=key):
                produce(req, fixture())

    def test_invalid_bins_parameters_and_forged_methods_are_denied(self):
        for bins in (0, -1, 65, True, "arbitrary", 1.5):
            req = request("histogram")
            req["parameters"]["bins"] = bins
            with self.assertRaises(StatArtifactError, msg=repr(bins)):
                produce(req, fixture())
        req = request("ecdf")
        req["parameters"]["scale"] = "proportion"
        with self.assertRaisesRegex(StatArtifactError, "method-specific"):
            produce(req, fixture())
        req = request("boxplot")
        req["method"]["methodId"] = METHODS["histogram"]
        with self.assertRaisesRegex(StatArtifactError, "method ID"):
            produce(req, fixture())

    def test_nonfinite_nonjson_and_missingness_are_refused_not_imputed(self):
        rows = fixture()
        bads = [
            ({"value": float("nan"), "availability": "available"}, "numeric"),
            ({"value": float("inf"), "availability": "available"}, "numeric"),
            ({"value": 3, "availability": "mystery"}, "availability"),
            ({"value": 5, "availability": "not_available"}, "method failed"),
            ({"value": True, "availability": "available"}, "method failed"),
        ]
        for sample, expected in bads:
            with self.assertRaisesRegex(StatArtifactError, expected):
                produce(request("histogram"), [sample])
        with self.assertRaises(StatArtifactError):
            produce(request("histogram"), rows * 2000)

    def test_unavailable_only_records_retain_explicit_status_without_fake_bins(self):
        rows = [{"value": None, "region": "East", "availability": "not_available"},
                {"value": None, "region": "West", "availability": "no_record"}]
        art = produce(request("histogram"), rows)
        self.assertEqual(art["quality"]["availableRows"], 0)
        self.assertEqual(art["quality"]["missingness"]["not_available"], 1)
        self.assertEqual(art["quality"]["missingness"]["no_record"], 1)
        self.assertEqual([s["n"] for s in art["chart"]["series"]], [0, 0])
        self.assertTrue(all(not s["points"] for s in art["chart"]["series"]))
        self.assertEqual(replay(art, rows)["replay"], "deterministic-match")

    def test_other_methods_call_existing_statkit_without_adding_new_model_logic(self):
        freq = synthetic_request("frequency", "category", segment="region",
                                 params={"scale": "count"})
        rows = [{"category": "A", "region": "East", "availability": "available"},
                {"category": "B", "region": "East", "availability": "available"},
                {"category": None, "region": "West", "availability": "suppressed"}]
        a = produce(freq, rows)
        self.assertEqual(a["quality"]["missingness"]["suppressed"], 1)
        self.assertEqual(replay(a, rows)["replay"], "deterministic-match")
        scatter = synthetic_request("scatter", "xvalue", y="yvalue", segment="region",
                                    unit="fictional-units", params={"xUnit":"fictional-units"})
        pairs = [{"xvalue": 1, "yvalue": 2, "region":"A","availability":"available"},
                 {"xvalue": 2, "yvalue": 3, "region":"A","availability":"available"}]
        self.assertEqual(produce(scatter, pairs)["chart"]["chartType"], "scatter")
        time = synthetic_request("time-series", "period", y="value", segment="region",
                                 unit="synthetic-index")
        sequence = [{"period":2020,"value":1,"region":"A","availability":"available"},
                    {"period":2021,"value":None,"region":"A","availability":"not_available"},
                    {"period":2022,"value":3,"region":"A","availability":"available"}]
        self.assertEqual(produce(time, sequence)["chart"]["series"][0]["points"][1]["value"], None)
        interval = synthetic_request("interval", "place", y="value", segment="region",
                                     unit="synthetic-percent",
                                     params={"lower":"low", "upper":"high",
                                             "intervalLabel":"Illustrative reported interval"})
        bounds = [{"place":"A","value":4.0,"low":3.0,"high":5.0,
                   "region":"One","availability":"available"}]
        spec=produce(interval,bounds)
        self.assertEqual(spec["chart"]["series"][0]["points"][0]["lower"],3)
        self.assertFalse(spec["quality"]["publisherUncertaintyVerified"])

    def test_cli_roundtrip_new_file_only_and_refuses_published_input(self):
        rows = ROOT / "examples/statkit-synthetic.json"
        req = ROOT / "examples/stat02a-histogram-request.json"
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "preview.json"
            self.assertEqual(main(["produce","--input",str(rows),"--request",str(req),
                                   "--output",str(artifact)]), 0)
            result = json.loads(artifact.read_text("utf-8"))
            self.assertEqual(result["kind"],KIND)
            replayed = Path(tmp) / "replayed.json"
            self.assertEqual(main(["replay","--input",str(rows),"--artifact",str(artifact),
                                   "--output",str(replayed)]),0)
            self.assertEqual(json.loads(replayed.read_text())["replay"],
                             "deterministic-match")
            with self.assertRaisesRegex(StatArtifactError, "already exists"):
                main(["produce","--input",str(rows),"--request",str(req),
                      "--output",str(artifact)])
            data = Path(tmp) / "duplicate.json"
            data.write_text('[{"value":1,"value":2}]')
            with self.assertRaisesRegex(StatArtifactError, "duplicate"):
                read_json_file(str(data))
            data.write_text('[{"value":NaN}]')
            with self.assertRaisesRegex(StatArtifactError, "nonfinite"):
                read_json_file(str(data))
        government = ROOT / "publication/index.json"
        with self.assertRaisesRegex(StatArtifactError, "published evidence"):
            read_json_file(str(government))

    def test_artifact_format_cannot_be_promoted_to_a_published_release(self):
        art = produce(request("histogram"), fixture())
        self.assertIsNone(art["sourceIdentity"]["sourceCommit"])
        self.assertIsNone(art["sourceIdentity"]["releaseId"])
        self.assertEqual(art["status"], "synthetic-preview-not-approved")
        self.assertNotIn("ReviewDecision", json.dumps(art))
        self.assertNotIn("approvedMethodology", json.dumps(art))


if __name__ == "__main__":
    unittest.main()
