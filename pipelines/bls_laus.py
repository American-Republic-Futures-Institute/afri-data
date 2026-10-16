"""Strict source-preserving BLS Local Area Unemployment Statistics adapter.

Parses tab-separated \`la.data.2.AllStatesU\` rows by an explicit allowlist of
unadjusted state unemployment-rate series IDs. No county assumption, monthly
data aggregation or automatic seasonality coercion is permitted.
"""
from __future__ import annotations
import csv
import io
import math
import re

SOURCE_DATA_URL="https://download.bls.gov/pub/time.series/la/la.data.2.AllStatesU"
SOURCE_SERIES_URL="https://download.bls.gov/pub/time.series/la/la.series"
SOURCE_AREA_URL="https://download.bls.gov/pub/time.series/la/la.area"
STATE_RATE_SERIES=re.compile(r"^LAUST(?P<state>[0-9]{2})0000000000003$")
ANNUAL="M13"

def parse_laus_state_annual(original: bytes, year: int) -> list[dict]:
    """Return annual published rate rows, with strict source-series semantics."""
    if not isinstance(year,int) or isinstance(year,bool) or year<1990 or year>2100:
        raise ValueError("Invalid LAUS publication year")
    try:
        stream=io.StringIO(original.decode("utf-8-sig"))
    except UnicodeError as exc:
        raise ValueError("Invalid BLS source encoding") from exc
    reader=csv.DictReader(stream,delimiter="\t")
    expected={"series_id","year","period","value","footnote_codes"}
    if not reader.fieldnames or not expected.issubset({x.strip() for x in reader.fieldnames}):
        raise ValueError("Unrecognized LAUS data schema")
    results={}
    for raw in reader:
        row={k.strip():str(v or "").strip() for k,v in raw.items() if k is not None}
        match=STATE_RATE_SERIES.fullmatch(row.get("series_id",""))
        if not match or row.get("year")!=str(year) or row.get("period")!=ANNUAL:
            continue
        state=match["state"]
        if state in results:
            raise ValueError("Duplicate LAUS rate by state/year")
        try:
            value=float(row["value"])
        except ValueError as exc:
            raise ValueError("Invalid LAUS unemployment value") from exc
        if not math.isfinite(value) or not 0<=value<=100:
            raise ValueError("Invalid LAUS unemployment rate range")
        # Preserve the original official BLS qualifiers; the source-aware
        # release parser will validate these codes against la.footnote.
        raw_codes=row["footnote_codes"]
        if not re.fullmatch(r"(?:[A-Z](?:[,; ]+[A-Z])*)?", raw_codes):
            raise ValueError("Unsupported BLS source footnote-code notation")
        codes=sorted(set(code for code in re.split(r"[,; ]+",raw_codes) if code))
        results[state]={"geoid":state,"year":year,"value":value,
                        "unit":"percent","statistic":"published_estimate",
                        "referencePeriod":"annual_average",
                        "seasonalAdjustment":"not_seasonally_adjusted",
                        "status":"available","seriesId":row["series_id"],
                        "footnoteCodes":codes}
    if not results:
        raise ValueError("No LAUS annual unadjusted state unemployment rates found")
    return [results[k] for k in sorted(results)]
