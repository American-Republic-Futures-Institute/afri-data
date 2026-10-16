"""Schema diagnostics must not expose untrusted monetary or award data."""
import json
import unittest

from tools.inspect_usaspending import diagnostic, safe_code


class USAspendingDiagnosticTests(unittest.TestCase):
    def test_known_and_anomalous_codes_are_counted_without_amounts(self):
        source={"scope":"place_of_performance","geo_layer":"state",
                "spending_level":"transactions","results":[
                    {"shape_code":"VA","display_name":"Virginia","aggregated_amount":1e12},
                    {"shape_code":"VI","display_name":"Virgin Islands","aggregated_amount":3},
                    {"shape_code":None,"display_name":"Unknown","aggregated_amount":33333333.11},
                    {"shape_code":"non-state area","aggregated_amount":333.7},
                ]}
        report=diagnostic(json.dumps(source).encode())
        self.assertEqual(report["recognizedReferenceAreas"],1)
        self.assertEqual(report["excludedTerritories"],1)
        self.assertEqual(report["anomalousCodeCounts"],{"<null>":1,"non-state area":1})
        self.assertNotIn("33333333",json.dumps(report))
        self.assertNotIn("1e12",json.dumps(report))

    def test_code_sanitization(self):
        self.assertEqual(safe_code("VA"),"VA")
        self.assertEqual(safe_code(""),"<empty>")
        self.assertEqual(safe_code(None),"<null>")
        self.assertEqual(safe_code("<script>bad</script>"),"<noncanonical-string>")
        self.assertEqual(safe_code("x"*100),"<noncanonical-string>")
