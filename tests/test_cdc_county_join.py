"""Synthetic-only county join regression; never published as evidence."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from pipelines.census_county_geography import STATES
from tools.cdc_county_join import reconcile_counties, validate_published_county_join


def fixtures():
    state_codes=sorted(STATES-{"21","42","48"})
    base,extra=divmod(3144-(120+67+254),len(state_codes))
    counts={s:base+(1 if i<extra else 0) for i,s in enumerate(state_codes)}
    counts.update({"21":120,"42":67,"48":254})
    features=[]
    rows=[]
    for state,n in sorted(counts.items()):
        counties=(list(range(1,n+1)) if state!="48"
                  else list(range(1,254))+[301])
        for county in counties:
            geoid=state+str(county).zfill(3)
            name="Loving" if geoid=="48301" else "Synthetic County "+geoid
            features.append({
                "id":geoid,"type":"Feature",
                "properties":{"GEOID":geoid,"STATEFP":state,
                              "COUNTYFP":str(county).zfill(3),
                              "NAME":name,"vintage":2023},
            })
            if geoid=="48301":
                continue
            unavailable=state in {"21","42"}
            rows.append({
                "geoid":geoid,"year":2023,"publisherVintage":2025,
                "referencePeriod":"2023 BRFSS source for obesity measure",
                "statistic":"model_based_estimate","unit":"percent",
                "value":None if unavailable else 35.4,
                "status":"not_available" if unavailable else "available",
                "confidenceInterval95":None if unavailable else "(31.2, 39.7)",
                "lower95":None if unavailable else 31.2,
                "upper95":None if unavailable else 39.7,
            })
    assert len(features)==3144 and len(rows)==3143
    geo={"type":"FeatureCollection",
         "metadata":{"publisher":"U.S. Census Bureau","joinKey":"GEOID","vintage":2023},
         "features":features}
    cdc={"schemaVersion":"1.0.0",
         "indicatorId":"county-modeled-obesity-prevalence",
         "geography":"county","joinKey":"geoid","vintage":2025,
         "observations":rows}
    return geo,cdc


class CountyJoinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference_geo,cls.reference_cdc=fixtures()

    def setUp(self):
        self.geography=deepcopy(self.reference_geo)
        self.cdc=deepcopy(self.reference_cdc)

    def test_source_releases_join_without_inferred_loving_county_value(self):
        result=reconcile_counties(self.geography,self.cdc)
        self.assertEqual(result["geometryPolygons"],3144)
        self.assertEqual(result["matchedGeographies"],3143)
        self.assertEqual(result["explicitlyUnavailableEstimates"],187)
        self.assertEqual(result["availableModeledEstimates"],2956)
        self.assertEqual(result["unavailableByStateFips"],{"21":120,"42":67})
        self.assertEqual(result["censusOnly"],[{
            "geoid":"48301","name":"Loving","stateFips":"48",
            "reason":"no_observation_in_cdc_places_2025","value":None
        }])
        self.assertEqual(result["cdcOnly"],[])

    def test_duplicate_geometry_geoid_rejected(self):
        self.geography["features"][-1]=deepcopy(self.geography["features"][0])
        with self.assertRaisesRegex(ValueError,"Duplicate Census"):
            reconcile_counties(self.geography,self.cdc)

    def test_duplicate_cdc_geoid_rejected(self):
        self.cdc["observations"][-1]=deepcopy(self.cdc["observations"][0])
        with self.assertRaisesRegex(ValueError,"Duplicate CDC"):
            reconcile_counties(self.geography,self.cdc)

    def test_unknown_cdc_geoid_rejected_without_imputation(self):
        self.cdc["observations"][0]["geoid"]="48999"
        with self.assertRaisesRegex(ValueError,"no approved county geometry"):
            reconcile_counties(self.geography,self.cdc)

    def test_loving_injected_as_observed_record_is_a_contract_change(self):
        self.cdc["observations"][0]["geoid"]="48301"
        with self.assertRaisesRegex(ValueError,"Unexpected Census-only"):
            reconcile_counties(self.geography,self.cdc)

    def test_missing_boundary_rejected(self):
        self.geography["features"]=self.geography["features"][:-1]
        with self.assertRaisesRegex(ValueError,"Census county geography contract"):
            reconcile_counties(self.geography,self.cdc)

    def test_null_estimate_is_not_zero(self):
        ky=next(r for r in self.cdc["observations"] if r["geoid"].startswith("21"))
        ky["value"]=0.0
        with self.assertRaisesRegex(ValueError,"fabricated modeled value"):
            reconcile_counties(self.geography,self.cdc)

    def test_improper_null_confidence_interval_rejected(self):
        pa=next(r for r in self.cdc["observations"] if r["geoid"].startswith("42"))
        pa["confidenceInterval95"]="(0, 0)"
        with self.assertRaisesRegex(ValueError,"fabricated modeled value"):
            reconcile_counties(self.geography,self.cdc)

    def test_bad_publisher_year_or_reference_period_rejected(self):
        self.cdc["observations"][0]["year"]=2025
        with self.assertRaisesRegex(ValueError,"statistic or reference period"):
            reconcile_counties(self.geography,self.cdc)

    def test_wrong_source_geometry_identity_rejected(self):
        self.geography["features"][0]["properties"]["STATEFP"]="99"
        with self.assertRaisesRegex(ValueError,"Geographic identity mismatch"):
            reconcile_counties(self.geography,self.cdc)

    def test_nonfinite_and_out_of_bounds_model_interval_rejected(self):
        valid=next(r for r in self.cdc["observations"] if r["status"]=="available")
        valid["upper95"]=float("nan")
        with self.assertRaisesRegex(ValueError,"confidence interval invalid"):
            reconcile_counties(self.geography,self.cdc)

    def test_changed_missingness_requires_methodology_review(self):
        ky=next(r for r in self.cdc["observations"] if r["geoid"].startswith("21"))
        ky.update({"status":"available","value":35.4,"lower95":31.2,
                   "upper95":39.7,"confidenceInterval95":"(31.2, 39.7)"})
        with self.assertRaisesRegex(ValueError,"availability footprint changed"):
            reconcile_counties(self.geography,self.cdc)

    def test_no_release_approval_does_not_claim_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/"publication").mkdir()
            (root/"publication/index.json").write_text(json.dumps(
                {"schemaVersion":"1.0.0","releases":[]}))
            outcome=validate_published_county_join(root)
            self.assertEqual(outcome["countyJoinStatus"],
                             "waiting-for-both-approved-source-releases")
