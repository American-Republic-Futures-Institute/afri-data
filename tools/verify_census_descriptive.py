"""STAT-03: deterministic Census descriptive chart publication, no review ceremony.

Recompute the actual method over already published immutable Census input.
Validating source/method/numbers is technical data quality, not a claim of
scientific certification. Never mutate source-native publisher releases.
"""
import json
from pathlib import Path
from arfi_stats.artifacts import ROOT, hash_json
from arfi_stats.publication_gate import candidate_from_pilot

FILE = ROOT / "publication/descriptive/census-2025-state-population-histogram.json"
ID = "census-2025-state-population-histogram"
EXACT_FIELDS = {
    "schemaVersion", "type", "id", "publicationStatus", "reviewStatus",
    "dataset", "publisher", "analysisProducer", "geography", "sourceYear",
    "sourcePeriod", "sourceCommit", "sourceManifestSha256",
    "observationsSha256", "chartSha256", "unitOfAnalysis",
    "populationWeighted", "selectedJurisdictions", "method",
    "limitations", "chart",
}

def verify(artifact=None):
    candidate = candidate_from_pilot("histogram")
    original = candidate["sourcePilot"]
    art = json.loads(FILE.read_text("utf8")) if artifact is None else artifact
    expected = {
        "schemaVersion": "1.0.0",
        "type": "ARFI-ReproducibleDescriptiveChart/1.0.0",
        "id": ID,
        "publicationStatus": "published-reproducible-descriptive",
        "reviewStatus": "not-independently-reviewed",
        "dataset": original["sourceIdentity"]["releaseId"],
        "publisher": "U.S. Census Bureau",
        "analysisProducer": "American Republic Futures Institute",
        "geography": "50 states, District of Columbia and Puerto Rico",
        "sourceYear": original["sourceIdentity"]["selectedYear"],
        "sourcePeriod": original["quality"]["sourcePeriod"],
        "sourceCommit": original["sourceIdentity"]["sourceCommit"],
        "sourceManifestSha256": "5ea73893a9d343f907979c67ac7fe4d7b85784483ff36df94d6311fc7499c4de",
        "observationsSha256": original["sourceIdentity"]["observationsSha256"],
        "chartSha256": hash_json(original["chart"]),
        "unitOfAnalysis": "state-equivalent-jurisdiction",
        "populationWeighted": False,
        "selectedJurisdictions": 52,
        "method": original["computation"]["methodId"],
        "limitations": [
            "Every observation is a Census published demographic estimate, not an exact enumeration.",
            "The distribution gives each jurisdiction one observation regardless of the resident population.",
            "Neither individual-resident population inference nor policy performance rankings are supported.",
            "This is a reproducible ARFI descriptive visualization and has not undergone independent methodology review.",
        ],
        "chart": original["chart"],
    }
    if type(art) is not dict or set(art) != EXACT_FIELDS or art != expected:
        differences = [
            key for key in sorted(set(expected) | set(art))
            if art.get(key) != expected.get(key)
        ]
        raise ValueError(
            "STAT-03: descriptive artifact differs from the exact Census source replay "
            "at " + ",".join(differences)
        )
    if hash_json(art["chart"]) != art["chartSha256"]:
        raise ValueError("STAT-03: embedded chart does not match its canonical SHA")
    points = art["chart"]["series"][0]["points"]
    if not (art["selectedJurisdictions"] == 52 and
            sum(point["count"] for point in points) == 52 and
            art["chart"]["selection"]["missingness"]["available"] == 52 and
            all(art["chart"]["authority"][k] is False for k in (
                "publicationAuthorized","sourceVerified","crossSourceAuthorized",
                "statisticalInferenceAuthorized","causalInferenceAuthorized"
            ))):
        raise ValueError("STAT-03: chart denominator or preview authority changed")
    return {
        "status": "reproduced",
        "id": ID,
        "jurisdictions": 52,
        "bins": len(points),
        "chartSha256": expected["chartSha256"],
        "reviewStatus": expected["reviewStatus"],
    }

if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
