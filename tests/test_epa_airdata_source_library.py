"""Offline EPA publisher ZIP acquisition, path safety, revision and Git-custody checks."""
import copy
from datetime import datetime,timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile,ZIP_DEFLATED

from tools import epa_airdata_source_library as e
from tools.source_library import BASE, refresh, verify, canonical, validate_catalog


def fixture(year=2025,scope="county",rows=None,header=None,filename=None):
    rows=rows or (260 if scope=="county" else 130)
    header=header or (["State","County","Year","Days with AQI","Good Days","AQI Max"]
                       if scope=="county" else
                       ["CBSA","Year","Days with AQI","Good Days","AQI Max"])
    lines=[",".join(header)]
    for index in range(rows):
        row=({"State":"Virginia","County":f"Monitored County {index}",
              "Year":str(year),"Days with AQI":"300","Good Days":"220","AQI Max":"99"}
             if scope=="county" else
             {"CBSA":f"Metro {index}","Year":str(year),"Days with AQI":"300",
              "Good Days":"220","AQI Max":"99"})
        lines.append(",".join(row.get(key,"") for key in header))
    name=filename or f"{e.KINDS[scope]}_{year}.csv"
    output=io.BytesIO()
    with ZipFile(output,"w",compression=ZIP_DEFLATED) as archive:
        archive.writestr(name,"\n".join(lines)+"\n")
    return output.getvalue()


