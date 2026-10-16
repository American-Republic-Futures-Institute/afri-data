"""Source-to-source additive publication transition regression and tamper tests."""
import unittest
from tools.release_transition import check_transition, check_geography_transition


def release(rid):
    p=f"publication/releases/{rid}/"
    return {"releaseId":rid,"manifestPath":p+"manifest.json",
            "observationsPath":p+"observations.json","indicatorId":"original-indicator",
            "geography":"state","vintage":2025,
            "time":{"firstYear":2025,"lastYear":2025},"status":"published"}


def index(*items):
    return {"schemaVersion":"1.0.0","publicationStatus":"published",
            "releases":list(items)}


def blobs(*ids):
    out={}
    for rid in ids:
        base=f"publication/releases/{rid}/"
        out[base+"manifest.json"]="sha-manifest-"+rid
        out[base+"observations.json"]="sha-observations-"+rid
    return out


class ReleaseTransitionTests(unittest.TestCase):
    def setUp(self):
        self.old=index(release("census-2025"))
        self.files=blobs("census-2025")

    def test_adding_independent_source_is_valid(self):
        result=check_transition(self.old,index(release("census-2025"),release("bls-2025")),
                                self.files,blobs("census-2025","bls-2025"))
        self.assertEqual(result["newReleases"],["bls-2025"])

    def test_cannot_drop_previous_reviewed_release(self):
        with self.assertRaisesRegex(ValueError,"approved release removed"):
            check_transition(self.old,index(),self.files,self.files)

    def test_cannot_mutate_index_entry_of_previous_release(self):
        changed=release("census-2025");changed["vintage"]=2026
        with self.assertRaisesRegex(ValueError,"index entry changed"):
            check_transition(self.old,index(changed),self.files,self.files)

    def test_cannot_change_existing_asset_hash_or_contents(self):
        changed=dict(self.files);changed["publication/releases/census-2025/observations.json"]="modified"
        with self.assertRaisesRegex(ValueError,"immutable approved source"):
            check_transition(self.old,self.old,self.files,changed)

    def test_cannot_add_file_to_existing_release(self):
        changed=dict(self.files);changed["publication/releases/census-2025/unreviewed.csv"]="x"
        with self.assertRaisesRegex(ValueError,"immutable approved source"):
            check_transition(self.old,self.old,self.files,changed)

    def test_cannot_publish_unindexed_file(self):
        changed=dict(self.files);changed["publication/releases/unknown-source/foo.json"]="x"
        with self.assertRaisesRegex(ValueError,"Unregistered"):
            check_transition(self.old,self.old,self.files,changed)

    def test_new_release_requires_both_manifest_and_observations(self):
        changed=dict(self.files);changed["publication/releases/next/manifest.json"]="x"
        with self.assertRaisesRegex(ValueError,"missing its manifest or canonical observations"):
            check_transition(self.old,index(release("census-2025"),release("next")),self.files,changed)

    def test_duplicate_index_rejected(self):
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            check_transition(self.old,index(release("census-2025"),release("census-2025")),
                             self.files,self.files)



def geo_entry(rid):
    prefix=f"publication/geographies/releases/{rid}/"
    return {"releaseId":rid,"status":"published","geography":"county",
            "manifestPath":prefix+"manifest.json",
            "geometryPath":prefix+"counties.geojson","vintage":2023,"features":3143}


def geo_index(*items):
    return {"schemaVersion":"1.0.0","publicationStatus":"published",
            "releases":list(items)}


def geo_blobs(*ids):
    result={}
    for rid in ids:
        prefix=f"publication/geographies/releases/{rid}/"
        for name in ("manifest.json","counties.geojson","original.zip"):
            result[prefix+name]=f"{rid}-{name}"
    return result


class GeographyTransitionTests(unittest.TestCase):
    def test_can_add_independent_county_reference_without_statistics(self):
        rid="census-county-2023"
        got=check_geography_transition(None,geo_index(geo_entry(rid)),
                                       {},geo_blobs(rid))
        self.assertEqual(got["newGeographies"],[rid])

    def test_approved_geography_cannot_be_dropped(self):
        rid="census-county-2023"
        with self.assertRaisesRegex(ValueError,"approved geography release removed"):
            check_geography_transition(geo_index(geo_entry(rid)),geo_index(),
                                       geo_blobs(rid),geo_blobs(rid))

    def test_approved_geography_bytes_cannot_be_rewritten(self):
        rid="census-county-2023"
        changed=geo_blobs(rid)
        changed[f"publication/geographies/releases/{rid}/original.zip"]="tampered"
        with self.assertRaisesRegex(ValueError,"immutable approved geography"):
            check_geography_transition(geo_index(geo_entry(rid)),geo_index(geo_entry(rid)),
                                       geo_blobs(rid),changed)

    def test_unindexed_geography_blob_rejected(self):
        with self.assertRaisesRegex(ValueError,"Unregistered geography"):
            check_geography_transition(None,geo_index(),{},
                                       {"publication/geographies/releases/unknown/fake.bin":"x"})
