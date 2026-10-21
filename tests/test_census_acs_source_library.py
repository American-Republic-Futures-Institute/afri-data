"""DATA-07: offline official ACS five-year table-based state replay tests."""
import csv
import io
import json
from pathlib import Path
import unittest

from tools.stat05_geography import STATE_NAMES

FIPS = frozenset(STATE_NAMES)
from tools.census_acs_source_library import (
    BASE, CATALOG, PAGE, ROOT, TABLES, VINTAGES, census_records,
    parse_table, registry_sources, source_url,
)
from tools.source_library import SourceLibraryError, validate_catalog


def fixture(table,year,suppress=None):
    prefix=table.upper()
    buf=io.StringIO(newline="")
    fields=["GEO_ID",prefix+"_E001",prefix+"_M001",
            prefix+"_E002",prefix+"_M002"] if table=="b01002" else [
                "GEO_ID",prefix+"_E001",prefix+"_M001"]
    writer=csv.DictWriter(buf,fieldnames=fields,delimiter="|",lineterminator="\n")
    writer.writeheader()
    for state in sorted(FIPS):
        row={"GEO_ID":"0400000US"+state,
             prefix+"_E001":"37.4" if table=="b01002" else "62000",
             prefix+"_M001":"0.3" if table=="b01002" else "1400"}
        if suppress==state:
            row[prefix+"_E001"]="-666666666"
            row[prefix+"_M001"]="-666666666"
        if table=="b01002":
            row[prefix+"_E002"]="37.7";row[prefix+"_M002"]="0.2"
        writer.writerow(row)
    writer.writerow({"GEO_ID":"0500000US01001",
                      prefix+"_E001":"999999",prefix+"_M001":"1"})
    return buf.getvalue().encode("utf-8")


