"""Synthetic-only statistical contract tests. No government release is ingested."""
import copy
import json
import math
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

import arfi_stats as stat

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "contracts/stat-chart-preview.schema.json").read_text())
REGISTRY = json.loads((ROOT / "contracts/stat-method-registry.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def valid(model):
    errors = sorted(VALIDATOR.iter_errors(model), key=lambda err: str(err.path))
    assert not errors, "; ".join(str(err)[:300] for err in errors[:3])
    assert model["authority"] == {
        "sourceVerified": False, "publicationAuthorized": False,
        "crossSourceAuthorized": False, "statisticalInferenceAuthorized": False,
        "causalInferenceAuthorized": False}
    return model


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            {"value": 10, "region": "east", "availability": "available"},
            {"value": 10, "region": "east", "availability": "available"},
            {"value": 20, "region": "east", "availability": "available"},
            {"value": None, "region": "east", "availability": "not_available"},
            {"value": 30, "region": "west", "availability": "available"},
            {"value": 40, "region": "west", "availability": "available"},
            {"value": None, "region": "west", "availability": "no_record"},
        ]

    def test_histogram_uses_numpy_edges_shared_across_segments_and_accounts_for_nulls(self):
        h = valid(stat.histogram(self.records, x="value", segment="region",
                                 bins=3, scale="proportion", unit="persons"))
        self.assertEqual(h["selection"]["inputRows"], 7)
        self.assertEqual(h["selection"]["missingness"]["not_available"], 1)
        self.assertEqual(h["selection"]["missingness"]["no_record"], 1)
        self.assertEqual([s["label"] for s in h["series"]], ["east", "west"])
        self.assertEqual([s["n"] for s in h["series"]], [3, 2])
        self.assertEqual(sum(p["count"] for p in h["series"][0]["points"]), 3)
        self.assertEqual(sum(p["count"] for p in h["series"][1]["points"]), 2)
        self.assertAlmostEqual(sum(p["value"] for p in h["series"][0]["points"]), 1)
        self.assertAlmostEqual(sum(p["value"] for p in h["series"][1]["points"]), 1)
        for index in range(3):
            self.assertEqual(h["series"][0]["points"][index]["low"],
                             h["series"][1]["points"][index]["low"])
            self.assertEqual(h["series"][0]["points"][index]["high"],
                             h["series"][1]["points"][index]["high"])
        self.assertEqual(h["algorithm"]["methodId"], "numpy.histogram/1")
        self.assertNotIn("mean", h["series"][0])
        self.assertNotIn("mode", h["series"][0])

    def test_auto_bins_are_deterministic_bounded_and_sparse_data_supported(self):
        values = [{"x": float(i) / 10, "availability": "available"}
                  for i in range(300)]
        for strategy in ("fd", "sturges", "sqrt", "auto"):
            result = valid(stat.histogram(values, x="x", bins=strategy))
            self.assertGreater(len(result["series"][0]["points"]), 0)
            self.assertLessEqual(len(result["series"][0]["points"]), 64)
            self.assertEqual(sum(x["count"] for x in result["series"][0]["points"]), 300)
        singleton = valid(stat.histogram([{"x": 1, "availability": "available"}], x="x"))
        self.assertEqual(singleton["series"][0]["points"][0]["count"], 1)
        constant = valid(stat.histogram([{"x": 3, "availability": "available"}] * 10, x="x"))
        self.assertEqual(sum(p["count"] for p in constant["series"][0]["points"]), 10)
        no_data = valid(stat.histogram([{"x": None, "availability": "unknown"}], x="x"))
        self.assertEqual(no_data["series"], [])
        self.assertTrue(any("No available" in x for x in no_data["limitations"]))

    def test_ecdf_preserves_duplicate_frequency_without_suggesting_population_inference(self):
        m = valid(stat.ecdf(self.records, x="value", segment="region"))
        east = m["series"][0]
        self.assertEqual(east["n"], 3)
        self.assertEqual(east["points"][0]["countAtX"], 2)
        self.assertAlmostEqual(east["points"][0]["cumulative"], 2 / 3)
        self.assertEqual(east["points"][-1]["cumulative"], 1)
        self.assertFalse(m["authority"]["statisticalInferenceAuthorized"])

    def test_boxplot_uses_quantiles_and_preserves_outlier_candidates(self):
        rows = [{"metric": v, "availability": "available"}
                for v in (1, 2, 3, 4, 20)]
        box = valid(stat.boxplot(rows, x="metric"))
        stats = box["series"][0]["statistics"]
        self.assertEqual(stats["median"], 3)
        self.assertEqual(stats["q1"], 2)
        self.assertEqual(stats["q3"], 4)
        self.assertEqual(stats["p10"], 1.4)
        self.assertEqual(stats["p90"], 13.6)
        self.assertEqual(stats["outliers"], [20.0])
        self.assertEqual(stats["max"], 20)
        self.assertEqual(box["algorithm"]["parameters"]["whisker"], "tukey-1.5-iqr")
        self.assertIsNone(valid(stat.boxplot([{"metric": None, "availability": "suppressed"}],
                                              x="metric"))["series"][0]["statistics"])

    def test_frequency_does_not_average_ordinals_or_lose_group_denominators(self):
        rows = [{"stars": n, "group": g, "availability": "available"}
                for n, g in [(5,"A"),(5,"A"),(4,"B"),(3,"B"),(4,"B")]]
        rows.append({"stars": None, "group": "B", "availability": "suppressed"})
        chart = valid(stat.frequency(rows, x="stars", segment="group", scale="proportion"))
        self.assertEqual(chart["series"][0]["points"],
                         [{"category": "5", "count": 2, "value": 1.0}])
        self.assertEqual(chart["series"][1]["n"], 3)
        self.assertEqual(chart["series"][1]["missingness"]["suppressed"], 1)
        self.assertEqual(chart["series"][1]["points"][0]["category"], "3")
        self.assertNotIn("mean", chart["algorithm"]["parameters"])

    def test_scatter_is_pairwise_description_not_statistical_association(self):
        rows = [{"population": a, "income": b, "region": c, "availability": "available"}
                for a, b, c in [(100,20,"A"),(200,30,"A"),(150,35,"B")]]
        p = valid(stat.scatter(rows, x="population", y="income", segment="region",
                               x_unit="persons", y_unit="USD"))
        self.assertEqual(p["series"][0]["points"], [{"x": 100., "y": 20.},
                                                   {"x": 200., "y": 30.}])
        self.assertNotIn("r", p["series"][0])
        self.assertEqual(p["fields"]["unit"], "USD")
        self.assertTrue(any("approximate" in s for s in p["limitations"]))
        self.assertFalse(p["authority"]["crossSourceAuthorized"])

    def test_time_series_has_ordered_source_periods_and_explicit_gaps(self):
        rows = [{"period": v, "score": value, "availability": status}
                for v, value, status in ((2022, 3, "available"), (2020, 1, "available"),
                                         (2021, None, "not_available"))]
        p = valid(stat.time_series(rows, x="period", y="score"))
        self.assertEqual([x["period"] for x in p["series"][0]["points"]],
                         ["2020", "2021", "2022"])
        self.assertEqual(p["series"][0]["points"][1]["value"], None)
        self.assertEqual(p["series"][0]["points"][1]["availability"], "not_available")
        self.assertFalse(p["axis"]["connectMissing"])
        with self.assertRaisesRegex(ValueError, "approved aggregation"):
            stat.time_series(rows + [rows[0]], x="period", y="score")
        with self.assertRaisesRegex(ValueError, "invalid ISO"):
            stat.time_series([{"period": "2025-13-92", "score": 1,
                               "availability": "available"}], x="period", y="score")

    def test_publisher_interval_display_never_fabricates_uncertainty(self):
        rows = [{"place": "A", "estimate": 4.5, "low95": 3.5, "high95": 5.3,
                 "availability": "available"},
                {"place": "B", "estimate": None, "low95": None, "high95": None,
                 "availability": "no_record"}]
        i = valid(stat.intervals(rows, x="place", y="estimate", lower="low95",
                                 upper="high95", unit="percent", interval_label="Source 95% interval"))
        self.assertEqual(i["series"][0]["points"],
                         [{"category":"A","estimate":4.5,"lower":3.5,"upper":5.3}])
        self.assertEqual(i["selection"]["missingness"]["no_record"], 1)
        self.assertTrue(any("source-supplied" in x for x in i["limitations"]))
        with self.assertRaisesRegex(ValueError, "contain published"):
            bad = copy.deepcopy(rows)
            bad[0]["high95"] = 4.0
            stat.intervals(bad, x="place", y="estimate", lower="low95", upper="high95")
        with self.assertRaisesRegex(ValueError, "required"):
            missing = copy.deepcopy(rows)
            del missing[0]["low95"]
            stat.intervals(missing, x="place", y="estimate", lower="low95", upper="high95")

    def test_filter_and_fingerprint_are_repeatable_without_mutation(self):
        rows = copy.deepcopy(self.records)
        first = valid(stat.histogram(rows, x="value", segment="region", bins=2,
                                     where={"region": ["west"]}))
        self.assertEqual(first["selection"]["selectedRows"], 3)
        self.assertEqual(first["selection"]["filters"]["region"], ["west"])
        self.assertEqual(first["selection"]["missingness"]["not_available"], 0)
        self.assertEqual(first["series"][0]["n"], 2)
        other = stat.histogram(list(reversed(rows)), x="value", segment="region",
                               bins=2, where={"region":["west"]})
        self.assertEqual(first["inputFingerprint"], other["inputFingerprint"])
        self.assertEqual(rows, self.records)

    def test_every_method_is_registered_and_denies_publication_by_default(self):
        self.assertEqual(REGISTRY["publicationAuthorized"], False)
        self.assertEqual(set(stat.CHARTS), {x["kind"] for x in REGISTRY["methods"]})
        self.assertEqual(set(stat.METHODS.values()), {x["methodId"] for x in REGISTRY["methods"]})
        self.assertTrue(all(x["publicationAuthorized"] is False and
                            x["independentReviewStatus"]=="pending" for x in REGISTRY["methods"]))
        self.assertEqual(stat.VERSION, "0.1.0")
        self.assertEqual(stat.CONTRACT, "ARFI-StatChartPreview/1.0.0")
        self.assertFalse(hasattr(stat, "predict"))
        self.assertFalse(hasattr(stat, "bayesian_shrinkage"))

    def test_invalid_inputs_fail_closed_not_silently_excluded(self):
        baseline = [{"value": 1., "availability": "available"}]
        invalid = [
            (lambda row: row.update(value=float("nan")), "finite"),
            (lambda row: row.update(value=float("inf")), "finite"),
            (lambda row: row.update(value=True), "finite"),
            (lambda row: row.update(value=2**80), "finite"),
            (lambda row: row.update(availability="guessed"), "missingness"),
            (lambda row: row.update(value=None), "null"),
            (lambda row: row.update(availability="not_available"), "cannot hide"),
        ]
        for mutate, expected in invalid:
            sample = copy.deepcopy(baseline)
            mutate(sample[0])
            with self.assertRaisesRegex(ValueError, expected):
                stat.histogram(sample, x="value")
        for bins in (-1, 0, 65, "unreviewed", True):
            with self.assertRaises(ValueError):
                stat.histogram(baseline, x="value", bins=bins)
        with self.assertRaisesRegex(ValueError, "column"):
            stat.histogram(baseline, x="row.value")
        with self.assertRaisesRegex(ValueError, "bounded"):
            stat.histogram(baseline * 100001, x="value")
        with self.assertRaisesRegex(ValueError, "unsupported filter"):
            stat.histogram(baseline, x="value", where={"value": [None]})
        with self.assertRaisesRegex(ValueError, "too many visible series"):
            stat.histogram([{"x":i,"group":str(i),"availability":"available"} for i in range(65)],
                           x="x",segment="group")

    def test_model_does_not_create_mean_only_or_auto_adjust_rating(self):
        ratings = [{"stars": 5, "availability": "available"}]*2 + [
            {"stars": 4, "availability": "available"}]*500
        histogram = valid(stat.histogram(ratings, x="stars", bins=2))
        self.assertEqual(sum(p["count"] for p in histogram["series"][0]["points"]), 502)
        self.assertNotIn("adjustedScore", json.dumps(histogram))
        self.assertNotIn("priorStrength", json.dumps(histogram))
        self.assertFalse(histogram["authority"]["statisticalInferenceAuthorized"])


if __name__ == "__main__":
    unittest.main()
