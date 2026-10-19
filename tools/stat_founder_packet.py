"""STAT-02C.1 -- construct the exact founder method review packet, but NEVER approve it.

The producer makes the founder declare real conflicts. --inspect is read-only
and may be run in CI to collect exact fingerprints without publication.
No approval event or method ledger entry is created by this tool.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys

from arfi_stats.artifacts import ROOT, hash_json, canonical_bytes
from tools.stat_approval import checked, sha_bytes
from tools.stat_founder import (
    CONFLICT_PREFIX, DECISION, OWNER, RELEASE, candidate, require, source_is_owner_authorized,
)

PACKET_PATH = "governance/stat-founder/packets/census-2025-histogram.json"
SCHEMA = "stat-founder-method-packet.schema.json"
FIELDS = ("rightsLicense", "methodology", "temporalInterpretation",
          "geographicUniverse", "permittedPublicUses", "cautions")

FINDINGS = {
    "rightsLicense": (
        "The published input identifies the United States Census Bureau as source; "
        "the original Vintage 2025 NST-EST2025-ALLDATA.csv and cartographic archive "
        "URLs, SHA-256 digests, manifest and observations are preserved in the "
        "Census publication release. Federal government source material is "
        "generally public domain under 17 U.S.C. 105; that does not certify "
        "rights in every third-party component or endorsement of this derived view. "
        "The actual publisher source notice and redistribution conditions require "
        "the founder's review before signing."
    ),
    "methodology": (
        "Histogram is the deterministic ARFI StatKit numpy.histogram/1 method "
        "operating on 52 positive, source-native integer population estimates, "
        "one per state-equivalent geography in 2025. Bins are selected using "
        "NumPy's Freedman-Diaconis rule (bins=fd) with count scale. No custom "
        "weighting, interpolation, imputation, per-capita conversion, smoothing, "
        "new interval or cross-source join is authorized. The exact candidate, "
        "StatKit implementation digests, NumPy version, histogram bin edges "
        "and counts must replay identically to the published source."
    ),
    "temporalInterpretation": (
        "Each observation is the Census Vintage 2025 estimated resident "
        "population for July 1, 2025. Vintage identifies the estimate release; "
        "neither the histogram nor the year implies a direct census count on "
        "that day, continuous measurement, short-term forecast, causal trend "
        "or comparability to differently revised vintages."
    ),
    "geographicUniverse": (
        "The complete source-bound 2025 scope is exactly 50 States, the "
        "District of Columbia and Puerto Rico, identified by their distinct "
        "two-character Census FIPS codes. Each of the 52 jurisdictions supplies "
        "one equally weighted observation; it is not a resident-weighted "
        "population distribution. The source-bound pilot verifies exact "
        "membership, sorting, positive integers, values and availability, "
        "not merely an arbitrary set of 52 records."
    ),
    "permittedPublicUses": (
        "Publication permits a descriptive educational visualization and "
        "its accessible table of jurisdiction-level Census population-estimate "
        "frequency bins. This is an ARFI founder-reviewed analysis, expressly "
        "not independent certification or a Census-published histogram. "
        "No citizen-level inference, statistical significance, policy "
        "effectiveness ranking, causal inference, counterfactual modeling or "
        "cross-source correlation is authorized."
    ),
    "cautions": (
        "Estimates are modeled publisher measurements, not exact enumerations. "
        "Large jurisdictions contribute only one observation just as small "
        "jurisdictions do; visual frequencies describe jurisdictions and not "
        "persons. Bin selection affects the chart's appearance, and "
        "Freedman-Diaconis does not supply uncertainty intervals, standard "
        "errors or validity outside the selected 2025 release. Original "
        "source caveats and missingness must remain inspectable alongside "
        "each public presentation."
    ),
}


def evidence():
    c = candidate()
    source = source_is_owner_authorized(c)
    manifest = ROOT / "publication/releases" / RELEASE / "manifest.json"
    return {
        "candidateSha256": hash_json(c),
        "chartSha256": c["methodIdentity"]["chartSha256"],
        "observationsSha256": c["sourceIdentity"]["observationsSha256"],
        "sourceManifestSha256": sha_bytes(manifest.read_bytes()),
        "sourceDecisionId": source["decisionId"],
        "methodId": c["methodIdentity"]["methodId"],
        "methodVersion": c["methodIdentity"]["methodVersion"],
        "sourceCommit": c["sourceIdentity"]["sourceCommit"],
        "sourceYear": c["sourcePilot"]["sourceIdentity"]["selectedYear"],
        "jurisdictions": c["sourceIdentity"]["selectedJurisdictions"],
        "limitations": c["interpretation"]["limitations"],
        "packetPath": PACKET_PATH,
    }


def build_packet(disclosure: str):
    if type(disclosure) is not str or not (64 <= len(disclosure.strip()) <= 4000):
        raise ValueError(
            "Actual conflict-of-interest disclosure must be provided by the "
            "founder (64-4000 characters); not a generated or placeholder statement"
        )
    statement = disclosure.strip()
    # Never silently coerce a placeholder or a known incomplete declaration
    # into a formal method sign-off.
    if any(token in statement.lower() for token in (
        "to be confirmed", "not yet provided", "pending founder", "tbd",
        "not yet declared", "to be disclosed", "placeholder",
    )):
        raise ValueError("Pending conflict disclosure may not enter the approved packet")
    refs = evidence()
    packet = {
        "contract": "ARFI-FounderStatMethodPacket/1.0.0",
        "sourceReleaseId": RELEASE,
        "sourceDecisionId": DECISION,
        "candidateSha256": refs["candidateSha256"],
        "methodId": refs["methodId"],
        "methodVersion": refs["methodVersion"],
        "chartSha256": refs["chartSha256"],
        "observationsSha256": refs["observationsSha256"],
        "sourceManifestSha256": refs["sourceManifestSha256"],
        "periodYear": 2025,
        "unitOfAnalysis": "state-equivalent-jurisdiction",
        "approvalClass": "founder-reviewed-not-independent",
        "reviewScope": {field: "reviewed-with-cautions" for field in FIELDS},
        "findings": {**FINDINGS, "conflictOfInterest": CONFLICT_PREFIX + statement},
        "limitations": refs["limitations"],
        "reviewerLogin": OWNER,
    }
    return checked(packet, SCHEMA)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate exact founder Census review packet (NOT authorization)"
    )
    parser.add_argument("command", choices=("inspect", "packet", "chart-fixture"))
    parser.add_argument("--conflict-disclosure", help="Founder's complete, truthful COI statement")
    args = parser.parse_args(argv)
    if args.command != "packet" and args.conflict_disclosure:
        parser.error("inspect takes no conflict disclosure")
    if args.command == "packet" and not args.conflict_disclosure:
        parser.error("packet requires an actual founder-provided --conflict-disclosure")
    if args.command == "chart-fixture":
        chart = candidate()["sourcePilot"]["chart"]
        print("STAT_CHART_CANONICAL_BASE64=" +
              base64.b64encode(canonical_bytes(chart)).decode("ascii"))
        return 0
    result = evidence() if args.command == "inspect" else build_packet(args.conflict_disclosure)
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True,
                                ensure_ascii=False, allow_nan=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
