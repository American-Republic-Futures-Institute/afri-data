"""County geometry-to-source identity matching, without any fabricated rates."""
import unittest

from tools.geography_crosswalk import reconcile_county_geoids


class GeographyCrosswalkTests(unittest.TestCase):
    def test_cdc_loving_county_is_explicit_no_measurement(self):
        geometry=["48301","48001","11001"]
        cdc=["48001","11001"]
        report=reconcile_county_geoids(geometry,cdc,expected_missing={"48301"})
        self.assertEqual(report["joinedGeoids"],2)
        self.assertEqual(report["unmatchedGeometryGeoids"],["48301"])
        self.assertEqual(report["imputedValues"],0)

    def test_unreviewed_missing_county_is_not_silently_hidden(self):
        with self.assertRaisesRegex(ValueError,"missingness differs"):
            reconcile_county_geoids(["48301","48001"],["48001"])

    def test_additional_source_geography_outside_geom_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"lacks Census geometry"):
            reconcile_county_geoids(["48301"],["48301","48001"])

    def test_duplicate_source_geography_cannot_pass_count_based_join(self):
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            reconcile_county_geoids(["48301"],["48301","48301"])

    def test_invalid_or_truncated_fips_cannot_pass(self):
        with self.assertRaisesRegex(ValueError,"five-digit"):
            reconcile_county_geoids(["48301"],["301"])

    def test_approved_match_is_exact_not_display_name(self):
        report=reconcile_county_geoids(["11001","48301"],["48301","11001"])
        self.assertEqual(report["joinedGeoids"],2)
        self.assertEqual(report["unmatchedGeometryGeoids"],[])
