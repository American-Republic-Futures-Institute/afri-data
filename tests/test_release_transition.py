"""Source-to-source additive publication transition regression and tamper tests."""
import unittest
from tools.release_transition import check_transition


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
