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
    def test_discovery_of_complete_new_acs_vintage_requires_all_eight_official_tables(self):
        from datetime import datetime, timezone
        from tools.census_acs_source_library import discovered_vintages, supported_year
        now = datetime(2026, 10, 20, tzinfo=timezone.utc)
        checked = []
        def all_available(url):
            checked.append(url)
            return True
        self.assertEqual(discovered_vintages(now=now, available=all_available),
                         [2022, 2023, 2024, 2025])
        self.assertEqual(len(checked), 16)
        self.assertTrue(all(url.startswith(BASE+"2025/") for url in checked))
        self.assertTrue(supported_year(2025, now=now))
        self.assertFalse(supported_year(2026, now=now))
        result = registry_sources(discover=True, now=now, available=all_available)
        self.assertEqual(len(result), 64)
        newest = [x for x in result if x["releaseYear"] == 2025]
        self.assertEqual(len(newest), 16)
        self.assertEqual({x["surveyReferencePeriod"] for x in newest}, {"2021-2025"})

    def test_partial_or_unreleased_acs_vintage_stays_unpublished(self):
        from datetime import datetime, timezone
        from tools.census_acs_source_library import discovered_vintages
        now = datetime(2026, 10, 20, tzinfo=timezone.utc)
        available = lambda url: "b19013.dat" in url or "b25077.dat" in url
        self.assertEqual(discovered_vintages(now=now, available=available),
                         [2022, 2023, 2024])
        self.assertEqual(len(registry_sources(discover=True, now=now, available=available)),48)
        self.assertEqual(len(registry_sources(discover=True, now=now, available=lambda _: False)),48)

    def test_twelve_registered_acs_tables_are_allowed_in_official_vintage_head_probe(self):
        from tools.census_acs_source_library import official_table_available
        class Reply:
            headers={"Content-Length":"8192"}
            def __init__(self,url): self.url=url
            def __enter__(self): return self
            def __exit__(self,*_): pass
            def geturl(self): return self.url
        class Fake:
            def __init__(self): self.requests=[]
            def open(self,req,timeout):
                self.requests.append(req.full_url)
                self.request=req
                return Reply(req.full_url)
        opener=Fake()
        for table in sorted(TABLES):
            with self.subTest(table=table):
                url=source_url(2025,table)
                self.assertTrue(official_table_available(url,opener=opener))
                self.assertEqual(opener.request.get_method(),"HEAD")
        self.assertEqual(len(opener.requests),16)
        self.assertEqual(len(set(opener.requests)),12)
        with self.assertRaisesRegex(ValueError,"Unapproved Census HEAD"):
            official_table_available(
                BASE+"2025/table-based-SF/data/5YRData/acsdt5y2025-b05001.dat",
                opener=opener)

    def test_census_availability_probe_rejects_hostile_paths_and_oversized_publishers(self):
        from tools.census_acs_source_library import official_table_available
        url=source_url(2025,"b19013")
        class Reply:
            def __init__(self, wanted, size):
                self._url=wanted
                self.headers={"Content-Length":str(size)}
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def geturl(self):return self._url
        class Fake:
            def __init__(self,size):self.size=size
            def open(self, req, timeout):
                self.request = req
                return Reply(req.full_url,self.size)
        fake=Fake(20_000_000)
        self.assertTrue(official_table_available(url,opener=fake))
        self.assertEqual(fake.request.get_method(),"HEAD")
        with self.assertRaisesRegex(RuntimeError,"byte ceiling"):
            official_table_available(url,opener=Fake(40_000_000))
        with self.assertRaisesRegex(ValueError,"Unapproved Census HEAD"):
            official_table_available("https://attacker.example/file.dat",opener=fake)

    def test_sixteen_official_tables_across_three_pooled_five_year_editions(self):
        sources=registry_sources()
        self.assertEqual(len(sources),48)
        self.assertEqual({s["table"] for s in sources},TABLES)
        self.assertEqual({s["releaseYear"] for s in sources},VINTAGES)
        t=json.loads((ROOT/"catalog/source-library/treasury-fiscaldata.json").read_text("utf-8"))
        from tools.cdc_places_source_library import registry_sources as cdc
        from tools.bls_qcew_source_library import registry_sources as bls
        validate_catalog({**t,"datasets":t["datasets"]+cdc()+bls()+sources})
        self.assertGreaterEqual(len(t["datasets"]+cdc()+bls()+sources),103)

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

    def test_controlled_census_population_total_retains_numeric_estimate_and_original_moe_sentinel(self):
        for edition in sorted(VINTAGES):
            for publisher_marker in ("-555555555", "*****"):
                with self.subTest(year=edition, marker=publisher_marker):
                    original=fixture("b01003",edition).replace(b"1400",publisher_marker.encode(),1)
                    rows=parse_table(original,table="b01003",year=edition)
                    first=rows[0]
                    self.assertEqual(len(rows),52)
                    self.assertEqual(first["B01003_E001"],"62000")
                    self.assertEqual(first["B01003_M001"],publisher_marker)
                    self.assertEqual(first["estimate_status"],"available")
                    self.assertEqual(first["margin_of_error_status"],"publisher_controlled")
                    self.assertEqual(first["margin_of_error_confidence"],"0.90")
                    self.assertEqual(first["survey_reference_period"],f"{edition-4}-{edition}")
                    self.assertNotEqual(first["B01003_M001"],"0")
                    self.assertEqual(rows[1]["margin_of_error_status"],"published")

    def test_controlled_marker_not_confused_with_arbitrary_missing_moe(self):
        raw=fixture("b01003",2024)
        for bad in ("-666666666","-888888888","-999999999"):
            with self.subTest(moe=bad):
                broken=raw.replace(b"1400",bad.encode(),1)
                with self.assertRaisesRegex(ValueError,"paired"):
                    parse_table(broken,table="b01003",year=2024)
        invalid=raw.replace(b"62000",b"*****",1)
        with self.assertRaisesRegex(ValueError,"Invalid official ACS numeric"):
            parse_table(invalid,table="b01003",year=2024)

    def test_irregular_nonstate_rows_do_not_invalidate_complete_original_state_source(self):
        # Only the requested 52 state geographies form this source product.
        # Census multi-geography full files can contain rows with missing or
        # extra columns outside the selected state-level GEO_ID subset.
        original=fixture("b25002",2022)
        nonstate_irregular=(
            b"0500000US01003|1000|20|unexpected-extra-source-column\n"
            b"0500000US01005|1000\n"
            b"1400000US01001020100|2000|50|extra\n")
        rows=parse_table(original+nonstate_irregular,table="b25002",year=2022)
        self.assertEqual(len(rows),52)
        self.assertEqual([r["state_fips"] for r in rows],sorted(FIPS))
        self.assertEqual(rows[0]["B25002_E001"],"62000")
        # The source-original digest necessarily reflects the entire exact
        # publisher byte stream, including non-state geographies.
        self.assertNotEqual(rows[0]["source_original_sha256"],
                            parse_table(original,table="b25002",year=2022)[0]["source_original_sha256"])

    def test_selected_acs_state_row_missing_or_extra_columns_still_fails_closed(self):
        original=fixture("b25002",2022)
        state_line=b"0400000US01|62000|1400"
        self.assertIn(state_line,original)
        for tampered in (state_line+b"|unexpected",b"0400000US01|62000"):
            with self.subTest(row=tampered):
                broken=original.replace(state_line,tampered,1)
                with self.assertRaisesRegex(ValueError,"Unexpected ACS state row width"):
                    parse_table(broken,table="b25002",year=2022)

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

    def test_four_new_housing_tables_preserve_source_editions_and_original_units(self):
        new_tables={
            "b25001":("housing units (ACS estimate)","62000","1400"),
            "b25008":("persons in occupied housing units","62000","1400"),
            "b25010":("persons per occupied housing unit","2.45","0.02"),
            "b25035":("year built (median)","1990","4"),
        }
        sources=registry_sources()
        for table,(unit,estimate,moe) in new_tables.items():
            for year in sorted(VINTAGES):
                with self.subTest(table=table,edition=year):
                    dataset=next(x for x in sources if x["id"]==f"census-acs5-{table}-{year}")
                    self.assertEqual(dataset["unit"],unit)
                    self.assertEqual(dataset["sourcePage"],PAGE)
                    self.assertEqual(dataset["preferredField"],table.upper()+"_E001")
                    self.assertEqual(dataset["surveyReferencePeriod"],f"{year-4}-{year}")
                    self.assertEqual(dataset["endpoint"],source_url(year,table))
                    self.assertTrue(dataset["endpoint"].endswith(f"acsdt5y{year}-{table}.dat"))
                    raw=fixture(table,year).replace(b"62000",estimate.encode()).replace(b"1400",moe.encode())
                    rows=parse_table(raw,table=table,year=year)
                    self.assertEqual(len(rows),52)
                    self.assertEqual(rows[0][table.upper()+"_E001"],estimate)
                    self.assertEqual(rows[0][table.upper()+"_M001"],moe)
                    self.assertEqual(rows[0]["margin_of_error_status"],"published")
                    self.assertEqual(rows[0]["survey_reference_period"],f"{year-4}-{year}")
                    self.assertRegex(rows[0]["source_original_sha256"],"^[0-9a-f]{64}$")

    def test_new_total_housing_units_controlled_population_moe_keeps_original_strings(self):
        raw=fixture("b25001",2024).replace(b"1400",b"-555555555",1)
        rows=parse_table(raw,table="b25001",year=2024)
        self.assertEqual(rows[0]["B25001_E001"],"62000")
        self.assertEqual(rows[0]["B25001_M001"],"-555555555")
        self.assertEqual(rows[0]["margin_of_error_status"],"publisher_controlled")
        self.assertEqual(rows[0]["estimate_status"],"available")

    def test_rent_cost_quartiles_and_burden_percent_retained_as_source_estimates(self):
        published=registry_sources()
        cases={
            "b25057": ("USD (inflation-adjusted vintage)", "880"),
            "b25058": ("USD (inflation-adjusted vintage)", "1200"),
            "b25059": ("USD (inflation-adjusted vintage)", "1800"),
            "b25071": ("percent (median rent/income)", "32.4"),
        }
        for table,(unit,original_estimate) in cases.items():
            for vintage in VINTAGES:
                with self.subTest(table=table,vintage=vintage):
                    key=f"census-acs5-{table}-{vintage}"
                    spec=next(x for x in published if x["id"]==key)
                    self.assertEqual(spec["unit"],unit)
                    self.assertEqual(spec["preferredField"],table.upper()+"_E001")
                    self.assertEqual(spec["surveyReferencePeriod"],
                                     f"{vintage-4}-{vintage}")
                    self.assertEqual(spec["endpoint"],source_url(vintage,table))
                    source=fixture(table,vintage)
                    source=source.replace(b"62000",original_estimate.encode())
                    source=source.replace(b"1400",b"20")
                    rows=parse_table(source,table=table,year=vintage)
                    self.assertEqual(len(rows),52)
                    self.assertEqual(rows[0][table.upper()+"_E001"],original_estimate)
                    self.assertEqual(rows[0][table.upper()+"_M001"],"20")
                    self.assertEqual(rows[0]["margin_of_error_confidence"],"0.90")
                    self.assertEqual(rows[0]["time_basis"],
                                     "acs_five_year_pooled_vintage_index_not_single_year")

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
