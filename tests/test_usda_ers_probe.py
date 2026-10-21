"""DATA-21A publisher-origin and bounded archive discovery probes."""
import io
import json
import unittest
import zipfile

from tools.probe_usda_ers_archive import (
    FORMAT, MAX_EXTRACTED, SOURCE_URL, USDAProbeError,
    ExactERSRedirect, inspect_original, safe_publisher_url)


def fixture(name="FarmIncomeState.csv", csv_text=None):
    csv_text = csv_text or (
        "State,Year,Commodity,Value,Unit\n"
        "Virginia,2025,Corn,\"1,200\",USD\n"
        "Alaska,2024,All commodities,\"(D)\",USD\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, csv_text)
        archive.writestr("README.txt", "USDA ERS official release\n")
    return buffer.getvalue()


class USDAERSProbeTests(unittest.TestCase):
    def test_original_zip_is_reported_without_derived_observations(self):
        source = fixture()
        info = inspect_original(source)
        self.assertEqual(info["format"], FORMAT)
        self.assertEqual(info["csvEntryCount"], 1)
        self.assertEqual(info["originalZipBytes"], len(source))
        self.assertEqual(len(info["originalZipSha256"]), 64)
        self.assertTrue(info["noDataPublished"])
        self.assertFalse(info["publicationClaimed"])
        self.assertEqual(info["csvMembers"][0]["header"],
                         ["State", "Year", "Commodity", "Value", "Unit"])

    def test_official_archive_path_and_host_cannot_be_substituted(self):
        self.assertTrue(safe_publisher_url(SOURCE_URL))
        for url in (
            "http://www.ers.usda.gov/media/29517/september-3-2026-release.zip",
            "https://ers.usda.gov.evil.test/media/29517/september-3-2026-release.zip",
            "https://evil.test/media/29517/september-3-2026-release.zip",
            "https://www.ers.usda.gov/media/29517/other.zip",
            "https://www.ers.usda.gov/media/../september-3-2026-release.zip",
            SOURCE_URL+"?download=1",
            SOURCE_URL+"#fragment",
        ):
            with self.subTest(url=url):
                self.assertFalse(safe_publisher_url(url))
                with self.assertRaises(USDAProbeError):
                    inspect_original(fixture(),resolved=url)

    def test_malicious_member_path_and_duplicate_columns_fail(self):
        for name in ("../x.csv", "/etc/passwd.csv", "safe\\..\\evil.csv"):
            with self.subTest(path=name),self.assertRaises(USDAProbeError):
                inspect_original(fixture(name=name))
        with self.assertRaises(USDAProbeError):
            inspect_original(fixture(csv_text="State,State\nVA,VA\n"))

    def test_broken_archive_fails(self):
        with self.assertRaises(USDAProbeError):
            inspect_original(b"PK\x03\x04"+b"x"*300)
        bad = bytearray(fixture())
        bad[-1] ^= 0x3f
        with self.assertRaises(USDAProbeError):
            inspect_original(bytes(bad))

    def test_redirect_can_only_target_same_publisher_release(self):
        from urllib.request import Request
        handler=ExactERSRedirect()
        follow="https://ers.usda.gov/sites/default/files/september-3-2026-release.zip"
        req=handler.redirect_request(Request(SOURCE_URL),None,302,"Found",{},follow)
        self.assertEqual(req.full_url,follow)
        with self.assertRaises(USDAProbeError):
            handler.redirect_request(Request(SOURCE_URL),None,302,"Found",{},
                                      "https://attacker.example/september-3-2026-release.zip")


if __name__ == "__main__":
    unittest.main()
