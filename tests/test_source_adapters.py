"""Offline tests for ACS and BLS publisher-specific source projections."""
import json
import unittest
from pipelines.census_acs_income import parse_acs_state_income
from pipelines.bls_laus import parse_laus_state_annual

class AdapterTests(unittest.TestCase):
    def test_acs_estimate_and_moe_remain_distinct(self):
        source=[["NAME","B19013_001E","B19013_001M","state"],
                ["Alabama","62984","1047","01"],["Alaska","-666666666","-666666666","02"]]
        rows=parse_acs_state_income(json.dumps(source).encode())
        self.assertEqual([x["geoid"] for x in rows],["01","02"])
        self.assertEqual(rows[0]["marginOfError"],1047)
        self.assertIsNone(rows[1]["value"])
        self.assertEqual(rows[1]["status"],"not_available")

    def test_acs_duplicate_geography_rejected(self):
        source=[["NAME","B19013_001E","B19013_001M","state"],
                ["Test","100","10","01"],["Duplicate","100","10","01"]]
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            parse_acs_state_income(json.dumps(source).encode())

    def test_acs_incomplete_moe_pair_rejected(self):
        source=[["NAME","B19013_001E","B19013_001M","state"],
                ["Test","100","-666666666","01"]]
        with self.assertRaisesRegex(ValueError,"Incomplete"):
            parse_acs_state_income(json.dumps(source).encode())

    def test_laus_accepts_annual_unadjusted_rate_only(self):
        raw=("series_id\tyear\tperiod\tvalue\tfootnote_codes\n"
             "LAUST010000000000003\t2025\tM13\t3.8\t\n"
             "LASST010000000000003\t2025\tM13\t3.2\t\n"
             "LAUST010000000000003\t2025\tM01\t9.9\t\n"
             "LAUST020000000000003\t2025\tM13\t4.1\t\n").encode()
        rows=parse_laus_state_annual(raw,2025)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]["geoid"],"01")
        self.assertEqual(rows[0]["value"],3.8)
        self.assertEqual(rows[0]["seasonalAdjustment"],"not_seasonally_adjusted")
        self.assertEqual(rows[0]["footnoteCodes"],[])

    def test_laus_duplicate_annual_series_rejected(self):
        raw=("series_id\tyear\tperiod\tvalue\tfootnote_codes\n"
             "LAUST010000000000003\t2025\tM13\t3.8\tG\n"
             "LAUST010000000000003\t2025\tM13\t3.9\tG\n").encode()
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            parse_laus_state_annual(raw,2025)

    def test_laus_invalid_rate_and_year_rejected(self):
        raw=("series_id\tyear\tperiod\tvalue\tfootnote_codes\n"
             "LAUST010000000000003\t2025\tM13\t105\tG\n").encode()
        with self.assertRaisesRegex(ValueError,"range"):
            parse_laus_state_annual(raw,2025)
        with self.assertRaisesRegex(ValueError,"Invalid LAUS publication year"):
            parse_laus_state_annual(raw,1900)
