"""Original USDA ERS farm-income/expense state history, never computed indicators.

The 6.23-MB original ZIP is retained byte-for-byte; its approximately 111-MB
CSV is decoded as publisher Windows-1252, streamed to EOF and CRC-checked.
Every projected cell is a publisher-original string. Only 'record_date' and a
custody hash are added for annual partitioning and independent source replay.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from hashlib import sha256
from io import BytesIO, TextIOWrapper
import json
from pathlib import Path
import re
import zipfile

from tools.probe_usda_ers_archive import (
    PUBLISHER_PAGE as SOURCE_PAGE, SOURCE_URL, MAX_ARCHIVE,
    USDAProbeError, fetch_original, inspect_original, require,
)
from tools.profile_usda_ers_release import EXPECTED_CSV, HEADERS

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = Path("catalog/source-library/usda-ers.json")
PROVIDER = "usda-ers"
PUBLISHER = "USDA Economic Research Service"
RELEASE_DATE = "2026-09-03"  # Release date corroborated by ERS source page.
RELEASE_TEXT = "Data as of September 3, 2026."  # Preserve publisher CSV string.
SOURCE_LABEL = "Source: USDA, Economic Research Service, Farm Income and Wealth Statistics"
DATE_BASIS = "usda-ers-annual-reference-year-not-source-release"
UNIT = "$1,000"  # Display label only; 'unit_desc' retains publisher NBSP padding.
ORIGINAL_UNIT = "$1,000" + "\u00a0" * 5
STATES = frozenset(
    "AK AL AR AZ CA CO CT DE FL GA HI IA ID IL IN KS KY LA MA MD ME MI MN MO "
    "MS MT NC ND NE NH NJ NM NV NY OH OK OR PA RI SC SD TN TX US UT VA VT WA "
    "WI WV WY".split()
)
SERIES = {
    "usda-ers-net-farm-income": {
        "prefix": "FIA", "suffix": "NTFI--P",
        "label": "Net farm income", "part1": "Net income", "part2": "Farm income",
    },
    "usda-ers-production-expenses": {
        "prefix": "EXA", "suffix": "PE--EXP",
        "label": "Production expenses, all, excl. operator dwellings",
        "part1": "Production expenses", "part2": "All",
    },
}
MAX_ROWS = 5_000_000
MAX_SELECTED = 8_000
MAX_CELL = 32_768
HEX = re.compile(r"^[0-9a-f]{64}$")
YEAR = re.compile(r"^(19|20)\d{2}$")


class USDAUnavailable(USDAProbeError):
    """Publisher source is missing, mutated or outside the audited series."""


class OriginalUSDARows(list):
    def __init__(self, rows, original_zip, member_crc32, member_bytes):
        super().__init__(rows)
        self.original_zip = original_zip
        self.member_crc32 = member_crc32
        self.member_bytes = member_bytes


def original_path(value):
    require(type(value) is str and HEX.fullmatch(value), "Unsafe ERS archive digest")
    return "publication/source-library/originals/usda-ers/sha256/" + value + ".zip"


def validate_registry(doc):
    require(type(doc) is dict and set(doc) == {
        "schemaVersion","publisher","sourceFamily","sourcePage",
        "sourceZip","refreshCadence","datasetClass","dateBasis",
        "unit","releaseDate","series","description"
    } and doc["schemaVersion"]=="1.0.0" and doc["publisher"]==PUBLISHER and
        doc["sourceFamily"]=="usda-ers-state-farm-finance-september-2026" and
        doc["sourcePage"]==SOURCE_PAGE and doc["sourceZip"]==SOURCE_URL and
        doc["refreshCadence"]=="weekly" and
        doc["datasetClass"]=="source-native-unreviewed" and
        doc["dateBasis"]==DATE_BASIS and doc["unit"]==UNIT and
        doc["releaseDate"]==RELEASE_DATE and
        type(doc["series"]) is list and len(doc["series"])==len(SERIES) and
        type(doc["description"]) is str and len(doc["description"])>=80,
        "Unapproved USDA ERS publisher registry")
    found=set()
    for item in doc["series"]:
        key=item.get("id") if type(item) is dict else None
        expected=SERIES.get(key)
        require(expected is not None and key not in found and
                item.get("variableDescription")==expected["label"] and
                type(item.get("title")) is str and 15<=len(item["title"])<=110 and
                type(item.get("description")) is str and
                50<=len(item["description"])<=420,
                "USDA ERS original source variable is not allowlisted")
        found.add(key)
    return doc


def registry_sources(root=ROOT):
    config=validate_registry(json.loads((Path(root)/REGISTRY).read_text("utf-8")))
    return [{
        "id":item["id"],
        "title":item["title"],
        "description":item["description"],
        "provider":PROVIDER, "publisher":PUBLISHER,
        "domain":"agriculture", "endpoint":SOURCE_URL,
        "sourcePage":SOURCE_PAGE, "unit":UNIT,
        "sourceVariableDescription":item["variableDescription"],
        "releaseDate":RELEASE_DATE,
        "dateBasis":DATE_BASIS, "dateField":"record_date",
        "preferredField":"Amount", "maxRows":MAX_SELECTED,
    } for item in config["series"]]


@lru_cache(maxsize=1)
def download_source():
    original,resolved=fetch_original()
    require(resolved==SOURCE_URL or resolved.startswith("https://ers.usda.gov/") or
            resolved.startswith("https://www.ers.usda.gov/"),
            "USDA government source URL changed")
    return original


def parse_original(raw, *, dataset):
    """Stream full publisher CSV, including nonselected rows, so CRC is checked."""
    selected=SERIES.get(dataset)
    require(selected is not None, "USDA ERS series was not approved")
    require(type(raw) is bytes and 1000 < len(raw) <= MAX_ARCHIVE,
            "Unsafe USDA ERS original ZIP size")
    # Include the immutable original ZIP hash in every source-backed row.
    original_sha=sha256(raw).hexdigest()
    audit=inspect_original(raw)
    require(audit["csvEntryCount"]==1 and
            audit["csvMembers"][0]["filename"]==EXPECTED_CSV,
            "USDA ERS source CSV changed identity")
    collected={}
    visited=0
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            item=archive.getinfo(EXPECTED_CSV)
            require(item.file_size>1000000 and
                    item.file_size<=2_000_000_000 and
                    item.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),
                    "Unexpected USDA decompression contract")
            with archive.open(item) as stream:
                with TextIOWrapper(stream, encoding="cp1252",errors="strict",newline="") as text:
                    reader=csv.DictReader(text,restkey="_extra",restval=None,strict=True)
                    require(tuple(reader.fieldnames or ())==HEADERS,
                            "USDA original CSV columns changed")
                    for source in reader:
                        visited += 1
                        require(visited<=MAX_ROWS and "_extra" not in source and
                                all(type(source.get(k)) is str and
                                    len(source[k])<=MAX_CELL and "\x00" not in source[k]
                                    for k in HEADERS),
                                "Malformed or excessive ERS original source row")
                        key=source["artificialKey"]
                        match=(selected["prefix"]+source["State"]+selected["suffix"])
                        if key!=match:
                            # Match *family* to detect illicit new geography/key mapping.
                            if (key.startswith(selected["prefix"]) and
                                key.endswith(selected["suffix"])):
                                raise USDAUnavailable("Unapproved ERS state or key identity")
                            continue
                        state=source["State"]
                        year=source["Year"]
                        require(state in STATES and YEAR.fullmatch(year) and
                                1910<=int(year)<=2026 and
                                source["VariableDescriptionTotal"]==selected["label"] and
                                source["VariableDescriptionPart1"]==selected["part1"] and
                                source["VariableDescriptionPart2"]==selected["part2"] and
                                source["unit_desc"]==ORIGINAL_UNIT and
                                source["PublicationDate"]==RELEASE_TEXT and
                                source["Source"]==SOURCE_LABEL,
                                "USDA variable, unit, publication or state identity changed")
                        identity=(year,state)
                        require(identity not in collected,
                                "Duplicate original USDA state/year/series")
                        collected[identity] = {
                            **source, "record_date":year+"-12-31",
                            "source_original_sha256":original_sha,
                        }
            # ZIP member CRC is validated on EOF by ZipExtFile.
            crc=format(item.CRC,"08x")
            member_bytes=item.file_size
    except (zipfile.BadZipFile, UnicodeError, csv.Error, EOFError) as exc:
        raise USDAUnavailable("Original ERS ZIP/CSV could not be streamed to EOF") from exc
    require(visited>=400000 and 3500<=len(collected)<=MAX_SELECTED,
            "Unexpected truncation of genuine USDA state farm financial history")
    require({geo for _,geo in collected}==STATES,
            "Original ERS source lost one or more of the 50 states or US aggregate")
    require(all((str(y),state) in collected
                for state in STATES if state!="US"
                for y in range(1960,2026)),
            "Original state historical coverage shrank in 1960–2025")
    require(("2026","US") in collected and ("1910","US") in collected,
            "USDA national long history or forecast period disappeared")
    return OriginalUSDARows([collected[key] for key in sorted(collected)],
                            raw, crc, member_bytes)


def ers_records(spec, fetch=download_source):
    key=spec.get("id")
    require(key in SERIES and spec.get("provider")==PROVIDER and
            spec.get("sourceVariableDescription")==SERIES[key]["label"] and
            spec.get("endpoint")==SOURCE_URL and spec.get("sourcePage")==SOURCE_PAGE and
            spec.get("unit")==UNIT and spec.get("dateBasis")==DATE_BASIS and
            spec.get("releaseDate")==RELEASE_DATE and
            spec.get("preferredField")=="Amount",
            "Unapproved USDA ERS source descriptor")
    return parse_original(fetch(),dataset=key)


def verify_original_file(root,entry):
    key=entry.get("id")
    require(key in SERIES and entry.get("provider")==PROVIDER and
            entry.get("sourceVariableDescription")==SERIES[key]["label"] and
            entry.get("endpoint")==SOURCE_URL and entry.get("sourcePage")==SOURCE_PAGE and
            entry.get("dateBasis")==DATE_BASIS and
            entry.get("releaseDate")==RELEASE_DATE and entry.get("unit")==UNIT and
            entry.get("originalZipPath")==original_path(entry.get("originalZipSha256")) and
            type(entry.get("originalZipBytes")) is int and
            1000<entry["originalZipBytes"]<=MAX_ARCHIVE and
            re.fullmatch(r"[0-9a-f]{8}",entry.get("originalMemberCrc32","")) and
            type(entry.get("originalMemberBytes")) is int and
            entry["originalMemberBytes"]>1000000,
            "USDA ERS original source custody metadata invalid")
    original=(Path(root)/entry["originalZipPath"]).read_bytes()
    require(len(original)==entry["originalZipBytes"] and
            sha256(original).hexdigest()==entry["originalZipSha256"],
            "USDA source publisher ZIP SHA-256 has changed")
    rows=parse_original(original,dataset=key)
    require(len(rows)==entry["rowCount"] and
            rows.member_crc32==entry["originalMemberCrc32"] and
            rows.member_bytes==entry["originalMemberBytes"],
            "USDA ZIP member CRC, size or original rows differ from publication")
    return rows
