"""Offline-only Census county geometry and source-archive integrity regressions."""
from __future__ import annotations

from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import shapefile

from pipelines.census_county_geography import (
    EXPECTED,STATES,parse_county_geometries,stage,archive_members,
)
from tools.validate_geography import validate_geography


def fake_shapefile_zip(*, duplicate=False, invalid_coord=False, metadata=False) -> bytes:
    """3143 clearly synthetic polygons. Never publish these as Census data."""
    shp,shx,dbf=io.BytesIO(),io.BytesIO(),io.BytesIO()
    w=shapefile.Writer(shp=shp,shx=shx,dbf=dbf,shapeType=shapefile.POLYGON)
    w.field("STATEFP","C",2)
    w.field("COUNTYFP","C",3)
    w.field("GEOID","C",5)
    w.field("NAME","C",80)
    states=sorted(STATES)
    for i in range(EXPECTED):
        state=states[i%len(states)]
        county=str(i//len(states)+1).zfill(3)
        geoid=state+county
        if duplicate and i==EXPECTED-1:
            state=states[0];county="001";geoid=state+county
        lon=-120+(i%70)*.5
        lat=25+((i//70)%40)*.5
        if invalid_coord and i==0:
            lon=190
        w.poly([[[lon,lat],[lon,lat+.1],[lon+.1,lat+.1],[lon+.1,lat],[lon,lat]]])
        w.record(state,county,geoid,"Synthetic county "+str(i))
    w.close()
    data=io.BytesIO()
    with zipfile.ZipFile(data,"w",zipfile.ZIP_DEFLATED) as archive:
        for ext,payload in (("shp",shp),("shx",shx),("dbf",dbf)):
            archive.writestr("cb_2023_us_county_20m."+ext,payload.getvalue())
        if metadata:
            archive.writestr("cb_2023_us_county_20m.shp.iso.xml",b"<metadata/>")
            archive.writestr("cb_2023_us_county_20m.shp.ea.iso.xml",b"<metadata/>")
            archive.writestr("cb_2023_us_county_20m.shp.xml",b"<metadata/>")
    return data.getvalue()


class CountyGeographyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original=fake_shapefile_zip()

    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)

    def test_full_county_coverage_without_any_measured_statistics(self):
        geo=parse_county_geometries(self.original)
        self.assertEqual(geo["type"],"FeatureCollection")
        self.assertEqual(len(geo["features"]),3143)
        self.assertEqual(geo["metadata"]["vintage"],2023)
        self.assertEqual(len({f["properties"]["GEOID"] for f in geo["features"]}),3143)
        self.assertNotIn("observations",geo)
        self.assertNotIn("value",geo["features"][0]["properties"])

    def test_separate_geo_index_and_source_byte_fingerprint(self):
        result=stage(self.root,self.original)
        folder=self.root/"publication/geographies/releases"/result["releaseId"]
        self.assertEqual((folder/"original.zip").read_bytes(),self.original)
        self.assertEqual(result["sourceSha256"],sha256(self.original).hexdigest())
        self.assertEqual(validate_geography(self.root),
                         {"geographyReleases":1,"countyFeatures":3143})
        self.assertFalse((self.root/"publication/index.json").exists())

    def test_corrupt_source_zip_rejected(self):
        with self.assertRaisesRegex(ValueError,"Invalid Census cartographic zip"):
            archive_members(b"not a zip")

    def test_traversal_zip_entry_rejected(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,"w") as z:
            for ext in ("shp","shx","dbf"):
                z.writestr("../cb_2023_us_county_20m."+ext,b"malicious")
        with self.assertRaisesRegex(ValueError,"Unexpected county source archive member"):
            archive_members(b.getvalue())


    def test_official_shapefile_iso_metadata_is_allowed_but_not_executed(self):
        """FGDC/ISO sidecars are inert and remain in the original source ZIP."""
        original=fake_shapefile_zip(metadata=True)
        members=archive_members(original)
        self.assertEqual(set(members),{".shp",".shx",".dbf"})
        output=parse_county_geometries(original)
        self.assertEqual(len(output["features"]),EXPECTED)
        saved=stage(self.root,original)
        result=validate_geography(self.root)
        self.assertEqual(result["countyFeatures"],EXPECTED)
        folder=self.root/"publication/geographies/releases"/saved["releaseId"]
        self.assertEqual((folder/"original.zip").read_bytes(),original)

    def test_unrecognized_xml_sidecar_fails_closed(self):
        original=fake_shapefile_zip()
        out=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(out,"w") as target:
            for name in source.namelist():
                target.writestr(name,source.read(name))
            target.writestr("cb_2023_us_county_20m.unapproved.xml",b"<x/>")
        with self.assertRaisesRegex(ValueError,"Unexpected county source archive member"):
            archive_members(out.getvalue())

    def test_duplicate_iso_metadata_sidecar_rejected(self):
        original=fake_shapefile_zip(metadata=True)
        out=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(out,"w") as target:
            for name in source.namelist():
                target.writestr(name,source.read(name))
            target.writestr("cb_2023_us_county_20m.shp.iso.xml",b"<duplicate/>")
        with self.assertRaisesRegex(ValueError,"Duplicate Census county archive member"):
            archive_members(out.getvalue())

    def test_reject_duplicate_fips(self):
        with self.assertRaisesRegex(ValueError,"Duplicate county FIPS"):
            parse_county_geometries(fake_shapefile_zip(duplicate=True))

    def test_reject_invalid_polygon_coordinate(self):
        with self.assertRaisesRegex(ValueError,"Invalid county polygon coordinate"):
            parse_county_geometries(fake_shapefile_zip(invalid_coord=True))

    def test_modifying_geojson_even_with_recomputed_sha_fails_source_replay(self):
        result=stage(self.root,self.original)
        folder=self.root/"publication/geographies/releases"/result["releaseId"]
        geofile=folder/"counties.geojson"
        geo=json.loads(geofile.read_text())
        geo["features"][0]["properties"]["NAME"]="Forged name"
        raw=(json.dumps(geo,sort_keys=True,separators=(",",":"))+"\n").encode()
        geofile.write_bytes(raw)
        manifest_path=folder/"manifest.json"
        manifest=json.loads(manifest_path.read_text())
        manifest["geometry"]["sha256"]=sha256(raw).hexdigest()
        manifest["geometry"]["bytes"]=len(raw)
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,"cannot be replayed"):
            validate_geography(self.root)

    def test_unsafe_symlink_asset_rejected(self):
        result=stage(self.root,self.original)
        folder=self.root/"publication/geographies/releases"/result["releaseId"]
        source=folder/"original.zip"
        source.unlink()
        source.symlink_to(folder/"counties.geojson")
        with self.assertRaisesRegex(ValueError,"symlink"):
            validate_geography(self.root)