class ACSHistoryTests(unittest.TestCase):
    def test_eight_official_tables_across_three_pooled_five_year_editions(self):
        sources=registry_sources()
        self.assertEqual(len(sources),24)
        self.assertEqual({s["table"] for s in sources},TABLES)
        self.assertEqual({s["releaseYear"] for s in sources},VINTAGES)
        t=json.loads((ROOT/"catalog/source-library/treasury-fiscaldata.json").read_text("utf-8"))
        from tools.cdc_places_source_library import registry_sources as cdc
        from tools.bls_qcew_source_library import registry_sources as bls
        validate_catalog({**t,"datasets":t["datasets"]+cdc()+bls()+sources})
        self.assertEqual(len(t["datasets"]+cdc()+bls()+sources),57)

    def test_publisher_original_suppression_strings_and_90_percent_moe_survive(self):
        rows=parse_table(fixture("b01002",2023,suppress="01"),table="b01002",year=2023)
        self.assertEqual(len(rows),52)
        self.assertEqual(rows[0]["GEO_ID"],"0400000US01")
        self.assertEqual(rows[0]["B01002_E001"],"-666666666")
        self.assertEqual(rows[0]["B01002_M001"],"-666666666")
        self.assertEqual(rows[0]["estimate_status"],"not_available")
        self.assertEqual(rows[1]["B01002_E001"],"37.4")
        self.assertEqual(rows[1]["B01002_M001"],"0.3")
        self.assertEqual(rows[1]["record_date"],"2023-12-31")
        self.assertEqual(rows[1]["survey_reference_period"],"2019-2023")
        self.assertEqual(rows[1]["time_basis"],"acs_five_year_pooled_vintage_index_not_single_year")
        self.assertEqual(rows[1]["margin_of_error_confidence"],"0.90")
        self.assertRegex(rows[1]["source_original_sha256"],"^[a-f0-9]{64}$")
        self.assertNotIn("B01002_E002",rows[1]) # only requested estimate/MOE, not a fabricated measure

    def test_52_state_equivalent_keys_and_stable_replay(self):
        data=fixture("b25077",2024)
        rows=parse_table(data,table="b25077",year=2024)
        self.assertEqual(len(rows),52)
        self.assertEqual([x["state_fips"] for x in rows], sorted(FIPS))
        self.assertEqual(rows,parse_table(data,table="b25077",year=2024))

    def test_no_imputation_if_moe_missing_or_bad_upstream_geography(self):
        raw=fixture("b19013",2024)
        broken=raw.replace(b"1400",b"-666666666",1)
        with self.assertRaisesRegex(ValueError,"paired"):
            parse_table(broken,table="b19013",year=2024)
        duplicate=raw+raw.splitlines()[1]+b"\n"
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            parse_table(duplicate,table="b19013",year=2024)
        missing=b"\n".join(raw.splitlines()[:-2])+b"\n"
        with self.assertRaisesRegex(ValueError,"coverage incomplete"):
            parse_table(missing,table="b19013",year=2024)

    def test_census_host_url_and_table_identity_reject_substitution(self):
        s=next(x for x in registry_sources() if x["id"]=="census-acs5-b19013-2024")
        calls=[]
        def fetch(url,*,host,limit):
            calls.append((url,host,limit))
            return fixture("b19013",2024)
        rows=census_records(s,fetch=fetch)
        self.assertEqual(len(rows),52)
        self.assertEqual(calls,[(
            "https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/acsdt5y2024-b19013.dat",
            "www2.census.gov",30000000)])
        s["endpoint"]="https://example.com/injected.dat"
        with self.assertRaisesRegex(ValueError,"Unapproved"):
            census_records(s,fetch=fetch)
        with self.assertRaises(ValueError):
            source_url(2024,"b05001")


    def test_new_official_population_gini_and_housing_source_edition_projections(self):
        original = registry_sources()
        expected = {"b01003":"persons (ACS estimate)",
                    "b19083":"unitless Gini index",
                    "b25002":"housing units (ACS estimate)",
                    "b25003":"occupied housing units"}
        for table,unit in expected.items():
            for year in VINTAGES:
                with self.subTest(table=table,year=year):
                    desc=next(x for x in original if x["id"]==f"census-acs5-{table}-{year}")
                    self.assertEqual(desc["unit"],unit)
                    self.assertEqual(desc["surveyReferencePeriod"],f"{year-4}-{year}")
                    self.assertEqual(desc["preferredField"],table.upper()+"_E001")
                    self.assertEqual(desc["endpoint"],source_url(year,table))
                    self.assertTrue(desc["endpoint"].startswith(BASE))
                    raw=fixture(table,year)
                    if table=="b19083":
                        raw=raw.replace(b"62000",b"0.4567").replace(b"1400",b"0.0180")
                    rows=parse_table(raw,table=table,year=year)
                    self.assertEqual(len(rows),52)
                    self.assertEqual(rows[0][table.upper()+"_E001"],
                                     "0.4567" if table=="b19083" else "62000")
                    self.assertEqual(rows[0]["margin_of_error_confidence"],"0.90")
                    self.assertEqual(rows[0]["survey_reference_period"],f"{year-4}-{year}")
                    self.assertEqual(rows[0]["record_date"],f"{year}-12-31")

    def test_gini_range_suppression_and_unsupported_table_fail_closed(self):
        raw=fixture("b19083",2024).replace(b"62000",b"0.4500").replace(b"1400",b"0.0100")
        self.assertEqual(parse_table(raw,table="b19083",year=2024)[0]["B19083_E001"],"0.4500")
        over=raw.replace(b"0.4500",b"1.2500",1)
        with self.assertRaisesRegex(ValueError,"unit interval"):
            parse_table(over,table="b19083",year=2024)
        suppressed=fixture("b25003",2023,suppress="01")
        rows=parse_table(suppressed,table="b25003",year=2023)
        self.assertEqual(rows[0]["estimate_status"],"not_available")
        self.assertEqual(rows[0]["B25003_M001"],"-666666666")
        with self.assertRaises(ValueError):
            source_url(2024,"b25099")


if __name__=="__main__":
    unittest.main()
