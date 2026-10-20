"""STAT-07A: synthetic compatibility, identity, and fail-closed publication tests."""
import copy
import hashlib
import json
import unittest

from tools.stat07_curation import CurationError, canonical_bytes, validate_recipe, validate_candidate


def source(release, indicator, vintage, unit, period, code="geoid"):
    doc={"indicatorId":indicator,"joinKey":code,"geography":"state",
         "observations":[{code:"01","year":2024,"unit":unit,"status":"available","value":100}]}
    raw=canonical_bytes(doc)
    manifest={"releaseId":release,"status":"published",
              "geography":{"level":"state","vintage":vintage},
              "assets":{"observations":{"sha256":hashlib.sha256(raw).hexdigest()}}}
    entry={"releaseId":release,"indicatorId":indicator,"status":"published"}
    inp={"releaseId":release,"sourceCommit":"a"*40,
         "observationsSha256":hashlib.sha256(raw).hexdigest(),
         "geographyKey":code,"selectionYear":2024,"temporalInterpretation":period,"measurementUnit":unit}
    return entry, (manifest,raw), inp


def example():
    a=source("census-population","population",2025,"persons","July 1 2025 resident population")
    b=source("acs-income","income",2024,"USD","2020-2024 pooled household median")
    index={"publicationStatus":"published","releases":[a[0],b[0]]}
    manifests={a[0]["releaseId"]:a[1],b[0]["releaseId"]:b[1]}
    recipe={"schemaVersion":"1.0.0","type":"ARFI-DataProductRecipe",
      "productId":"state-population-income-context","inputs":[a[2],b[2]],
      "compatibility":{"geographyLevel":"state","geographyIdentity":"census-fips",
       "boundaryVintages":[2025,2024],
       "temporalAlignment":"separate-source-native-periods",
       "populationComparability":"not-asserted","expectedCardinality":"one-to-one",
       "missingnessPolicy":"preserve-explicit-null-and-omissions",
       "uncertaintyPolicy":"preserve-publisher-native-uncertainty",
       "acceptedRisks":["Incompatible July 2025 and 2020-2024 pooled survey periods are shown separately"]},
      "operation":{"kind":"source-preserving-join","joinType":"inner",
       "preserveSourceColumns":True,"formulas":[]},
      "authority":{"status":"candidate-only","publicPublicationAuthorized":False,
       "crossSourceStatisticalDerivationAuthorized":False,"causalInferenceAuthorized":False}}
    product={"schemaVersion":"1.0.0","type":"ARFI-DerivedDataProduct",
      "productId":recipe["productId"],
      "recipeSha256":hashlib.sha256(canonical_bytes(recipe)).hexdigest(),
      "inputIdentities":[{k:v for k,v in i.items() if k in
       ("releaseId","sourceCommit","observationsSha256")} for i in recipe["inputs"]],
      "output":{"observationsSha256":"b"*64,"rowCount":1,"geographyKey":"fips",
       "lineageColumns":["population_source","income_source"]},
      "quality":{"unmatchedInputGeographies":[],"missingSourceValues":0,
       "duplicateKeys":0,"omissionLedger":[]},
      "authority":{"status":"unreviewed-candidate","publicPublicationAuthorized":False,
       "statisticalInferenceAuthorized":False,"causalInferenceAuthorized":False}}
    return index,manifests,recipe,product


class CurationContractTests(unittest.TestCase):
    def test_valid_source_preserving_candidate_does_not_grant_publication(self):
        idx,sources,recipe,product=example()
        decision=validate_recipe(recipe,idx,sources)
        self.assertTrue(decision["candidateOnly"])
        self.assertFalse(decision["publicPublicationAuthorized"])
        self.assertFalse(decision["statisticalDerivationAuthorized"])
        self.assertFalse(validate_candidate(recipe,product)["publicPublicationAuthorized"])

    def test_reject_source_hash_and_temporal_substitution(self):
        idx,sources,recipe,_=example()
        recipe["inputs"][0]["observationsSha256"]="f"*64
        with self.assertRaisesRegex(CurationError,"SHA-256"):validate_recipe(recipe,idx,sources)
        idx,sources,recipe,_=example()
        recipe["compatibility"]["temporalAlignment"]="matched-source-periods"
        with self.assertRaisesRegex(CurationError,"periods"):validate_recipe(recipe,idx,sources)

    def test_reject_duplicate_cardinality_and_geography_vintage(self):
        idx,sources,recipe,_=example()
        recipe["compatibility"]["boundaryVintages"]=[2024,2024]
        with self.assertRaisesRegex(CurationError,"vintages"):validate_recipe(recipe,idx,sources)
        idx,sources,recipe,_=example()
        release=recipe["inputs"][0]["releaseId"]
        manifest,raw=sources[release]
        doc=json.loads(raw)
        doc["observations"].append(copy.deepcopy(doc["observations"][0]))
        updated=canonical_bytes(doc)
        manifest["assets"]["observations"]["sha256"]=hashlib.sha256(updated).hexdigest()
        sources[release]=(manifest,updated)
        recipe["inputs"][0]["observationsSha256"]=hashlib.sha256(updated).hexdigest()
        with self.assertRaisesRegex(CurationError,"one observation"):validate_recipe(recipe,idx,sources)

    def test_source_period_selection_rejects_unpublished_year(self):
        idx,sources,recipe,_=example()
        recipe["inputs"][0]["selectionYear"]=2026
        with self.assertRaisesRegex(CurationError,"No published rows"):
            validate_recipe(recipe,idx,sources)

    def test_derivations_and_fabricated_approval_fail_at_schema_boundary(self):
        idx,sources,recipe,product=example()
        recipe["operation"]["formulas"]=["population/income"]
        with self.assertRaises(CurationError):validate_recipe(recipe,idx,sources)
        idx,sources,recipe,product=example()
        recipe["authority"]["publicPublicationAuthorized"]=True
        with self.assertRaises(CurationError):validate_recipe(recipe,idx,sources)
        idx,sources,recipe,product=example()
        product["authority"]["publicPublicationAuthorized"]=True
        with self.assertRaises(CurationError):validate_candidate(recipe,product)
        idx,sources,recipe,product=example()
        product["recipeSha256"]="f"*64
        with self.assertRaisesRegex(CurationError,"exact deterministic recipe"):validate_candidate(recipe,product)


if __name__=="__main__":
    unittest.main()
