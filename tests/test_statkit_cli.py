"""STAT-00 CLI accepts normalized objects only and never issues public artifacts."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from arfi_stats.__main__ import main, read_json, MAX_BYTES
from arfi_stats import CONTRACT


class StatKitCLITests(unittest.TestCase):
    def test_synthetic_histogram_cli_has_no_publication_authority(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "preview.json"
            fixture = Path(__file__).resolve().parents[1] / "examples/statkit-synthetic.json"
            main(["--chart", "histogram", "--input", str(fixture), "--x", "value",
                  "--segment", "region", "--bins", "fd", "--unit", "percent",
                  "--output", str(output)])
            result = json.loads(output.read_text())
            self.assertEqual(result["kind"], CONTRACT)
            self.assertEqual(result["selection"]["selectedRows"], 6)
            self.assertEqual(result["selection"]["missingness"]["not_available"], 1)
            self.assertEqual(result["series"][0]["label"], "East")
            self.assertFalse(result["authority"]["publicationAuthorized"])

    def test_cli_filter_json_accepts_dict_and_preserves_denominators(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            data=folder/"data.json"
            data.write_text(json.dumps([
                {"value":2,"region":"East","availability":"available"},
                {"value":None,"region":"East","availability":"no_record"},
                {"value":3,"region":"West","availability":"available"}]))
            filt=folder/"filter.json"
            filt.write_text('{"region":["East"]}')
            output=folder/"spec.json"
            main(["--chart","histogram","--input",str(data),"--x","value",
                  "--where",str(filt),"--output",str(output)])
            spec=json.loads(output.read_text())
            self.assertEqual(spec["selection"]["selectedRows"],2)
            self.assertEqual(spec["selection"]["missingness"]["no_record"],1)
            self.assertEqual(spec["series"][0]["n"],1)

    def test_rejects_duplicate_keys_nonfinite_and_nonlist_source(self):
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp)/"input.json"
            for raw,expected in [
                ('[{"x":1,"x":2}]',"Duplicate JSON key"),
                ('[{"x":NaN}]',"Non-finite"),
                ('{"x":2}',"list"),
            ]:
                data.write_text(raw)
                with self.assertRaisesRegex(ValueError,expected):
                    read_json(str(data))
            data.write_text('[{"x":3}]')
            with self.assertRaisesRegex(ValueError,"dict"):
                read_json(str(data),expected="dict")

    def test_minimal_preview_to_stdout_and_no_dynamic_code(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/"input.json"
            source.write_text(json.dumps([{"metric":5,"availability":"available"}]))
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                main(["--chart","histogram","--input",str(source),
                      "--x","metric","--bins","1"])
            spec=json.loads(output.getvalue())
            self.assertEqual(spec["series"][0]["points"][0]["count"],1)
            self.assertFalse(spec["authority"]["statisticalInferenceAuthorized"])


if __name__=="__main__":
    unittest.main()
