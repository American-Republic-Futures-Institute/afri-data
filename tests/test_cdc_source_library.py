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


def source_rows(field="obesity_crudeprev", count=COUNTIES):
    return [
        {"countyfips": f"{n + 1:05d}", "countyname": "Synthetic County " + str(n),
         "stateabbr": "VA", field: "18.2", field.replace("_crudeprev", "_crude95ci"): "(16.9, 19.5)"}
        for n in range(count)
    ]


class CdcOriginalSourceTests(unittest.TestCase):
    def test_official_2023_2024_2025_registrations_and_six_measure_allowlist(self):
        sources = registry_sources()
        self.assertEqual(len(sources), 18)
        self.assertEqual(len({s["id"] for s in sources}), 18)
        self.assertEqual({s["releaseYear"] for s in sources}, set(KNOWN))
        self.assertEqual({s["indicatorStem"] for s in sources}, MEASURES)
        treasury = json.loads((ROOT / CATALOG).read_text("utf-8"))
        validate_catalog({**treasury, "datasets": treasury["datasets"] + sources})
        self.assertEqual(len(treasury["datasets"]) + len(sources), 29)

    def test_stores_original_modeled_value_interval_and_separate_release_marker(self):
        source = next(s for s in registry_sources() if s["id"] == "cdc-places-obesity-2025")
        captured = []
        def get(url, *, host, limit):
            captured.append((url, host, limit))
            return json.dumps(source_rows()).encode("utf-8")
        rows = cdc_records(source, fetch=get)
        self.assertEqual(len(rows), COUNTIES)
        self.assertEqual(rows[0]["obesity_crudeprev"], "18.2")
        self.assertEqual(rows[0]["obesity_crude95ci"], "(16.9, 19.5)")
        self.assertEqual(rows[0]["record_date"], "2025-12-31")
        self.assertEqual(rows[0]["model_reference_year"], "2023")
        self.assertEqual(rows[0]["time_basis"], "publisher_release_year_marker_not_survey_date")
        self.assertEqual(captured[0][1:], ("data.cdc.gov", 3500000))
        self.assertTrue(captured[0][0].startswith(BASE + "i46a-9kgh.json?"))
        self.assertIn("%24select=", captured[0][0])

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
