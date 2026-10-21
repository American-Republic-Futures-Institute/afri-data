"""DATA-05: offline source-identity and model-value tests, no network."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.cdc_places_source_library import (
    BASE, COUNTIES, KNOWN, MEASURES, cdc_records, registry_sources,
)
from tools.source_library import CATALOG, ROOT, SourceLibraryError, validate_catalog, refresh


def source_rows(field="obesity_crudeprev", count=COUNTIES[2025]):
    return [
        {"countyfips": f"{n + 1:05d}", "countyname": "Synthetic County " + str(n),
         "stateabbr": "VA", field: "18.2", field.replace("_crudeprev", "_crude95ci"): "(16.9, 19.5)"}
        for n in range(count)
    ]


class CdcOriginalSourceTests(unittest.TestCase):
    def test_official_2023_2024_2025_registrations_and_fourteen_measure_allowlist(self):
        sources = registry_sources()
        self.assertEqual(len(sources), 42)
        self.assertEqual(len({s["id"] for s in sources}), 42)
        self.assertEqual({s["releaseYear"] for s in sources}, set(KNOWN))
        self.assertEqual({s["indicatorStem"] for s in sources}, MEASURES)
        treasury = json.loads((ROOT / CATALOG).read_text("utf-8"))
        validate_catalog({**treasury, "datasets": treasury["datasets"] + sources})
        self.assertEqual(len(treasury["datasets"]) + len(sources), 57)

    def test_eight_additional_measures_preserve_original_cdc_prevalence_and_intervals_across_vintages(self):
        extra = {"access2","casthma","cancer","copd","depression",
                 "mhlth","phlth","stroke"}
        sources = [s for s in registry_sources() if s["indicatorStem"] in extra]
        self.assertEqual(len(sources), 24)
        for source in sources:
            stem = source["indicatorStem"]
            year = source["releaseYear"]
            value = stem + "_crudeprev"
            ci = stem + "_crude95ci"
            def get(url, *, host, limit):
                self.assertEqual(host,"data.cdc.gov")
                self.assertEqual(limit,3500000)
                self.assertIn(value,url)
                self.assertIn(ci,url)
                return json.dumps(source_rows(field=value,count=COUNTIES[year])).encode("utf-8")
            with self.subTest(id=source["id"]):
                original=cdc_records(source,fetch=get)
                self.assertEqual(len(original),COUNTIES[year])
                self.assertEqual(original[0][value],"18.2")
                self.assertEqual(original[0][ci],"(16.9, 19.5)")
                self.assertEqual(original[0]["model_reference_year"],str(KNOWN[year][1]))
                self.assertEqual(original[0]["record_date"],f"{year}-12-31")
                self.assertNotIn("derived_metric",original[0])
        access=next(x for x in sources if x["id"]=="cdc-places-access2-2025")
        self.assertIn("18–64",access["description"])

    def test_missing_selected_measure_is_not_falsely_counted_as_published(self):
        source=next(x for x in registry_sources() if x["id"]=="cdc-places-access2-2025")
        empty=[{"countyfips":f"{i+1:05d}",
                "countyname":"Synthetic county","stateabbr":"VA"}
                for i in range(COUNTIES[2025])]
        def fetch(url,*,host,limit):
            return json.dumps(empty).encode("utf-8")
        with self.assertRaisesRegex(ValueError,"no published prevalence"):
            cdc_records(source,fetch=fetch)

    def test_stores_original_modeled_value_interval_and_separate_release_marker(self):
        source = next(s for s in registry_sources() if s["id"] == "cdc-places-obesity-2025")
        captured = []
        def get(url, *, host, limit):
            captured.append((url, host, limit))
            return json.dumps(source_rows()).encode("utf-8")
        rows = cdc_records(source, fetch=get)
        self.assertEqual(len(rows), COUNTIES[2025])
        self.assertEqual(rows[0]["obesity_crudeprev"], "18.2")
        self.assertEqual(rows[0]["obesity_crude95ci"], "(16.9, 19.5)")
        self.assertEqual(rows[0]["record_date"], "2025-12-31")
        self.assertEqual(rows[0]["model_reference_year"], "2023")
        self.assertEqual(rows[0]["time_basis"], "publisher_release_year_marker_not_survey_date")
        self.assertEqual(captured[0][1:], ("data.cdc.gov", 3500000))
        self.assertTrue(captured[0][0].startswith(BASE + "i46a-9kgh.json?"))
        self.assertIn("%24select=", captured[0][0])

    def test_2024_publisher_count_differing_from_other_vintages_is_preserved(self):
        source = next(s for s in registry_sources() if s["id"] == "cdc-places-obesity-2024")
        def publish(count):
            return lambda url, *, host, limit: json.dumps(
                source_rows(count=count)).encode("utf-8")
        self.assertEqual(len(cdc_records(source, fetch=publish(3144))), 3144)
        with self.assertRaisesRegex(ValueError, "county coverage changed"):
            cdc_records(source, fetch=publish(3143))
        self.assertEqual(COUNTIES, {2023: 3143, 2024: 3144, 2025: 3143})

    def test_refuses_truncation_duplicate_counties_unexpected_measure_and_silent_unit_inference(self):
        source = next(s for s in registry_sources() if s["id"] == "cdc-places-obesity-2025")
        def fetch(original):
            return lambda url, *, host, limit: json.dumps(original).encode("utf-8")
        with self.assertRaisesRegex(ValueError, "coverage changed"):
            cdc_records(source, fetch=fetch(source_rows(count=51)))
        duplicated = source_rows()
        duplicated[1]["countyfips"] = duplicated[0]["countyfips"]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            cdc_records(source, fetch=fetch(duplicated))
        invalid = source_rows()
        invalid[0]["obesity_crudeprev"] = "155.0"
        with self.assertRaisesRegex(ValueError, "Out-of-range"):
            cdc_records(source, fetch=fetch(invalid))
        changed = copy.deepcopy(source)
        changed["sourceId"] = "arbitrary"
        with self.assertRaisesRegex(ValueError, "Unapproved"):
            cdc_records(changed, fetch=fetch(source_rows()))
        unexpected = source_rows()
        unexpected[0]["unapproved_column"] = "new"
        with self.assertRaisesRegex(ValueError, "unrequested"):
            cdc_records(source, fetch=fetch(unexpected))

    def test_refresh_preserves_separate_treasury_and_cdc_publisher_provenance(self):
        t=json.loads((ROOT / CATALOG).read_text("utf-8"))
        c=registry_sources()[:1]
        descriptor={**t,"datasets":[t["datasets"][0],c[0]]}
        def fake(item):
            if item.get("provider")=="cdc-places":
                return [{"record_date": "2023-12-31",
                         "countyfips": "00001", "obesity_crudeprev": "18.2"}]
            return [{"record_date": "2023-01-01", "tot_pub_debt_out_amt": "123.45"}]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            stats=refresh(root=root,catalog=descriptor,loader=fake)
            self.assertEqual(stats["datasets"],2)
            index=json.loads((root/"publication/source-library/index.json").read_text("utf-8"))
            by_id={d["id"]:d for d in index["datasets"]}
            self.assertEqual(by_id[c[0]["id"]]["publisher"],
                             "Centers for Disease Control and Prevention")
            self.assertEqual(by_id[c[0]["id"]]["dateBasis"],"publisher-release-year-marker")
            self.assertEqual(by_id[t["datasets"][0]["id"]]["publisher"],t["publisher"])


if __name__ == "__main__":
    unittest.main()
