# CDC PLACES 2025 modeled adult obesity by county — review contract

Official publisher: Centers for Disease Control and Prevention, PLACES 2025
GIS-friendly county dataset ID i46a-9kgh (3143 counties, 167 original columns).

Source: https://data.cdc.gov/d/i46a-9kgh
Method: https://www.cdc.gov/places/methodology/

The source adapter selects five original publisher fields: countyfips,
countyname, stateabbr, obesity_crudeprev, obesity_crude95ci. The original
JSON response is archived losslessly and its exact SHA-256 fingerprint is
published. The individual county ID is a 5-character FIPS string.
Dates are **not interchangeable**: the 2025 release models obesity from
2023 BRFSS inputs. The program uses multilevel regression and
poststratification; values are model-derived, not directly surveyed county
measurements. A 95% model interval is not causal evidence.

The official dataset indicates 3,143 counties for 50 states and DC.
If this count, field names, confidence interval notation or source bytes
change, ingestion fails for manual source review. No Puerto Rico county
figures are synthesized or silently mapped to missing cells.

On merge to main, .github/workflows/stage-cdc-places.yml downloads
allowlisted public HTTPS source records, checks all county observations and
intervals, then opens a new reviewed-data branch. A reviewer must inspect
the method, source license, archive, SHA-256, coverage, revisions and source
status before approving a release PR. The workflow does not automatically
write to main and does not alter the existing Census population publication.

**CDC explicitly warns that PLACES cannot establish intervention impacts.**
The Observatory must label the metric model-based and show its 2023
reference period and uncertainty.
