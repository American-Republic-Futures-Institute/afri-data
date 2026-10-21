"""DATA-06 BLS keyless QCEW state-level source preservation tests."""
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import unittest

from tools.stat05_geography import STATE_NAMES

FIPS = frozenset(STATE_NAMES)
from tools.bls_qcew_source_library import (
    BASE, INDUSTRIES, bls_records, parse_quarter, registry_sources,
    official_csv, BLSUnavailable,
)
from tools.source_library import ROOT, CATALOG, validate_catalog


def original(year, quarter, industry="10", mutate=None):
    data=[]
    for fips in sorted(FIPS):
        for ownership in ("0", "5"):
            row={
                "area_fips": fips+"000", "year": str(year),
                "qtr": str(quarter), "own_code": ownership,
                "industry_code": industry.replace("_","-"),
                "month3_emplvl": "1000", "total_qtrly_wages": "120000.09",
            }
            if mutate is not None and fips=="01" and ownership=="0":
                mutate(row)
            data.append(row)
    data.append({"area_fips":"US000","year":str(year),"qtr":str(quarter),
                 "own_code":"0","industry_code":industry.replace("_","-"),
                 "month3_emplvl":"1000000","total_qtrly_wages":"5000000.00"})
    buffer=io.StringIO(newline="")
    writer=csv.DictWriter(buffer,fieldnames=list(data[0]),lineterminator="\n")
    writer.writeheader()
    writer.writerows(data)
    return buffer.getvalue().encode("utf-8")


class QcewSourceTests(unittest.TestCase):
    def test_preferred_original_source_field_allows_digits_not_hostile_paths(self):
        from tools.source_library import SourceLibraryError
        from tools.cdc_places_source_library import registry_sources as cdc
        qcew=registry_sources()
        treasury=json.loads((ROOT/CATALOG).read_text("utf-8"))
        combined={**treasury, "datasets": treasury["datasets"]+cdc()+qcew}
        validate_catalog(combined)
        combined["datasets"][-1]["preferredField"]="month3_emplvl/../secret"
        with self.assertRaisesRegex(SourceLibraryError,"Invalid source metric"):
            validate_catalog(combined)

    def test_original_quarter_record_values_not_recalculated_or_reformatted(self):
        rows=parse_quarter(original(2025,1),year=2025,quarter=1,industry="10")
        self.assertEqual(len(rows),2*len(FIPS))
        self.assertEqual(rows[0]["record_date"],"2025-03-31")
        self.assertEqual(rows[0]["month3_emplvl"],"1000")
        self.assertEqual(rows[0]["total_qtrly_wages"],"120000.09")
        self.assertEqual(rows[0]["time_basis"],"qcew_quarter_end_index_not_daily_measurement")
        self.assertFalse(any(r["area_fips"]=="US000" for r in rows))
        self.assertEqual(len({r["area_fips"] for r in rows}),52)

    def test_manufacturing_hyphen_remains_exactly_as_publisher_wrote_it(self):
        rows=parse_quarter(original(2024,4,industry="31_33"),year=2024,quarter=4,industry="31_33")
        self.assertEqual(rows[0]["industry_code"],"31-33")

    def test_all_registered_official_industry_sources_with_cdc_and_treasury(self):
        s=registry_sources()
        self.assertEqual(len(s),4)
        self.assertEqual({x["industryCode"] for x in s},set(INDUSTRIES.values()))
        treasury=json.loads((ROOT/CATALOG).read_text("utf-8"))
        from tools.cdc_places_source_library import registry_sources as cdc
        validate_catalog({**treasury,"datasets":treasury["datasets"]+cdc()+s})

    def test_reject_bls_bad_quarter_industry_or_missing_geographic_coverage(self):
        with self.assertRaisesRegex(BLSUnavailable,"quarter/industry"):
            parse_quarter(original(2025,1),year=2025,quarter=2,industry="10")
        with self.assertRaisesRegex(BLSUnavailable,"quarter/industry"):
            parse_quarter(original(2025,1),year=2025,quarter=1,industry="54")
        partial=original(2025,1).decode()
        partial="\n".join(l for l in partial.splitlines()
                          if not l.startswith(("01000,","02000,","04000,",
                                               "05000,","06000,","08000,",
                                               "09000,","10000,","11000,")))+"\n"
        with self.assertRaisesRegex(BLSUnavailable,"Incomplete"):
            parse_quarter(partial.encode(),year=2025,quarter=1,industry="10")

    def test_recent_history_pulls_every_released_quarter_and_excludes_unpublished(self):
        s=next(x for x in registry_sources() if x["id"]=="bls-qcew-all-industry")
        requests=[]
        def fetch(url,*,year,latest_year):
            requests.append(url)
            q=int(url.split("/")[-3])
            if year==2026 and q>1:return None
            return original(year,q)
        rows=bls_records(s,fetch=fetch,now=datetime(2026,10,20,tzinfo=timezone.utc))
        self.assertEqual(len(requests),20)
        self.assertEqual(len(rows),17*2*len(FIPS))
        self.assertEqual(rows[-1]["record_date"],"2026-03-31")
        self.assertEqual(rows[0]["record_date"],"2022-03-31")
        self.assertTrue(all(r["total_qtrly_wages"]=="120000.09" for r in rows))


if __name__=="__main__":
    unittest.main()
