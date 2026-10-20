"""Source-preserving Census ACS 2024 five-year median-household-income adapter.

This parser is intentionally offline-first. Census requires a user-provisioned
API key for live requests; no keys are stored in code, metadata or published
artifact manifests. Source response bytes must be captured and SHA-256-hashed
before any reviewed release can be staged.
"""
from __future__ import annotations

import json
import math
from decimal import Decimal, InvalidOperation

ACS_YEAR = 2024
ESTIMATE = "B19013_001E"
MOE = "B19013_001M"
OFFICIAL_URL = "https://api.census.gov/data/2024/acs/acs5"
TABLE = "B19013"
# Sentinel codes denote missing or nonapplicable Census statistics, never zero.
MISSING_CODES = frozenset({"", "null", "-666666666", "-888888888", "-999999999", "-555555555"})

def parse_acs_state_income(original: bytes) -> list[dict]:
    """Project official header-aligned JSON; retain estimate and MOE separately."""
    try:
        table=json.loads(original.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Invalid ACS source response") from exc
    if not isinstance(table,list) or len(table)<2 or not isinstance(table[0],list):
        raise ValueError("Missing ACS table header or source values")
    fields=table[0]
    expected={"NAME",ESTIMATE,MOE,"state"}
    if len(fields)!=len(set(fields)) or not expected.issubset(fields):
        raise ValueError("Unexpected ACS header schema")
    results=[]
    seen=set()
    for line in table[1:]:
        if not isinstance(line,list) or len(line)!=len(fields):
            raise ValueError("Invalid ACS row width")
        row=dict(zip(fields,line))
        geoid=row["state"]
        if not isinstance(geoid,str) or len(geoid)!=2 or not geoid.isdigit() or geoid in seen:
            raise ValueError("Duplicate or invalid state FIPS")
        seen.add(geoid)
        def parse_number(value,kind):
            if value is None or str(value).strip() in MISSING_CODES:
                return None
            try:
                decimal=Decimal(str(value))
                if not decimal.is_finite() or decimal<0 or decimal>1_000_000_000:
                    raise ValueError("Out-of-range ACS "+kind)
                return int(decimal) if decimal==decimal.to_integral_value() else float(decimal)
            except (InvalidOperation, ValueError) as exc:
                raise ValueError("Invalid ACS "+kind) from exc
        estimate=parse_number(row[ESTIMATE],"estimate")
        margin=parse_number(row[MOE],"MOE")
        if estimate is None or margin is None:
            if estimate is not None or margin is not None:
                raise ValueError("Incomplete estimate/MOE pair")
            status="not_available"
        else:
            status="available"
        results.append({"geoid":geoid,"name":row["NAME"],"year":ACS_YEAR,
                        "referencePeriod":"2020-2024 five-year ACS",
                        "value":estimate,"marginOfError":margin,
                        "status":status,"unit":"USD","statistic":"survey_estimate",
                        "sourceVariables":[ESTIMATE,MOE]})
    return sorted(results,key=lambda x:x["geoid"])


def parse_acs_table_based_income(original: bytes) -> list[dict]:
    """Project only official 0400000USxx rows from ACS 2024 5YR B19013 .dat.

    The entire table-based Summary File is archived byte-for-byte, including
    other geography levels. This function does not derive any median or MOE.
    Census's table-based names E001/M001 identify the same B19013 estimate
    and 90-percent MOE that the Census API exposes as B19013_001E/_001M.
    """
    import csv
    import io
    from pipelines.census_state_population import FIPS
    from tools.stat05_geography import STATE_NAMES

    try:
        decoded=original.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("Invalid UTF-8 in original Census table-based file") from exc
    source=csv.DictReader(io.StringIO(decoded),delimiter="|")
    required=["GEO_ID","B19013_E001","B19013_M001"]
    if source.fieldnames!=required:
        raise ValueError("Unexpected official ACS 2024 5YR B19013 table-based header")
    rows=[]
    found=set()
    for raw in source:
        if None in raw or any(value is None for value in raw.values()):
            raise ValueError("Wrong column width in official ACS B19013 table")
        geoid=raw["GEO_ID"]
        if not geoid.startswith("0400000US"):
            continue
        fips=geoid.removeprefix("0400000US")
        if fips not in FIPS or fips not in STATE_NAMES or fips in found:
            raise ValueError("Unexpected or duplicate publisher state-equivalent GEO_ID")
        found.add(fips)

        def number(value,field,*,positive=False):
            code=value.strip()
            if code in MISSING_CODES:
                return None
            if not code.isascii() or not code.isdecimal():
                raise ValueError("Unexpected Census "+field+" sentinel or numeric field")
            amount=int(code)
            if (positive and amount<=0) or amount>1_000_000_000:
                raise ValueError("Invalid original Census "+field+" integer")
            return amount

        estimate=number(raw["B19013_E001"],"income estimate",positive=True)
        moe=number(raw["B19013_M001"],"margin of error")
        if (estimate is None)!=(moe is None):
            raise ValueError("Publisher estimate/MOE suppression must be preserved as a pair")
        rows.append({
            "geoid":fips,"name":STATE_NAMES[fips],"year":ACS_YEAR,
            "referencePeriod":"2020-2024 five-year ACS",
            "value":estimate,"marginOfError":moe,
            "status":"not_available" if estimate is None else "available",
            "unit":"USD","statistic":"survey_estimate",
            "sourceVariables":[ESTIMATE,MOE],
        })
    if found!=set(FIPS) or len(rows)!=52:
        raise ValueError("ACS 2024 publisher coverage differs from 52 state-equivalents")
    return sorted(rows,key=lambda item:item["geoid"])
