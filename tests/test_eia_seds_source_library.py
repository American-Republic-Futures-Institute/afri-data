"""DATA-19B: source-native EIA State Energy Data System originals."""
import copy
import csv
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest

from tools.eia_seds_source_library import (
    SERIES, SOURCE_URL, SOURCE_PAGE, UNIT, STATES, EIAUnavailable,
    registry_sources, parse_original, eia_records, original_path, validate_registry)
from tools.source_library import CATALOG, ROOT, refresh, verify, validate_catalog
from tools.source_freshness import source_fingerprint


def fixture(missing=None, duplicate=False, invalid=None):
    years=[1960,1961,1962]
    out=io.StringIO(newline="")
    writer=csv.writer(out,lineterminator="\n")
    writer.writerow(["Data_Status","State","MSN"]+[str(y) for y in years])
    for code in sorted(STATES):
        if code==missing:
            continue
        for msn in sorted(SERIES.values()):
            values=["1234","1234.50","-13"]
            if invalid is not None and code=="AL" and msn=="TETCB":
                values[1]=invalid
            writer.writerow(["1962F",code,msn]+values)
    writer.writerow(["1962F","US","TETCB","99999","99999","99999"])
    writer.writerow(["1962F","AL","NOTCB","1","2","3"])
    if duplicate:
        writer.writerow(["1962F","AL","TETCB","1234","1234.50","-13"])
    return out.getvalue().encode("utf-8")


class EIAOriginalTests(unittest.TestCase):
    def test_five_approved_series_have_exact_keyless_eia_publisher_file(self):
        descriptors=registry_sources()
        self.assertEqual({x["id"] for x in descriptors},set(SERIES))
        for spec in descriptors:
            with self.subTest(spec=spec["id"]):
                self.assertEqual(spec["endpoint"],SOURCE_URL)
                self.assertEqual(spec["sourcePage"],SOURCE_PAGE)
                self.assertEqual(spec["preferredField"],"value")
                self.assertEqual(spec["unit"],"billion Btu")
                self.assertEqual(spec["dateBasis"],
                                 "eia-seds-annual-reference-year-end-not-publisher-release")
        treasury=json.loads((ROOT/CATALOG).read_text("utf-8"))
        validate_catalog({**treasury,"datasets":treasury["datasets"]+descriptors})

    def test_state_year_cell_strings_are_original_and_explicit_not_day_values(self):
        source=fixture()
        for spec in registry_sources():
            records=eia_records(spec,fetch=lambda:source)
            self.assertEqual(len(records),153)
            self.assertEqual(len(set(x["State"] for x in records)),51)
            first=next(x for x in records if x["State"]=="AL" and
                       x["record_date"]=="1961-12-31")
            self.assertEqual(first["MSN"],spec["msn"])
            self.assertEqual(first["value"],"1234.50")
            self.assertEqual(first["Data_Status"],"1962F")
            self.assertEqual(first["unit"],UNIT)
            self.assertEqual(first["value_year_column"],"1961")
            self.assertEqual(first["source_original_sha256"],sha256(source).hexdigest())
            self.assertEqual(first["time_basis"],"eia_seds_annual_year_not_release_date")
            self.assertTrue(all(row["MSN"]==spec["msn"] for row in records))
            self.assertTrue(all(row["State"] in STATES for row in records))

    def test_incomplete_or_duplicate_state_or_malformed_values_fail_closed(self):
        for alteration,error in [
            ({"missing":"WY"},"50-state/DC"),
            ({"duplicate":True},"Duplicate EIA"),
            ({"invalid":"=WEBSERVICE('evil')"},"Unrecognized SEDS")]:
            with self.subTest(alteration=alteration),self.assertRaisesRegex(EIAUnavailable,error):
                parse_original(fixture(**alteration),msn="TETCB")
        bad=fixture().replace(b"Data_Status,State,MSN",b"Data_Status,MSN,State")
        with self.assertRaisesRegex(EIAUnavailable,"schema"):
            parse_original(bad,msn="TETCB")
        with self.assertRaisesRegex(EIAUnavailable,"unknown|Unknown"):
            parse_original(fixture(),msn="QWERT")

    def test_registry_cannot_remap_an_eia_msn_to_a_wrong_publisher_metric(self):
        reg=json.loads((ROOT/"catalog/source-library/eia-seds.json").read_text())
        for prop,bad in [
            ("sourceCsv","https://evil.example/use_all_btu.csv"),
            ("publisherPage","https://evil.example"),
            ("unit","MWh"),("dataBasis","date-of-publication")]:
            tampered=copy.deepcopy(reg);tampered[prop]=bad
            with self.subTest(prop=prop),self.assertRaisesRegex(EIAUnavailable,"publisher"):
                validate_registry(tampered)
        tampered=copy.deepcopy(reg);tampered["series"][0]["msn"]="FAKE"
        with self.assertRaisesRegex(EIAUnavailable,"MSN"):
            validate_registry(tampered)

    def test_git_retains_byte_exact_full_publisher_csv_and_detects_revisions(self):
        source=fixture()
        spec=next(s for s in registry_sources() if s["id"]=="eia-seds-total-consumption")
        treasury=json.loads((ROOT/CATALOG).read_text("utf-8"))
        catalog={**treasury,"datasets":[spec]}
        original=lambda _:eia_records(spec,fetch=lambda:source)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            result=refresh(root=root,catalog=catalog,loader=original,
                           now="2026-10-21T12:00:00Z")
            self.assertEqual(result["failedSources"],{})
            self.assertEqual(result["datasets"],1)
            self.assertEqual(result["records"],153)
            entry=json.loads((root/"publication/source-library/index.json").read_text())["datasets"][0]
            self.assertEqual(entry["originalCsvSha256"],sha256(source).hexdigest())
            self.assertEqual((root/entry["originalCsvPath"]).read_bytes(),source)
            self.assertEqual(verify(root)["records"],153)
            first=source_fingerprint(entry)
            p=root/"publication/source-library/data/eia-seds-total-consumption/1961.json"
            rows=json.loads(p.read_text())["records"]
            self.assertEqual(len(rows),51)
            self.assertTrue(all(x["record_date"]=="1961-12-31" for x in rows))
            source=source.replace(b"1234.50",b"1234.51")
            result=refresh(root=root,catalog=catalog,loader=original,
                           now="2026-10-21T13:00:00Z")
            self.assertEqual(result["failedSources"],{})
            new=json.loads((root/"publication/source-library/index.json").read_text())["datasets"][0]
            self.assertNotEqual(first,source_fingerprint(new))
            self.assertEqual(verify(root)["records"],153)
            original_file=root/new["originalCsvPath"]
            original_file.write_bytes(b"changed government source")
            with self.assertRaisesRegex(EIAUnavailable,"SHA-256"):
                verify(root)


if __name__=="__main__":
    unittest.main()
