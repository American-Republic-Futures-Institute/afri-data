"""Offline threat and source-contract tests for USDA NASS DATA-23A."""
import gzip,io,unittest
from urllib.request import Request
from tools.probe_usda_nass import ProbeError,NoRedirect,inspect_prefix,source_url,safe_url,MAX_EXPANDED
HEADER="SOURCE_DESC\tSECTOR_DESC\tCOMMODITY_DESC\tSTATISTICCAT_DESC\tUNIT_DESC\tDOMAIN_DESC\tAGG_LEVEL_DESC\tYEAR\tFREQ_DESC\tREFERENCE_PERIOD_DESC\tSTATE_ALPHA\tCOUNTY_CODE\tVALUE"
ROW="SURVEY\tCROPS\tCORN\tAREA HARVESTED\tACRES\tTOTAL\tSTATE\t2025\tANNUAL\tYEAR\tVA\t\t(D)"
def fixture(h=HEADER,r=ROW,n=8):
    data=("\n".join([h]+[r]*n)+"\n").encode()
    return gzip.compress(data)[:-8]
class TestNASS(unittest.TestCase):
    def test_allowlisted_official_identity(self):
        u=source_url("crops","20261022")
        self.assertTrue(safe_url(u))
        for bad in (u.replace("https:","http:"),u+"?download=true",u.replace("nass.usda.gov","nass.usda.gov.attacker.test"),u.replace("/datasets/","/datasets/../")):
            self.assertFalse(safe_url(bad))
    def test_prefix_preserves_suppression_and_is_not_full_custody(self):
        x=inspect_prefix(fixture())
        self.assertEqual(x["observedFieldCount"],13)
        self.assertEqual(x["previewExamples"][0]["VALUE"],"(D)")
        self.assertFalse(x["fullGzipCRCVerified"])
        self.assertEqual(x["completePreviewRows"],8)
    def test_unsafe_column_definitions_rejected(self):
        for h in (HEADER.replace("YEAR","STATE_ALPHA"),HEADER.replace("UNIT_DESC","UNKNOWN_UNIT")):
            with self.assertRaises(ProbeError):inspect_prefix(fixture(h=h))
    def test_unsafe_row_shape_and_width_rejected(self):
        for r in (ROW+"\textra",ROW+"X"*140000):
            with self.assertRaises(ProbeError):inspect_prefix(fixture(r=r))
    def test_gzip_bomb_and_truncation_rejected(self):
        with self.assertRaises(ProbeError):inspect_prefix(b"not a gzip stream indeed")
        with self.assertRaises(ProbeError):inspect_prefix(fixture()[:18])
        bomb=gzip.compress((HEADER+"\n"+ROW+"\n").encode()+b"X"*(MAX_EXPANDED+100))[:-8]
        with self.assertRaises(ProbeError):inspect_prefix(bomb)
    def test_unapproved_redirect_rejected(self):
        with self.assertRaises(ProbeError):
            NoRedirect().redirect_request(Request(source_url("crops","20261022")),None,302,"redirect",{},"https://evil.example/steal")
if __name__=="__main__": unittest.main()