class EPAOriginalsTests(unittest.TestCase):
    def test_historical_registry_is_seventy_four_official_original_editions(self):
        specs=e.registry_sources(now=datetime(2026,10,21,tzinfo=timezone.utc))
        self.assertEqual(len(specs),74)
        self.assertEqual(len({x["id"] for x in specs}),74)
        self.assertEqual({x["sourceScope"] for x in specs},{"county","cbsa"})
        self.assertTrue(all(x["endpoint"].startswith(e.BASE) for x in specs))
        self.assertTrue(all(x["dateBasis"]=="epa-annual-measurement-year-end-not-publisher-release"
                            for x in specs))
        self.assertEqual(specs[0]["id"],"epa-airdata-county-1990")
        self.assertEqual(specs[-1]["id"],"epa-airdata-cbsa-2026")
        catalog={"schemaVersion":"1.0.0","publisher":"U.S. Treasury",
                "publisherApi":BASE,"refreshCadence":"weekly",
                "datasetClass":"source-native-unreviewed","datasets":specs}
        validate_catalog(catalog)

    def test_latest_year_discovery_uses_both_official_original_editions(self):
        touched=[]
        def exists(url):
            touched.append(url)
            return url.endswith("_2027.zip")
        rows=e.registry_sources(now=datetime(2027,10,21,tzinfo=timezone.utc),
                                discover=True,available=exists)
        self.assertEqual(len(rows),76)
        self.assertEqual(len(touched),2)
        self.assertTrue(all(x.startswith(e.BASE) for x in touched))
        no=e.registry_sources(now=datetime(2027,10,21,tzinfo=timezone.utc),
                              discover=True,available=lambda _:False)
        self.assertEqual(len(no),74)

    def test_exact_original_zip_is_read_with_all_publisher_fields_and_safe_year_basis(self):
        for scope,n in (("county",260),("cbsa",130)):
            with self.subTest(scope=scope):
                raw=fixture(scope=scope)
                result=e.parse_original(raw,year=2025,scope=scope)
                self.assertEqual(len(result),n)
                self.assertTrue(all(row["record_date"]=="2025-12-31" for row in result))
                self.assertTrue(all(row["Days with AQI"]=="300" for row in result))
                self.assertEqual(result[0]["Good Days"],"220")
                self.assertTrue(all(row["time_basis"]=="epa_annual_observation_year_not_publication_date"
                                    for row in result))

    def test_source_library_retains_exact_original_zip_and_reconciles_year_partitions(self):
        specs=e.registry_sources(now=datetime(2026,10,21,tzinfo=timezone.utc))
        county=next(x for x in specs if x["id"]=="epa-airdata-county-2025")
        catalog={"schemaVersion":"1.0.0","publisher":"U.S. Treasury",
                 "publisherApi":BASE,"refreshCadence":"weekly",
                 "datasetClass":"source-native-unreviewed","datasets":[county]}
        raw=fixture()
        def source(_):
            return e.OriginalEPARows(e.parse_original(raw,year=2025,scope="county"),raw)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            report=refresh(root,catalog=catalog,loader=source,now="2026-10-21T13:00:00Z")
            self.assertEqual(report["datasets"],1)
            self.assertEqual(report["records"],260)
            index=json.loads((root/"publication/source-library/index.json").read_text())
            record=index["datasets"][0]
            self.assertEqual(record["provider"],"epa-airdata")
            self.assertEqual(record["originalZipSha256"],sha256(raw).hexdigest())
            self.assertEqual((root/record["originalZipPath"]).read_bytes(),raw)
            self.assertEqual(e.verify_original_file(root,record).__len__(),260)
            self.assertEqual(verify(root)["records"],260)
            ledger=json.loads((root/"publication/source-library/acquisition-ledger.json").read_text())
            self.assertEqual(ledger["totals"]["mirrored"],1)
            self.assertEqual(ledger["providers"]["epa-airdata"]["mirrored"],1)
            self.assertIsNone(ledger["sources"][0]["sourceReleaseToGitLagDays"])
            binary=root/record["originalZipPath"]
            binary.write_bytes(binary.read_bytes()+b"modified")
            with self.assertRaisesRegex(e.EPAUnavailable,"bytes were altered"):
                verify(root)

    def test_unqualified_projection_cannot_pass_for_an_unrelated_original_zip(self):
        raw=fixture()
        specs=e.registry_sources()
        one=next(x for x in specs if x["id"]=="epa-airdata-county-2025")
        regs={"schemaVersion":"1.0.0","publisher":"U.S. Treasury",
              "publisherApi":BASE,"refreshCadence":"weekly",
              "datasetClass":"source-native-unreviewed","datasets":[one]}
        source_rows=e.parse_original(raw,year=2025,scope="county")
        source_rows[0]["Good Days"]="fraud"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,"must match exact original ZIP"):
                refresh(Path(directory),catalog=regs,loader=lambda _:
                        e.OriginalEPARows(source_rows,raw))

    def test_missing_original_zip_fails_closed(self):
        specs=e.registry_sources()
        one=next(x for x in specs if x["id"]=="epa-airdata-county-2025")
        regs={"schemaVersion":"1.0.0","publisher":"U.S. Treasury",
              "publisherApi":BASE,"refreshCadence":"weekly",
              "datasetClass":"source-native-unreviewed","datasets":[one]}
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,"original publisher ZIP bytes"):
                refresh(Path(directory),catalog=regs,loader=lambda _:
                        e.parse_original(fixture(),year=2025,scope="county"))

    def test_reject_zip_slip_wrong_year_and_suspect_publisher_structure(self):
        for name in ("../../other.csv","annual_aqi_by_cbsa_2025.csv",
                     "annual_aqi_by_county_2024.csv"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(e.EPAUnavailable,"unexpected or unsafe"):
                    e.parse_original(fixture(filename=name),year=2025,scope="county")
        with self.assertRaisesRegex(e.EPAUnavailable,"year or monitored-day"):
            e.parse_original(fixture(year=2024),year=2025,scope="county")
        with self.assertRaisesRegex(e.EPAUnavailable,"header"):
            e.parse_original(fixture(header=["State","County","Year","Good Days","AQI Max"]),
                             year=2025,scope="county")

    def test_reject_insecure_or_unrelated_official_looking_urls(self):
        good=e.source_url(2025,"county")
        for link in ("https://aqs.epa.gov.evil.test/aqsweb/airdata/annual_aqi_by_county_2025.zip",
                     good+"?x=1",good.replace("https:","http:"),
                     "https://aqs.epa.gov/aqsweb/airdata/../secrets.zip"):
            with self.assertRaisesRegex(e.EPAUnavailable,"Unsafe EPA ZIP source"):
                e.official_zip(link)
        with self.assertRaisesRegex(e.EPAUnavailable,"edition identity"):
            e.source_url(2025,"not-a-scope")

    def test_reject_duplicate_monitored_county_labels(self):
        original=fixture(rows=260)
        with ZipFile(io.BytesIO(original)) as z:
            raw=z.read(z.namelist()[0]).decode()
        rows=raw.splitlines()
        rows[-1]=rows[-2]
        stream=io.BytesIO()
        with ZipFile(stream,"w",compression=ZIP_DEFLATED) as z:
            z.writestr("annual_aqi_by_county_2025.csv","\n".join(rows)+"\n")
        with self.assertRaisesRegex(e.EPAUnavailable,"Duplicate EPA"):
            e.parse_original(stream.getvalue(),year=2025,scope="county")

    def test_source_fingerprint_detects_zip_revision_even_if_rows_are_equal(self):
        from tools.source_freshness import source_fingerprint
        payload={"id":"epa-airdata-county-2025","rowCount":2,
                 "provider":"epa-airdata",
                 "partitions":[{"path":"publication/source-library/data/epa-airdata-county-2025/2025.json",
                                "sha256":"f"*64,"rows":2,"bytes":100}],
                 "originalZipSha256":"a"*64,"originalZipBytes":500,
                 "originalZipPath":e.original_path("a"*64)}
        b=copy.deepcopy(payload)
        b["originalZipSha256"]="b"*64
        b["originalZipPath"]=e.original_path("b"*64)
        self.assertNotEqual(source_fingerprint(payload),source_fingerprint(b))

if __name__=="__main__":
    unittest.main()
