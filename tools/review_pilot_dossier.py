"""Generate and verify source-bound BLS evidence for a *future human* reviewer.

This is a deterministic preparation dossier, NOT an independent review
packet, a review decision, or permission to compare published sources.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = "bls-laus-state-unemployment-2025-e1625280119b26c3"
BASE = Path("publication/releases") / RELEASE
DECISION = Path("governance/decisions") / (RELEASE + "-owner-authorization.json")
OUTPUT = Path("governance/dossiers") / (RELEASE + "-pending.json")
SCOPES = ("rightsLicense","methodology","temporalInterpretation",
          "geographicUniverse","permittedPublicUses","cautions")
QUESTIONS = (
 "Verify actual rights and downstream redistribution permissions of original BLS sources.",
 "Independently replay BLS M13, series measure 03 and official source footnote G.",
 "Assess 11-month 2025 estimates versus Puerto Rico's full 12-month year.",
 "Confirm all 52 jurisdictions and identify unmatched or missing source records.",
 "Confirm whether publisher estimates may be used only in source-qualified displays.",
 "Document cautions, revision risks, uncertainty and unsupported causal inferences."
)

def demand(condition, message):
    if not condition:
        raise ValueError("BLS review dossier rejected: " + message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def read_json(path):
    return json.loads(path.read_bytes())

def canonical(record):
    return (json.dumps(record,sort_keys=True,indent=2,ensure_ascii=False)+"\n").encode("utf-8")

def generate(root=ROOT):
    root=Path(root)
    folder=root/BASE
    raw=(folder/"manifest.json").read_bytes()
    manifest=json.loads(raw)
    decision=read_json(root/DECISION)
    observations=read_json(folder/"observations.json")["observations"]
    demand(manifest["releaseId"] == RELEASE and manifest["status"] == "published" and
           manifest["geography"]["level"] == "state" and
           manifest["temporalCoverage"]["firstYear"] == 2025 and
           manifest["temporalCoverage"]["lastYear"] == 2025,
           "release and time identity mismatch")
    demand(decision["releaseId"] == RELEASE and
           decision["methodologyStatus"] == "pending" and
           decision["authorization"] == "owner_authorized" and
           decision["reviewEvidence"] is None and
           decision["manifestSha256"] == sha(raw) and
           decision["assetSha256"] == {key:v["sha256"] for key,v in manifest["assets"].items()},
           "owner-authorized source fingerprints must remain unchanged")
    for key, asset in manifest["assets"].items():
        raw_asset=(folder/asset["path"]).read_bytes()
        demand(sha(raw_asset) == asset["sha256"] and
               len(raw_asset) == asset["bytes"], "published asset digest mismatch: "+key)
    sources=[{"role":s["role"],"sha256":s["sha256"]} for s in manifest["sourceFiles"]]
    demand(sources == decision["originalSources"], "original publisher hashes changed")
    for source in manifest["sourceFiles"]:
        compressed=(folder/manifest["assets"][source["archiveAsset"]]["path"]).read_bytes()
        expanded=gzip.decompress(compressed)
        demand(len(expanded)==source["bytes"] and sha(expanded)==source["sha256"],
               "original BLS archive does not reproduce official source hash")
    demand(len(observations)==52 and len({x["geoid"] for x in observations})==52 and
           all(x["year"]==2025 and x["unit"]=="percent" and x["status"]=="available"
               and x["seasonalAdjustment"]=="not_seasonally_adjusted"
               for x in observations), "unexpected BLS rate universe or unit")
    deficient=[x for x in observations if x["annualAverageMonths"]==11]
    full=[x for x in observations if x["annualAverageMonths"]==12]
    demand(len(deficient)==51 and len(full)==1 and full[0]["geoid"]=="72" and
           all(x["footnoteCodes"]==["G"] and x["excludedMonths"]==["2025-10"] and
               x["sourcePeriodQualifier"]=="no_october_cps_2025" for x in deficient) and
           full[0]["footnoteCodes"]==[] and full[0]["excludedMonths"]==[] and
           full[0]["sourcePeriodQualifier"]=="full_12_months_2025",
           "BLS missing-October footnote or Puerto Rico exception corrupted")
    return {
        "contract":"ARFI-ReviewDossier/1.0.0",
        "status":"pending_independent_human_assessment",
        "releaseId":RELEASE,"datasetId":manifest["datasetId"],
        "indicatorId":"state-unemployment-rate",
        "publicationKind":"indicator",
        "sourceCommit":decision["sourceCommit"],
        "manifestSha256":decision["manifestSha256"],
        "assetSha256":decision["assetSha256"],
        "originalSources":manifest["sourceFiles"],
        "publisher":manifest["publishedSource"],
        "publicationMethod":manifest["method"],
        "scopeResults":{key:"not_independently_certified" for key in SCOPES},
        "questionsForReviewer":list(QUESTIONS),
        "sample": {
            "referenceYear":2025,"geographicLevel":"state",
            "observationCount":len(observations),"allAvailable":True,
            "reportedUnit":"percent","qualifierGCount":len(deficient),
            "elevenMonthGeographies":len(deficient),
            "excludedMonth":"2025-10",
            "twelveMonthGeographies":[x["geoid"] for x in full],
            "unreviewedUncertainty":"publisher rate estimates may be revised"
        },
        "rightsStatus":"independent_review_required",
        "reviewerLogin":None,"independentReviewEvidence":None,
        "derivedComparisonAuthorized":False,"causalInferenceAuthorized":False
    }

def verify(root=ROOT):
    saved=(Path(root)/OUTPUT).read_bytes()
    expected=canonical(generate(root))
    demand(saved==expected, "candidate dossier differs from verified immutable evidence")
    return {"status":"source_dossier_verified_not_human_approved",
            "releaseId":RELEASE,"sha256":sha(saved),"humanReviewCount":0}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify",action="store_true")
    args=parser.parse_args()
    print(json.dumps(verify() if args.verify else generate(),sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
