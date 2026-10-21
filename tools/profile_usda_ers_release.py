"""Source-backed profile of the genuine USDA ERS September 2026 farm archive.

This is a reconnaissance gate, NOT a published dataset. It consumes one ZIP
member through a bounded streaming CSV parser to EOF (CRC checked by zipfile).
No input CSV table or publisher measurement is modified or rewritten.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
from io import BytesIO, TextIOWrapper
import json
import re
import zipfile

from tools.probe_usda_ers_archive import (
    MAX_MEMBER, PUBLISHER_PAGE, SOURCE_URL, USDAProbeError, fetch_original,
    inspect_original, require,
)

EXPECTED_CSV = "FarmIncome_WealthStatisticsData_September2026.csv"
HEADERS = ("Year", "State", "artificialKey", "VariableDescriptionTotal",
           "VariableDescriptionPart1", "VariableDescriptionPart2", "Amount",
           "unit_desc", "PublicationDate", "Source", "ChainType_GDP_Deflator")
MAX_ROWS = 5_000_000
MAX_CELL = 32_768
KEYWORDS = re.compile(
    r"net farm income|total cash receipts|production expenses|"
    r"cash receipts from (marketings|crops|animals)|"
    r"total expenses", re.I,
)


def profile(raw, resolved=SOURCE_URL):
    info = inspect_original(raw, resolved=resolved)
    require(info["csvEntryCount"] == 1 and
            info["csvMembers"][0]["filename"] == EXPECTED_CSV,
            "USDA ERS expected single original CSV filename changed")
    rows = 0
    states = Counter()
    years = Counter()
    publication = Counter()
    sources = Counter()
    categories = {}
    matches = defaultdict(lambda: {"rows": 0, "units": Counter(),
                                   "states": Counter(), "years": Counter(),
                                   "examples": []})
    key_collision = set()
    duplicate_samples = []
    bad = Counter()
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        member = archive.getinfo(EXPECTED_CSV)
        require(1000 < member.file_size <= MAX_MEMBER and
                member.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),
                "Original USDA CSV decompression bounds not acceptable")
        with archive.open(member) as original:
            with TextIOWrapper(original, encoding="utf-8-sig", errors="strict", newline="") as text:
                reader = csv.DictReader(text, restkey="_extra", restval=None, strict=True)
                require(tuple(reader.fieldnames or ()) == HEADERS,
                        "USDA ERS original CSV columns changed")
                for row in reader:
                    rows += 1
                    require(rows <= MAX_ROWS, "USDA ERS CSV exceeds bounded row budget")
                    require("_extra" not in row and
                            all(type(row.get(key)) is str and
                                len(row[key]) <= MAX_CELL for key in HEADERS),
                            "USDA original record invalid or oversized")
                    for col in HEADERS:
                        if "\x00" in row[col]:
                            raise USDAProbeError("NUL byte in publisher data")
                    state, year, key = row["State"], row["Year"], row["artificialKey"]
                    states[state] += 1
                    years[year] += 1
                    publication[row["PublicationDate"]] += 1
                    sources[row["Source"]] += 1
                    desc = (row["VariableDescriptionTotal"],row["VariableDescriptionPart1"],
                            row["VariableDescriptionPart2"], row["ChainType_GDP_Deflator"])
                    if key in categories and categories[key] != desc:
                        bad["key-description-or-chain-collision"] += 1
                    categories.setdefault(key, desc)
                    if len(key_collision) < 2_000_000:
                        signature=(state,year,key)
                        if signature in key_collision and len(duplicate_samples)<5:
                            duplicate_samples.append(list(signature))
                        key_collision.add(signature)
                    if KEYWORDS.search(" ".join(desc)):
                        m=matches[key]
                        m["rows"]+=1
                        m["units"][row["unit_desc"]]+=1
                        m["states"][state]+=1
                        m["years"][year]+=1
                        if len(m["examples"])<3:
                            m["examples"].append({field:row[field] for field in HEADERS})
                # Exhausted the original ZipExtFile (zipfile enforces original CRC).
    require(rows >= 10_000, "Unexpectedly small USDA publisher archive")
    require(not bad, "USDA artificialKey identity was not stable")
    selected = sorted(({
        "key": k,
        "description": list(categories[k]),
        "rows": val["rows"],
        "units": dict(val["units"].most_common(12)),
        "stateCount": len(val["states"]),
        "years": [min(val["years"]),max(val["years"])],
        "examples": val["examples"]
    } for k,val in matches.items()), key=lambda x:(x["description"][0], x["key"]))
    return {
        "publisher": "USDA Economic Research Service",
        "publisherPage": PUBLISHER_PAGE,
        "requestUrl": SOURCE_URL,
        "resolvedUrl": resolved,
        "archiveBytes":len(raw),
        "archiveSha256": info["originalZipSha256"],
        "memberName":EXPECTED_CSV,
        "memberCompressedBytes":member.compress_size,
        "memberOriginalBytes":member.file_size,
        "memberCRC32":format(member.CRC,"08x"),
        "memberCRCVerifiedByFullStream":True,
        "csvHeader":list(HEADERS),
        "recordCount":rows,
        "stateCount":len(states),
        "stateIdentities":sorted(states),
        "yearCount":len(years),
        "yearRange":[min(years),max(years)],
        "publisherPublicationDateCount":len(publication),
        "publicationDateSamples":publication.most_common(10),
        "sourceLabels":sources.most_common(10),
        "artificialKeyCount":len(categories),
        "duplicateIdentitySamples":duplicate_samples,
        "matches":selected,
        "observedAt":datetime.now(timezone.utc).isoformat(),
        "notYetMirrored":True,
    }


def main():
    raw,url=fetch_original()
    result=profile(raw,url)
    print(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=True))


if __name__=="__main__":
    main()
