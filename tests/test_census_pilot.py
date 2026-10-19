"""STAT-02A.2 source-bound Census pilot regression and denial tests."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from arfi_stats import METHODS
from arfi_stats.artifacts import ROOT, StatArtifactError, hash_json
from arfi_stats.census_pilot import (
    CHART_TYPES, CensusPilotError, _source, main, produce, replay,
)


def replace(artifact, path, value):
    candidate = copy.deepcopy(artifact)
    current = candidate
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value
    candidate["artifactSha256"] = hash_json({
        k: v for k, v in candidate.items() if k != "artifactSha256"
    })
    return candidate


class SourceBoundCensusPilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = {kind: produce(kind) for kind in CHART_TYPES}

    def test_all_methods_are_exactly_source_bound_and_nonpublishing(self):
        for kind in CHART_TYPES:
            with self.subTest(kind=kind):
                artifact = self.reference[kind]
                self.assertEqual(artifact, produce(kind))
                self.assertEqual(artifact["sourceIdentity"]["selectedJurisdictions"], 52)
                self.assertEqual(artifact["sourceIdentity"]["sourceRows"], 312)
                self.assertEqual(artifact["sourceIdentity"]["selectedYear"], 2025)
                self.assertEqual(artifact["computation"]["methodId"], METHODS[kind])
                self.assertEqual(artifact["chart"]["chartType"], kind)
                self.assertEqual(artifact["chart"]["selection"]["inputRows"], 52)
                self.assertEqual(artifact["chart"]["selection"]["selectedRows"], 52)
                self.assertEqual(artifact["chart"]["series"][0]["n"], 52)
                self.assertEqual(artifact["chart"]["selection"]["missingness"]["available"], 52)
                self.assertIn("UNWEIGHTED_JURISDICTIONS_NOT_RESIDENTS",
                              artifact["eligibility"]["reasonCodes"])
                self.assertEqual(artifact["eligibility"]["decision"], "qualified")
                self.assertFalse(artifact["authority"]["publicationAuthorized"])
                self.assertFalse(artifact["eligibility"]["publicationAuthorized"])
                self.assertFalse(artifact["chart"]["authority"]["publicationAuthorized"])
                self.assertTrue(artifact["authority"]["sourceIdentityVerified"])
                self.assertFalse(artifact["chart"]["authority"]["sourceVerified"])
                self.assertEqual(artifact["authority"]["independentReviewStatus"],
                                 "not_independently_certified")
                self.assertIn("jurisdiction", artifact["quality"]["limitations"][1])
                self.assertEqual(replay(artifact), {
                    "replay": "deterministic-match",
                    "artifactSha256": artifact["artifactSha256"],
                    "sourceIdentityVerified": True,
                    "publicationAuthorized": False,
                    "independentReviewStatus": "not_independently_certified",
                })
        self.assertEqual(len({a["artifactSha256"] for a in self.reference.values()}), 3)

    def test_exact_source_2025_selection_and_no_state_omission(self):
        profile, rows = _source()
        self.assertEqual(len(rows), 52)
        self.assertEqual(len({row["fips"] for row in rows}), 52)
        self.assertTrue(all(row["year"] == 2025 for row in rows))
        self.assertTrue(all(row["availability"] == "available" for row in rows))
        self.assertEqual(profile["measurement"]["unit"], "persons")
        self.assertEqual([row["fips"] for row in rows],
                         sorted(row["fips"] for row in rows))
        self.assertEqual(rows[[row["fips"] for row in rows].index("72")]["fips"], "72")

    def test_schema_independently_verifies_chart_and_strict_authority(self):
        artifact_schema = json.loads(
            (ROOT / "contracts/stat-source-pilot-artifact.schema.json").read_text())
        chart_schema = json.loads(
            (ROOT / "contracts/stat-chart-preview.schema.json").read_text())
        registry = Registry().with_resources([
            (chart_schema["$id"], Resource.from_contents(chart_schema)),
        ])
        validator = Draft202012Validator(artifact_schema, registry=registry)
        good = self.reference["histogram"]
        self.assertTrue(validator.is_valid(good))
        for path, value in [
            (("authority", "publicationAuthorized"), True),
            (("authority", "independentReviewStatus"), "approved"),
            (("authority", "crossSourceAuthorized"), True),
            (("eligibility", "decision"), "permitted"),
            (("eligibility", "methodApplicable"), False),
            (("analysisRequest", "otherReleaseIds"), ["other-release"]),
            (("chart", "authority", "sourceVerified"), True),
            (("sourceIdentity", "selectedJurisdictions"), 51),
            (("quality", "unitOfAnalysis"), "individual-resident"),
        ]:
            with self.subTest(path=path):
                candidate = replace(good, path, value)
                self.assertFalse(validator.is_valid(candidate))

    def test_replay_refuses_checksum_and_recomputed_tampering(self):
        good = self.reference["boxplot"]
        changed = copy.deepcopy(good)
        changed["quality"]["sourcePeriod"] = "July 1, 2024"
        with self.assertRaises((CensusPilotError, StatArtifactError)):
            replay(changed)
        for path, value in [
            (("chart", "series", 0, "n"), 51),
            (("sourceIdentity", "selectedInputSha256"), "a" * 64),
            (("sourceIdentity", "sourceCommit"), "a" * 40),
            (("analysisRequest", "observationsSha256"), "b" * 64),
            (("computation", "coreSha256"), "c" * 64),
            (("computation", "numpyVersion"), "999.0.0"),
            (("quality", "sourceCaveats"), ["Replacement with a plausible new text."]),
            (("eligibility", "requestFingerprint"), "d" * 64),
        ]:
            with self.subTest(path=path):
                candidate = replace(good, path, value)
                with self.assertRaises((CensusPilotError, StatArtifactError)):
                    replay(candidate)

    def test_denies_unverified_source_eligibility_and_malformed_selection(self):
        with self.assertRaisesRegex(CensusPilotError, "method"):
            produce("scatter")
        with self.assertRaisesRegex(CensusPilotError, "method"):
            produce("time-series")
        with self.assertRaisesRegex(CensusPilotError, "method"):
            produce("frequency")
        with patch("arfi_stats.census_pilot.verify_profile",
                   side_effect=ValueError("mismatched published evidence")):
            with self.assertRaises(ValueError):
                produce("histogram")
        source_profile, rows = _source()
        for mutation in ("duplicate", "missing", "invalid"):
            candidate = copy.deepcopy(rows)
            if mutation == "duplicate":
                candidate[1]["fips"] = candidate[0]["fips"]
            elif mutation == "missing":
                candidate.pop()
            else:
                candidate[0]["value"] = -1
            with self.subTest(mutation=mutation), patch(
                "arfi_stats.census_pilot._source",
                return_value=(source_profile, candidate)
            ):
                with self.assertRaises(CensusPilotError):
                    produce("histogram")
        with patch("arfi_stats.census_pilot.evaluate",
                   return_value={"decision": "denied"}):
            with self.assertRaises(Exception):
                produce("histogram")

    def test_cli_generates_new_file_replays_and_rejects_repo_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pilot.json"
            self.assertEqual(main(["produce", "--kind", "ecdf",
                                   "--output", str(path)]), 0)
            self.assertTrue(path.exists())
            self.assertEqual(main(["replay", "--artifact", str(path)]), 0)
            with self.assertRaises(StatArtifactError):
                main(["produce", "--kind", "ecdf", "--output", str(path)])
        with self.assertRaises(CensusPilotError):
            main(["produce", "--kind", "histogram",
                  "--output", str(ROOT / "examples/forbidden-stat-pilot.json")])


if __name__ == "__main__":
    unittest.main()
