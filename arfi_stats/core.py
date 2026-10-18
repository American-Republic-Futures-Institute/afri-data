"""ARFI-StatKit: data-agnostic, pre-publication statistical chart models.

This is a bounded adapter around NumPy's established binning/quantile routines.
It never verifies government source identity, grants methodological authority,
imputes values, weights respondents, or performs cross-release joins.

Source verification, statistical method eligibility, reviewer approval, and
public chart admission are separate system boundaries (STAT-01/STAT-02).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from hashlib import sha256
import json
import math
import re
from types import MappingProxyType
from typing import Any

import numpy as np

VERSION = "0.1.0"
CONTRACT = "ARFI-StatChartPreview/1.0.0"
STATUS = frozenset(("available", "not_available", "no_record", "suppressed",
                    "not_applicable", "unknown"))
CHARTS = frozenset(("histogram", "ecdf", "boxplot", "frequency", "scatter",
                    "time-series", "interval"))
METHODS = MappingProxyType({
    "histogram": "numpy.histogram/1",
    "ecdf": "numpy.unique-cumsum/1",
    "boxplot": "numpy.quantile-linear-tukey/1",
    "frequency": "categorical-count/1",
    "scatter": "source-paired-points/1",
    "time-series": "source-period-points/1",
    "interval": "publisher-supplied-bounds/1",
})
MAX_ROWS = 100_000
MAX_GROUPS = 64
MAX_BINS = 64
MAX_SERIES_POINTS = 100_000
MAX_CATEGORIES = 500
NAME = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,79}$")
PERIOD = re.compile(r"^\d{4}(?:-\d{2}-\d{2})?$")


def require(ok: Any, message: str) -> None:
    if not ok:
        raise ValueError("ARFI StatKit rejected: " + message)


def field(name: Any) -> str:
    require(isinstance(name, str) and NAME.fullmatch(name) is not None,
            "column names must be simple bounded identifiers")
    return name


def number(value: Any) -> float:
    require(type(value) in (float, int) and abs(value) <= 2**53 - 1 and
            math.isfinite(value),
            "values must be finite safe-range numbers, not booleans, infinities or NaN")
    require(abs(value) <= 2**53 - 1,
            "numeric values exceed the safe floating-point integer range")
    return float(value)


def text(value: Any, *, max_len: int = 160) -> str:
    require(isinstance(value, str) and 0 < len(value) <= max_len and
            not any(ord(char) < 32 for char in value),
            "text dimensions must contain bounded printable values")
    return value


def segment_value(value: Any) -> str:
    if type(value) is int:
        number(value)
        return str(value)
    if type(value) is float:
        return str(number(value))
    return text(value)


def where_filter(where: Any) -> dict[str, list]:
    if where is None:
        return {}
    require(isinstance(where, dict) and len(where) <= 6,
            "filters must use a bounded equality-inclusion mapping")
    cleaned = {}
    for key, options in where.items():
        field(key)
        require(type(options) in (tuple, list) and 1 <= len(options) <= 100,
                "filter choices must be explicit allowlisted values")
        values = []
        for item in options:
            if isinstance(item, str):
                values.append(text(item))
            elif type(item) in (float, int):
                values.append(number(item))
            elif type(item) is bool:
                values.append(item)
            else:
                require(False, "unsupported filter value")
        cleaned[key] = values
    return {key: cleaned[key] for key in sorted(cleaned)}


def validate_input(rows: Any, *, columns: tuple[str, ...], segment: str | None,
                   availability: str, where: Any, unit: str) -> tuple[list, dict, dict]:
    require(isinstance(rows, (list, tuple)) and len(rows) <= MAX_ROWS,
            "input must be a bounded list or tuple of observation objects")
    for column in columns:
        field(column)
    if segment is not None:
        field(segment)
    field(availability)
    text(unit, max_len=80)
    filters = where_filter(where)
    selected = []
    summary = {key: 0 for key in sorted(STATUS)}
    for row in rows:
        require(type(row) is dict, "every observation must be a plain object")
        require(all(key in row for key in (*columns, availability,
                *((segment,) if segment is not None else ()), *filters)),
                "required column, group, availability or filter missing")
        if not all(row[key] in candidates for key, candidates in filters.items()):
            continue
        state = row[availability]
        require(type(state) is str and state in STATUS, "unrecognized missingness classification")
        if segment is not None:
            segment_value(row[segment])
        summary[state] += 1
        selected.append(row)
    require(len({segment_value(row[segment]) for row in selected}) <= MAX_GROUPS
            if segment is not None else True,
            "too many visible series")
    return selected, summary, filters


def grouped(rows: list[dict], *, columns: tuple[str, ...], segment: str | None,
            availability: str) -> list[tuple[str, list[dict], dict]]:
    groups = defaultdict(list)
    for row in rows:
        groups[segment_value(row[segment]) if segment else "All observations"].append(row)
    built = []
    for label in sorted(groups):
        data = groups[label]
        counts = {key: 0 for key in sorted(STATUS)}
        for row in data:
            state = row[availability]
            counts[state] += 1
            if state == "available":
                for col in columns:
                    require(row[col] is not None, "available rows cannot carry null measures")
            else:
                require(all(row[col] is None for col in columns),
                        "unavailable observations cannot hide numeric measurements")
        built.append((label, data, counts))
    return built


def digest_input(rows: list[dict], *, columns: tuple[str, ...], segment: str | None,
                 availability: str, filters: dict, params: dict) -> str:
    keys = sorted(set((*columns, availability, *((segment,) if segment else ()))))
    values = sorted(json.dumps({k: row[k] for k in keys}, sort_keys=True,
                               separators=(",", ":"), ensure_ascii=False, allow_nan=False)
                    for row in rows)
    material = {"rows": values, "filters": filters, "parameters": params,
                "version": VERSION}
    return sha256(json.dumps(material, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def model(kind: str, rows: Any, *, x: str, y: str | None = None,
          segment: str | None = None, availability: str = "availability",
          where: dict | None = None, unit: str = "untyped",
          params: dict | None = None) -> tuple[dict, list, list]:
    require(kind in CHARTS, "unsupported chart primitive")
    columns = (x,) if y is None else (x, y)
    selected, summary, filters = validate_input(
        rows, columns=columns, segment=segment, availability=availability,
        where=where, unit=unit)
    measures = (y,) if kind in ("interval", "time-series") else columns
    series = grouped(selected, columns=measures, segment=segment, availability=availability)
    options = params or {}
    base = {
        "kind": CONTRACT, "version": VERSION, "chartType": kind,
        "fields": {"x": x, "y": y, "segment": segment,
                   "availability": availability, "unit": unit},
        "selection": {"inputRows": len(rows), "selectedRows": len(selected),
                      "filters": filters, "missingness": summary},
        "algorithm": {"methodId": METHODS[kind], "numpyVersion": np.__version__,
                      "parameters": options},
        "inputFingerprint": digest_input(
            selected, columns=columns, segment=segment,
            availability=availability, filters=filters,
            params={"kind": kind, "fields": {"x": x, "y": y, "segment": segment,
                                           "availability": availability, "unit": unit},
                    **options}),
        "series": [],
        "limitations": [
            "Exploratory, synthetic-or-caller-supplied evidence; not independently source-verified.",
            "Observations are not assumed representative or statistically independent.",
            "Numerical visualizations do not establish statistical or causal inference."
        ] + (["Floating-point distribution bins are approximate; exact monetary totals require decimal or integer minor units."]
             if unit in ("USD", "EUR", "GBP") else []),
        "authority": {"sourceVerified": False, "publicationAuthorized": False,
                      "crossSourceAuthorized": False, "statisticalInferenceAuthorized": False,
                      "causalInferenceAuthorized": False}
    }
    return base, series, selected


def histogram(rows: Any, *, x: str, segment: str | None = None,
              bins: int | str = "fd", scale: str = "count",
              availability: str = "availability", where: dict | None = None,
              unit: str = "untyped") -> dict:
    """Common X bin boundaries across all groups; Y = count or within-group share."""
    require((type(bins) is int and 1 <= bins <= MAX_BINS) or
            bins in ("fd", "sturges", "sqrt", "auto"),
            "bin rule must be fd, sturges, sqrt, auto, or 1..64")
    require(scale in ("count", "proportion"), "Y axis must be count or group proportion")
    base, parts, _ = model("histogram", rows, x=x, segment=segment,
                          availability=availability, where=where, unit=unit,
                          params={"bins": bins, "scale": scale})
    observed = [number(row[x]) for _, items, _ in parts for row in items
                if row[availability] == "available"]
    if not observed:
        base["limitations"].append("No available observations; no bins constructed.")
        return base
    actual_bins = bins
    if isinstance(bins, str) and len(observed) == 1:
        actual_bins = 1
    edges = np.histogram_bin_edges(observed, bins=actual_bins)
    if len(edges) - 1 > MAX_BINS:
        edges = np.linspace(float(edges[0]), float(edges[-1]), MAX_BINS + 1)
        base["algorithm"]["parameters"]["boundedBinOverride"] = MAX_BINS
    base["axis"] = {"x": x, "y": scale, "sharedBinEdges": True}
    for label, data, counts in parts:
        values = [number(row[x]) for row in data if row[availability] == "available"]
        freqs, _ = np.histogram(values, bins=edges)
        n = len(values)
        base["series"].append({
            "label": label, "n": n, "missingness": counts,
            "points": [{"low": float(edges[i]), "high": float(edges[i + 1]),
                        "count": int(count), "value": float(count / n) if scale == "proportion" and n else
                        float(count) if scale == "proportion" else int(count)}
                       for i, count in enumerate(freqs)]
        })
    return base


def ecdf(rows: Any, *, x: str, segment: str | None = None,
         availability: str = "availability", where: dict | None = None,
         unit: str = "untyped") -> dict:
    base, parts, _ = model("ecdf", rows, x=x, segment=segment,
                          availability=availability, where=where, unit=unit)
    base["axis"] = {"x": x, "y": "cumulative share", "range": [0, 1]}
    for label, data, counts in parts:
        vals = [number(row[x]) for row in data if row[availability] == "available"]
        unique, frequencies = np.unique(vals, return_counts=True)
        cumulative = np.cumsum(frequencies)
        base["series"].append({
            "label": label, "n": len(vals), "missingness": counts,
            "points": [{"x": float(v), "countAtX": int(c),
                        "cumulative": float(n / len(vals))}
                       for v, c, n in zip(unique, frequencies, cumulative)]
        })
    return base


def boxplot(rows: Any, *, x: str, segment: str | None = None,
            availability: str = "availability", where: dict | None = None,
            unit: str = "untyped") -> dict:
    """Tukey 1.5*IQR rule; use observed min/max and outliers, not a CI."""
    base, parts, _ = model("boxplot", rows, x=x, segment=segment,
                          availability=availability, where=where, unit=unit,
                          params={"quantile": "linear", "whisker": "tukey-1.5-iqr"})
    base["axis"] = {"x": segment or "All observations", "y": x}
    for label, data, counts in parts:
        vals = np.asarray([number(row[x]) for row in data
                           if row[availability] == "available"], dtype=float)
        stat = None
        if len(vals):
            q = np.quantile(vals, [.10, .25, .50, .75, .90], method="linear")
            lo, q1, median, q3, hi = (float(z) for z in q)
            fence_lo = q1 - 1.5 * (q3 - q1)
            fence_hi = q3 + 1.5 * (q3 - q1)
            inside = vals[(vals >= fence_lo) & (vals <= fence_hi)]
            stat = {"min": float(np.min(vals)), "max": float(np.max(vals)),
                    "p10": lo, "q1": q1, "median": median, "q3": q3, "p90": hi,
                    "iqr": q3 - q1, "whiskerLow": float(np.min(inside)),
                    "whiskerHigh": float(np.max(inside)),
                    "outliers": [float(v) for v in np.sort(vals[(vals < fence_lo) | (vals > fence_hi)])]}
        base["series"].append({"label": label, "n": len(vals),
                               "missingness": counts, "statistics": stat})
    return base


def frequency(rows: Any, *, x: str, segment: str | None = None,
              scale: str = "count", availability: str = "availability",
              where: dict | None = None) -> dict:
    """Nominal/ordinal category distribution. Categories are never averaged."""
    require(scale in ("count", "proportion"), "frequency scale unsupported")
    base, parts, _ = model("frequency", rows, x=x, segment=segment,
                          availability=availability, where=where,
                          params={"scale": scale})
    base["axis"] = {"x": x, "y": scale}
    for label, data, counts in parts:
        values = [segment_value(row[x]) for row in data
                  if row[availability] == "available"]
        frequencies = Counter(values)
        require(len(frequencies) <= MAX_CATEGORIES,
                "category cardinality requires a reviewed grouping strategy")
        n = len(values)
        base["series"].append({
            "label": label, "n": n, "missingness": counts,
            "points": [{"category": key, "count": count,
                        "value": float(count / n) if scale == "proportion" else count}
                       for key, count in sorted(frequencies.items())]
        })
    return base


def scatter(rows: Any, *, x: str, y: str, segment: str | None = None,
            availability: str = "availability", where: dict | None = None,
            x_unit: str = "untyped", y_unit: str = "untyped") -> dict:
    base, parts, _ = model("scatter", rows, x=x, y=y, segment=segment,
                          availability=availability, where=where, unit=y_unit,
                          params={"xUnit": x_unit, "trendline": False})
    base["axis"] = {"x": x, "y": y, "xUnit": x_unit, "yUnit": y_unit}
    for label, data, counts in parts:
        pairs = [{"x": number(row[x]), "y": number(row[y])}
                 for row in data if row[availability] == "available"]
        require(len(pairs) <= MAX_SERIES_POINTS, "too many scatter observations")
        base["series"].append({"label": label, "n": len(pairs),
                               "missingness": counts, "points": pairs})
    base["limitations"].append("A scatter plot is not evidence of correlation significance or causation.")
    return base


def time_series(rows: Any, *, x: str, y: str, segment: str | None = None,
                availability: str = "availability", where: dict | None = None,
                unit: str = "untyped") -> dict:
    base, parts, _ = model("time-series", rows, x=x, y=y, segment=segment,
                          availability=availability, where=where, unit=unit)
    base["axis"] = {"x": x, "y": y, "timeOrdering": "ascending",
                    "connectMissing": False, "interpolation": False}
    for label, data, counts in parts:
        points = []
        for row in data:
            raw = row[x]
            require((type(raw) is int and 1000 <= raw <= 9999) or
                    (type(raw) is str and PERIOD.fullmatch(raw) is not None),
                    "period must be an explicit ISO date or four-digit year")
            period = str(raw)
            try:
                if len(period) == 4:
                    require(1000 <= int(period) <= 9999, "invalid year")
                else:
                    date.fromisoformat(period)
            except ValueError as exc:
                raise ValueError("ARFI StatKit rejected: invalid ISO source period") from exc
            points.append({"period": period,
                           "value": number(row[y]) if row[availability] == "available" else None,
                           "availability": row[availability]})
        points.sort(key=lambda z: z["period"])
        require(len(set(len(z["period"]) for z in points)) <= 1,
                "mixed temporal resolutions require a reviewed harmonization method")
        require(len(set(z["period"] for z in points)) == len(points),
                "multiple observations per period require an approved aggregation method")
        base["series"].append({"label": label, "n": counts["available"],
                               "missingness": counts, "points": points})
    base["limitations"].append("Time points are source-reported; no interpolation, change rate or forecast.")
    return base


def intervals(rows: Any, *, x: str, y: str, lower: str, upper: str,
              segment: str | None = None, availability: str = "availability",
              where: dict | None = None, unit: str = "untyped",
              interval_label: str = "publisher-reported interval") -> dict:
    """Plot source-supplied bounds; cannot calculate coverage or statistical significance."""
    text(interval_label)
    for key in (lower, upper):
        field(key)
    base, parts, selected = model("interval", rows, x=x, y=y, segment=segment,
                                  availability=availability, where=where, unit=unit,
                                  params={"lower": lower, "upper": upper,
                                          "intervalLabel": interval_label})
    require(all(lower in row and upper in row for row in selected),
            "publisher interval columns required for every selected record")
    # Bind the actual interval inputs to the fingerprint, not only center values.
    base["inputFingerprint"] = digest_input(
        selected, columns=(x, y, lower, upper), segment=segment,
        availability=availability, filters=base["selection"]["filters"],
        params={"kind": "interval", "lower": lower, "upper": upper, "unit": unit,
                "intervalLabel": interval_label})
    base["axis"] = {"x": x, "y": y, "interval": interval_label}
    for label, data, counts in parts:
        points = []
        for row in data:
            if row[availability] != "available":
                require(row.get(lower) is None and row.get(upper) is None,
                        "missing observations cannot have interval bounds")
                continue
            center = number(row[y])
            low, high = number(row[lower]), number(row[upper])
            require(low <= center <= high, "publisher bounds must contain published estimate")
            points.append({"category": segment_value(row[x]), "estimate": center,
                           "lower": low, "upper": high})
        base["series"].append({"label": label, "n": len(points),
                               "missingness": counts, "points": points})
    base["limitations"].append("Intervals are original source-supplied bounds; no new statistical interval has been calculated.")
    return base
