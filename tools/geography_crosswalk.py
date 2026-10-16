"""Pure GEOID coverage reconciliation between independently approved sources.

No statistical measurement is modified, imputed, estimated or joined by
geographic display name. A county polygon without observation remains a
visible no-data feature; a measurement without an approved geometry fails.
"""
from __future__ import annotations

import re


def reconcile_county_geoids(geometry_geoids, indicator_geoids,
                            *, expected_missing=frozenset()) -> dict:
    def validate(values,role):
        rows=list(values)
        if not rows or any(not isinstance(x,str) or re.fullmatch(r"[0-9]{5}",x) is None for x in rows):
            raise ValueError("Invalid five-digit county GEOID in "+role)
        if len(rows)!=len(set(rows)):
            raise ValueError("Duplicate county GEOID in "+role)
        return set(rows)
    geography=validate(geometry_geoids,"geometry")
    indicators=validate(indicator_geoids,"indicator")
    if not isinstance(expected_missing,(set,frozenset,tuple,list)):
        raise ValueError("Explicit expected_missing GEOID set required")
    expected=validate(expected_missing,"expected_missing") if expected_missing else set()
    unmatched_geo=geography-indicators
    unmatched_indicators=indicators-geography
    if unmatched_indicators:
        raise ValueError("Official indicator lacks Census geometry: "+", ".join(sorted(unmatched_indicators)))
    if unmatched_geo != expected:
        raise ValueError("County geometry-to-indicator missingness differs from reviewed crosswalk: "+
                         ", ".join(sorted(unmatched_geo^expected)))
    return {
        "geometryFeatures":len(geography),
        "indicatorGeoids":len(indicators),
        "joinedGeoids":len(geography & indicators),
        "unmatchedGeometryGeoids":sorted(unmatched_geo),
        "unexpectedIndicatorGeoids":[],
        "imputedValues":0,
        "joinKey":"GEOID",
        "mapping":"exact",
    }
