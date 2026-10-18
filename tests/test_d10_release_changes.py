"""D-10 synthetic revision-diff tests: stable bytes, precision, missingness, identities."""
import copy
import unittest

from tools.release_diff import build_changeset, canonical_bytes, verify_changeset
from tools.governance_transition import (check_revisions, check_review_transition,
                                         check_changeset_transition)


def pkg(rid, rows, dataset="source-dataset", geography="state", source="a"):
    manifest = {"releaseId": rid, "datasetId": dataset, "indicatorId": "indicator-one",
                "geography": {"level": geography, "joinKey": "geoid", "vintage": 2025},
                "temporalCoverage": {"firstYear": 2025, "lastYear": 2025, "vintage": 2025},
                "schemaVersion": "1.0.0",
                "sourceFiles": [{"role": "original", "sha256": source * 64}],
                "assets": {"observations": {"sha256": "f" * 64}},
                "method": "Source-preserving projection"}
    observations = {"datasetId": dataset, "indicatorId": "indicator-one",
                    "geography": geography, "observations": rows}
    return manifest, observations


def row(code, amount, **fields):
    return {"geoid": code, "year": 2025, "value": 1.25,
            "reportedAmount": amount, "status": "available", **fields}


class DeterministicChangeSetTests(unittest.TestCase):
    def setUp(self):
        self.old_m, self.old_o = pkg("v2025", [
            row("01", "-125.0000", referencePeriod="FY2025"),
            row("02", "0.00", lower95=12.5, upper95=19.0),
            row("03", "50.05"),
        ])
        self.new_m, self.new_o = pkg("v2026", [
            row("01", "-125.0001", referencePeriod="FY2026"),
            row("02", "0.00", lower95=12.0, upper95=19.0,
                status="suppressed", value=None),
            row("04", "15.5"),
        ], source="b")
        self.new_m["temporalCoverage"]["vintage"] = 2026

    def test_stable_byte_identical_and_field_sensitive(self):
        one = build_changeset(self.old_m, self.old_o, self.new_m, self.new_o)
        two = build_changeset(copy.deepcopy(self.old_m), copy.deepcopy(self.old_o),
                              copy.deepcopy(self.new_m), copy.deepcopy(self.new_o))
        self.assertEqual(canonical_bytes(one), canonical_bytes(two))
        self.assertEqual(one["counts"],
                         {"added": 1, "removed": 1, "revised": 2, "unchanged": 0})
        self.assertEqual(one["changes"], sorted(one["changes"],
                         key=lambda x: (x["key"]["geoid"], x["key"]["year"])))
        revised = one["changes"][0]["fields"]
        decimal = next(f for f in revised if f["field"] == "reportedAmount")
        self.assertEqual((decimal["before"], decimal["after"]), ("-125.0000", "-125.0001"))
        self.assertTrue(any(f["field"] == "referencePeriod" for f in revised))
        second = one["changes"][1]["fields"]
        self.assertTrue({"lower95", "status", "value"} <= {x["field"] for x in second})
        self.assertTrue(any(x["field"] == "sourceFiles" for x in one["manifestFields"]))
        self.assertTrue(any(x["field"] == "temporalCoverage.vintage"
                            for x in one["manifestFields"]))
        verify_changeset(one, self.old_m, self.old_o, self.new_m, self.new_o)

    def test_cannot_forge_diff_or_switch_datasets_or_geo_universe(self):
        report = build_changeset(self.old_m, self.old_o, self.new_m, self.new_o)
        report["counts"]["revised"] = 0
        with self.assertRaisesRegex(ValueError, "does not match"):
            verify_changeset(report, self.old_m, self.old_o, self.new_m, self.new_o)
        wrong = copy.deepcopy(self.new_m)
        wrong["datasetId"] = "other-publisher"
        foreign = copy.deepcopy(self.new_o)
        foreign["datasetId"] = "other-publisher"
        with self.assertRaisesRegex(ValueError, "cross-source"):
            build_changeset(self.old_m, self.old_o, wrong, foreign)
        wrong = copy.deepcopy(self.new_m)
        wrong["geography"]["joinKey"] = "other-id"
        with self.assertRaisesRegex(ValueError, "incompatible geography"):
            build_changeset(self.old_m, self.old_o, wrong, self.new_o)
        wrong = copy.deepcopy(self.new_m)
        wrong["releaseId"] = self.old_m["releaseId"]
        with self.assertRaisesRegex(ValueError, "fresh release"):
            build_changeset(self.old_m, self.old_o, wrong, self.new_o)
        duplicated = copy.deepcopy(self.new_o)
        duplicated["observations"].append(dict(duplicated["observations"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate geography"):
            build_changeset(self.old_m, self.old_o, self.new_m, duplicated)

    def test_missing_fields_and_numeric_decimal_type_are_not_silently_collapsed(self):
        from decimal import Decimal
        left_m, left_o = pkg("one", [row("01", "1.00")])
        right_m, right_o = pkg("two", [row("01", "1.00")])
        left_o["observations"][0]["lower95"] = Decimal("1.0001")
        right_o["observations"][0]["lower95"] = Decimal("1.0002")
        report = build_changeset(left_m, left_o, right_m, right_o)
        self.assertEqual(report["counts"]["revised"], 1)
        field = next(x for x in report["changes"][0]["fields"] if x["field"] == "lower95")
        self.assertEqual(field["before"], {"numericDecimal": "1.0001"})
        self.assertEqual(field["after"], {"numericDecimal": "1.0002"})


class AppendOnlyGovernanceTests(unittest.TestCase):
    def test_prior_decisions_cannot_change_or_disappear(self):
        p = "governance/decisions/baseline.json"
        q = "governance/decisions/next.json"
        old = {"schemaVersion": "1.0.0", "decisionPaths": [p]}
        new = {"schemaVersion": "1.0.0", "decisionPaths": [p, q]}
        self.assertEqual(check_review_transition(old, new, {p: "one"},
                         {p: "one", q: "two"})["newDecisions"], [q])
        for candidate, blobs in [
            ({"schemaVersion": "1.0.0", "decisionPaths": [q]}, {p: "one", q: "two"}),
            (new, {p: "forged", q: "two"}),
            (new, {p: "one"}),
            (new, {p: "one", q: "two", "governance/decisions/forged.json": "x"}),
        ]:
            with self.assertRaises(ValueError):
                check_review_transition(old, candidate, {p: "one"}, blobs)

    def test_published_revision_reports_are_immutable(self):
        old = {"governance/changesets/old--new.json": "sha-one"}
        self.assertEqual(check_changeset_transition(old, {**old,
            "governance/changesets/new--next.json": "sha-two"})["newChangeReports"],
            ["governance/changesets/new--next.json"])
        with self.assertRaisesRegex(ValueError, "changed or was deleted"):
            check_changeset_transition(old,
                {"governance/changesets/old--new.json": "modified"})
        with self.assertRaisesRegex(ValueError, "changed or was deleted"):
            check_changeset_transition(old, {})
        with self.assertRaisesRegex(ValueError, "orphan"):
            check_changeset_transition(old, {**old,
                "governance/changesets/forged--next.json": "fake"}, set())

    def test_same_dataset_requires_predecessor_and_exact_changeset(self):
        a, observations = pkg("old", [row("01", "-3.00")])
        b, updated = pkg("new", [row("01", "-3.01")])
        old = {"releases": [{"releaseId": "old"}]}
        proposed = {"releases": [{"releaseId": "old"},
                                 {"releaseId": "new", "predecessorReleaseId": "old"}]}
        report = build_changeset(a, observations, b, updated)
        args = (lambda _: a, lambda _: b, lambda _: observations,
                lambda _: updated)
        result = check_revisions(old, proposed, *args, lambda _: report)
        self.assertEqual(len(result["revisions"]), 1)
        revised = copy.deepcopy(proposed)
        del revised["releases"][1]["predecessorReleaseId"]
        with self.assertRaisesRegex(ValueError, "predecessor"):
            check_revisions(old, revised, *args, lambda _: report)
        tamper = copy.deepcopy(report)
        tamper["reportSha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "does not match"):
            check_revisions(old, proposed, *args, lambda _: tamper)
        with self.assertRaisesRegex(ValueError, "missing canonical"):
            check_revisions(old, proposed, *args, lambda _: None)


if __name__ == "__main__":
    unittest.main()
