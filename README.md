# ARFI Public Data Repository

**American Republic Futures Institute · Public Data Observatory**

This is the research-data publication and provenance repository for the proposed ARFI Data Observatory. It is not the authoritative source for the Institute's Plan text or constitutional models; those remain in their own repositories. The purpose is to make public-sector evidence discoverable, reproducible and visualization-ready without introducing a new managed database or paid ETL service.

**Current status (acquisition snapshot, 2026-10-22):** 238 source-native government feeds mirrored across nine publisher families (1,487 historical partitions; 584,802 records); five separately curated releases appear in the publication index. The source library lives on the [rolling acquisition branch](https://github.com/American-Republic-Futures-Institute/afri-data/tree/data/source-library), while reviewed publication metadata lives on `main`. The source-program inventory below tracks both acquired subsets and pending programs. This is not a claim of complete federal coverage, independent scientific review, or custody of every full upstream original. **Never treat test fixtures as real government data.**

## Repository structure

    catalog/
      publishers.json                      67 registered government and research organizations
      source-programs.json                 130 candidate public-data programs (discovery, not publication)
      datasets/                            Reviewed dataset definitions and authoritative source URLs
      indicators/                          Indicator metadata and chart semantics
      publication-contract.json            Shared website entry-point expectations
    contracts/                             JSON Schema contracts (publishers/datasets/indicators/releases)
    pipelines/
      census_state_population.py           Census official-source ingestion and verified projection
    tools/
      validate.py                          Source/catalog/asset/hash/geography contract enforcement
    tests/
      test_pipeline.py                     Offline conversion and tampering/security tests
    publication/
      index.json                           Created after verified and approved refresh
      releases/                            Versioned static evidence packages, no synthetic values
    examples/
      choropleth.html                      ECharts + GeoJSON map, trend chart, accessible table
    docs/
      EVIDENCE-GOVERNANCE.md               Original / normalized / derived / interpretation separation
      WEBSITE-INTEGRATION.md               Stable joins, immutable publishing and /data/ API contract
      OPERATIONS.md                        Runbook and approval gates
    .github/workflows/
      validate.yml                         Test contracts and integrity
      refresh-census.yml                   Fetch public Census originals and stage reviewer PR

## Principles

1. Original government source remains authoritative. Keep source URL, vintage, original bytes where practical, SHA-256, timestamp and methodology.
2. Distinguish **L0 original evidence**, **L1 typed source-preserving projections**, **L2 explicitly derived statistics**, and **L3 separately attributable interpretation**.
3. Never conflate counts with rates, estimates with enumerations, missing with zero, or incomparable vintages/geographies. No fabricated statistical values.
4. Only approved releases are published to the website. The source discovery registry does not imply that an unreviewed research publisher or dataset is unbiased, approved or freely redistributable.
5. Static-first deployment: GitHub Actions, small versioned JSON/CSV/GeoJSON and an existing website. Budget target is **zero incremental paid infrastructure**, subject to account and usage limits.

## Census bootstrap source example

- Official Census 2025 resident population estimates, source CSV:
  https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/state/totals/NST-EST2025-ALLDATA.csv
- Official Census 2025 state cartographic boundaries (1:20 million):
  https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_state_20m.zip
- Population methodology and release:
  https://www.census.gov/data/tables/time-series/demo/popest/2020s-state-total.html
- Census cartographic methodology:
  https://www.census.gov/geographies/mapping-files/2025/geo/carto-boundary-file.html

The 2025 Census ALLDATA publication includes annual population estimates for 2020 through 2025 and is a **published statistical estimate**. The two-character state FIPS joins to the cartographic feature GEOID. The first map illustrates source-backed published population totals; it is not a public-service outcome index.

<!-- SOURCE-INVENTORY:BEGIN -->
## Data source targets and acquisition status

**Generated from the [reviewed program registry](catalog/source-programs.json), [source evidence snapshot](catalog/source-inventory-evidence.json), and [published release index](publication/index.json).** Never edit the statuses by hand; run `python -m tools.source_inventory --write` after updating the reviewed registry or source receipts.

- **131 targeted source programs**; **238 mirrored source feeds** from the rolling source ledger (across 10 mapped programs); **5 programs** have at least one curated publication.
- Source mirror evidence: `data/source-library@e688a8190b98` (last checked `2026-10-22T20:29:38Z`). These are bounded source-native mirrors, not claims that every upstream full original archive was saved byte-for-byte.
- **Imported** = an acquired source feed in the independently verified rolling source snapshot, or a curated source-backed release when marked *release only*. **Analyzed** = a source-backed curated indicator release exists; this does *not* claim independent methodological review. **Published** = listed in the ARFI publication index. **Pending** = no approved source import, or *expansion* when only a subset of a broad government program is held.
- Program registration is a *discovery candidate*, not blanket ingestion approval. Source acquisition, statistical analysis and website publication remain separate.

<details><summary>Agriculture — 8 programs; 1 with imported feeds</summary>

| Target source program | Imported | Analyzed | Published | Pending |
|---|---|---|---|---|
| [Map the Meal Gap](https://www.feedingamerica.org/research/map-the-meal-gap) (`feeding-america-gap`) | No | No | No | Yes |
| [Farm Income and Wealth Statistics](https://www.ers.usda.gov/data-products/farm-income-and-wealth-statistics) (`ers-farm-finance`) | 2 feeds | No | No | Expansion |
| [Food Access Research Atlas](https://www.ers.usda.gov/data-products/food-access-research-atlas/) (`ers-food-access`) | No | No | No | Yes |
| [Food Environment Atlas](https://www.ers.usda.gov/data-products/food-environment-atlas) (`ers-food-env`) | No | No | No | Yes |
| [Rural Economy and Population](https://www.ers.usda.gov/topics/rural-economy-population) (`ers-rural`) | No | No | No | Yes |
| [USDA Food Nutrition Program Data](https://www.fns.usda.gov/pd/overview) (`usda-assistance`) | No | No | No | Yes |
| [Census of Agriculture](https://www.nass.usda.gov/Publications/AgCensus/) (`nass-agcensus`) | No | No | No | Yes |
| [NASS Quick Stats](https://quickstats.nass.usda.gov/) (`nass-quickstats`) | No | No | No | Yes |

</details>

<details><summary>Connectivity — 2 programs; 0 with imported feeds</summary>

| Target source program | Imported | Analyzed | Published | Pending |
|---|---|---|---|---|
| [National Broadband Map](https://broadbandmap.fcc.gov/) (`fcc-broadband`) | No | No | No | Yes |
| [NTIA Broadband Program Data](https://www.ntia.gov/data) (`ntia-broadband`) | No | No | No | Yes |

</details>

<details><summary>Demography — 3 programs; 1 with imported feeds</summary>

| Target source program | Imported | Analyzed | Published | Pending |
|---|---|---|---|---|
| [American Community Survey](https://www.census.gov/programs-surveys/acs) (`census-acs`) | 48 feeds | Curated | 1 release | Expansion |
| [Decennial Census](https://www.census.gov/programs-surveys/decennial-census.html) (`census-decennial`) | No | No | No | Yes |
| [Population Estimates Program](https://www.census.gov/programs-surveys/popest.html) (`census-popest`) | Release only | Curated | 1 release | Expansion |

</details>

<details><summary>Discovery — 1 programs; 0 with imported feeds</summary>

| Target source program | Imported | Analyzed | Published | Pending |
|---|---|---|---|---|
| [Data.gov Federal and Subnational Discovery Catalog](https://catalog.data.gov/) (`datagov-catalog`) | No | No | No | Yes |

</details>

<details><summary>Economy — 12 programs; 2 with imported feeds</summary>

| Target source program | Imported | Analyzed | Published | Pending |
|---|---|---|---|---|
| [GDP by County and Metropolitan Area](https://www.bea.gov/data/gdp/gdp-county-and-metropolitan-area) (`bea-regional-gdp`) | 2 feeds | No | No | Expansion |
| [Gross Domestic Product](https://www.bea.gov/data/gdp/gross-domestic-product) (`bea-gdp`) | No | No | No | Yes |
| [International Trade and Investment](https://www.bea.gov/data/intl-trade-investment) (`bea-trade`) | No | No | No | Yes |
| [Regional Personal Income](https://www.bea.gov/data/income-saving/personal-income-county-metro-and-other-areas) (`bea-income`) | 2 feeds | No | No | Expansion |
| [Consumer Price Index](https://www.bls.gov/cpi/) (`bls-cpi`) | No | No | No | Yes |
| [Producer Price Index](https://www.bls.gov/ppi/) (`bls-ppi`) | No | No | No | Yes |
| [Financial Accounts of the United States](https://www.federalreserve.gov/releases/z1/) (`fed-z1`) | No | No | No | Yes |
| [Industrial Production and Capacity Utilization](https://www.federalreserve.gov/releases/g17/) (`fed-g17`) | No | No | No | Yes |
| [Survey of Consumer Finances](https://www.federalreserve.gov/econres/scfindex.htm) (`fed-scf`) | No | No | No | Yes |
| [County Business Patterns](https://www.census.gov/programs-surveys/cbp.html) (`census-cbp`) | No | No | No | Yes |
| [Nonemployer Statistics](https://www.census.gov/programs-surveys/nonemployer-statistics.html) (`census-nonemployer`) | No | No | No | Yes |
| [Survey of Income and Program Participation](https://www.census.gov/programs-surveys/sipp.html) (`census-sipp`) | No | No | No | Yes |

</details>

<details><summary>Education — 7 programs; 0 with imported feeds</summary>

| Target source program | Imported | Analyzed | Published | Pending |
|---|---|---|---|---|
| [Civil Rights Data Collection](https://ocrdata.ed.gov/) (`education-civil-rights`) | No | No | No | Yes |
| [College Scorecard](https://collegescorecard.ed.gov/data/) (`education-college-scorecard`) | No | No | No | Yes |
| [Common Core of Data Schools and Districts](https://nces.ed.gov/ccd/) (`nces-ccd`) | No | No | No | Yes |
| [Education Demographic and Geographic Estimates](https://nces.ed.gov/Programs/Edge/) (`nces-edge`) | No | No | No | Yes |
| [Integrated Postsecondary Education Data System](https://nces.ed.gov/ipeds/) (`nces-ipeds`) | No | No | No | Yes |
| [National Assessment of Educational Progress](https://www.nationsreportcard.gov/) (`nces-naep`) | No | No | No | Yes |
| [Urban Education Data Portal](https://educationdata.urban.org/) (`urban-education`) | No | No | No | Yes |

</details>

<details><summary>Energy — 3 programs; 1 with imported feeds</summary>

| Target source program | Imported | Analyzed | Published | Pending |
|---|---|---|---|---|
| [EIA Electricity and Grid Data](https://www.eia.gov/electricity/data.php) (`eia-electricity`) | No | No | No | Yes |
| [Energy Information Administration API](https://www.eia.gov/opendata/) (`eia-open-data`) | No | No | No | Yes |
| [State Energy Profiles](https://www.eia.gov/state/) (`eia-state-energy`) | 5 feeds | No | No | Expansion |

</details>

<details><summary>Environment — 13 programs; 2 with imported feeds</summary>

| Target source program | Imported | Analyzed | Published | Pending |
|---|---|---|---|---|
| [Air Trends](https://www.epa.gov/air-trends) (`epa-air`) | 74 feeds | No | No | Expansion |
| [EPA Water Data](https://www.epa.gov/waterdata) (`epa-water`) | No | No | No | Yes |
| [Environmental Compliance History Online](https://echo.epa.gov/) (`epa-echo`) | No | No | No | Yes |
| [Toxics Release Inventory](https://www.epa.gov/toxics-release-inventory-tri-program) (`epa-tri`) | No | No | No | Yes |
| [NASA Earthdata Catalog](https://www.earthdata.nasa.gov/data/catalog) (`nasa-earthdata`) | No | No | No | Yes |
| [NASA Fire Information Resource Management](https://firms.modaps.eosdis.nasa.gov/) (`nasa-firms`) | No | No | No | Yes |
| [Climate Data Online](https://www.ncei.noaa.gov/cdo-web/) (`noaa-climate-data`) | No | No | No | Yes |
| [NOAA Digital Coast](https://coast.noaa.gov/digitalcoast/) (`noaa-coastal`) | No | No | No | Yes |
| [NOAA National Centers for Environmental Information](https://www.ncei.noaa.gov/) (`noaa-ncei`) | No | No | No | Yes |
| [NOAA Tides and Currents](https://tidesandcurrents.noaa.gov/) (`noaa-tides`) | No | No | No | Yes |
| [Earthquake Hazards](https://www.usgs.gov/programs/earthquake-hazards) (`usgs-earthquakes`) | 27 feeds | No | No | Expansion |
| [National Minerals Information Center](https://www.usgs.gov/centers/national-minerals-information-center) (`usgs-minerals`) | No | No | No | Yes |
| [USGS Water Data](https://waterdata.usgs.gov/) (`usgs-water`) | No | No | No | Yes |

</details>

<details><summary>Finance — 9 programs; 1 with imported feeds</summary>

| Target source program | Imported | Analyzed | Published | Pending |
|---|---|---|---|---|
| [Congressional Budget and Economic Data](https://www.cbo.gov/data) (`cbo-budget`) | No | No | No | Yes |
| [Consumer Complaint Database](https://www.consumerfinance.gov/data-research/) (`cfpb-complaints`) | No | No | No | Yes |
| [FDIC Financial Institution Data](https://www.fdic.gov/analysis) (`fdic-reports`) | No | No | No | Yes |
| [IRS Statistics of Income](https://www.irs.gov/statistics) (`irs-soi`) | No | No | No | Yes |
| [OMB Federal Budget Publications](https://www.whitehouse.gov/omb/) (`omb-budget`) | No | No | No | Yes |
| [Tax Foundation Federal State Local Tax Data](https://taxfoundation.org/data/) (`tax-foundation-rates`) | No | No | No | Yes |
| [FiscalData datasets](https://fiscaldata.treasury.gov/) (`treasury-fiscaldata`) | 15 feeds | No | No | Expansion |
| [TreasuryDirect government securities](https://www.treasurydirect.gov/) (`treasury-td`) | No | No | No | Yes |
| [Federal Award Geographic Spending](https://www.usaspending.gov/) (`usaspending-awards`) | Release only | Curated | 1 release | Expansion |

</details>

<details><summary>Geography — 3 programs; 0 with imported feeds</summary>

| Target source program | Imported | Analyzed | Published | Pending |
|---|---|---|---|---|
| [OpenStreetMap Geographic Reference](https://www.openstreetmap.org/) (`osm-mapping`) | No | No | No | Yes |
| [Cartographic Boundary Files](https://www.census.gov/geographies/mapping-files/2025/geo/carto-boundary-file.html) (`census-cartographic`) | No | No | No | Yes |
| [TIGER Line geographic products](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html) (`census-geography`) | No | No | No | Yes |

</details>

<details><summary>Governance — 8 programs; 0 with imported feeds</summary>

| Target source program | Imported | Analyzed | Published | Pending |
|---|---|---|---|---|
| [Congress.gov Bills and Legislative Activity](https://www.congress.gov/) (`congress-bills`) | No | No | No | Yes |
| [DHS Immigration Statistics](https://www.dhs.gov/immigration-statistics) (`dhs-immigration`) | No | No | No | Yes |
| [Election Administration and Voting Survey](https://www.eac.gov/research-and-data) (`eac-election-survey`) | No | No | No | Yes |
| [Federal Election Campaign Finance Data](https://www.fec.gov/data/) (`fec-finance`) | No | No | No | Yes |
| [GAO Oversight and Recommendations](https://www.gao.gov/) (`gao-reports`) | No | No | No | Yes |
| [GovInfo Official Publications](https://www.govinfo.gov/) (`gpo-govinfo`) | No | No | No | Yes |
| [State and Local Government Finances](https://www.census.gov/programs-surveys/gov-finances.html) (`census-state-finance`) | No | No | No | Yes |
| [V-Dem Democracy Data](https://www.v-dem.net/data/) (`vdem-democracy`) | No | No | No | Yes |

</details>

<details><summary>Health — 18 programs; 1 with imported feeds</summary>

| Target source program | Imported | Analyzed | Published | Pending |
|---|---|---|---|---|
| [AHRQ Health Quality Research Data](https://www.ahrq.gov/data/index.html) (`ahrq-research`) | No | No | No | Yes |
| [Healthcare Cost and Utilization Project](https://hcup-us.ahrq.gov/) (`ahrq-hcup`) | No | No | No | Yes |
| [Behavioral Risk Factor Surveillance](https://www.cdc.gov/brfss/) (`cdc-brfss`) | No | No | No | Yes |
| [CDC PLACES Small Area Health Estimates](https://www.cdc.gov/places/) (`cdc-places`) | 42 feeds | Curated | 1 release | Expansion |
| [CDC WONDER](https://wonder.cdc.gov/) (`cdc-wonder`) | No | No | No | Yes |
| [Chronic Disease Indicators](https://www.cdc.gov/cdi/) (`cdc-chronic`) | No | No | No | Yes |
| [National Health Interview Survey](https://www.cdc.gov/nchs/nhis/) (`cdc-nhis`) | No | No | No | Yes |
| [National Health and Nutrition Examination Survey](https://www.cdc.gov/nchs/nhanes/) (`cdc-nhanes`) | No | No | No | Yes |
| [National Vital Statistics System](https://www.cdc.gov/nchs/nvss/) (`cdc-vitals`) | No | No | No | Yes |
| [CMS Data](https://data.cms.gov/) (`cms-program-data`) | No | No | No | Yes |
| [CMS Provider Data](https://data.cms.gov/provider-data/) (`cms-providers`) | No | No | No | Yes |
| [Medicaid and CHIP Data](https://data.medicaid.gov/) (`cms-medicaid`) | No | No | No | Yes |
| [Open Payments](https://openpaymentsdata.cms.gov/) (`cms-open-payments`) | No | No | No | Yes |
| [County Health Rankings](https://www.countyhealthrankings.org/) (`chr-counties`) | No | No | No | Yes |
| [HRSA Public Health Geospatial Data](https://data.hrsa.gov/) (`hrsa-map`) | No | No | No | Yes |
| [KFF Health Research Data](https://www.kff.org/) (`kff-health-policy`) | No | No | No | Yes |
| [ClinicalTrials.gov Research Data](https://clinicaltrials.gov/data-api/api) (`nih-clinical-trials`) | No | No | No | Yes |
| [SAMHSA Behavioral Health Data](https://www.samhsa.gov/data/) (`samhsa-data`) | No | No | No | Yes |

</details>

<details><summary>Housing — 6 programs; 0 with imported feeds</summary>

| Target source program | Imported | Analyzed | Published | Pending |
|---|---|---|---|---|
| [Home Mortgage Disclosure Act](https://www.consumerfinance.gov/data-research/hmda/) (`cfpb-hmda`) | No | No | No | Yes |
| [House Price Index](https://www.fhfa.gov/data/hpi) (`fhfa-house-price`) | No | No | No | Yes |
| [Annual Homelessness Assessment](https://www.huduser.gov/portal/datasets/ahar.html) (`hud-homelessness`) | No | No | No | Yes |
| [Comprehensive Housing Affordability Strategy](https://www.huduser.gov/portal/datasets/cp.html) (`hud-housing-affordability`) | No | No | No | Yes |
| [HUD Fair Market Rents](https://www.huduser.gov/portal/datasets/fmr.html) (`hud-fair-market-rents`) | No | No | No | Yes |
| [American Housing Survey](https://www.census.gov/programs-surveys/ahs.html) (`census-housing-survey`) | No | No | No | Yes |

</details>

<details><summary>Infrastructure — 6 programs; 0 with imported feeds</summary>

| Target source program | Imported | Analyzed | Published | Pending |
|---|---|---|---|---|
| [Bureau of Transportation Statistics](https://www.bts.gov/) (`bts-stats`) | No | No | No | Yes |
| [National Transportation Atlas Database](https://www.bts.gov/geospatial) (`bts-ntad`) | No | No | No | Yes |
| [DOT Open Data](https://data.transportation.gov/) (`dot-open`) | No | No | No | Yes |
| [Highway Performance Monitoring System](https://www.fhwa.dot.gov/policyinformation/hpms.cfm) (`fhwa-hpms`) | No | No | No | Yes |
| [National Bridge Inventory](https://www.fhwa.dot.gov/bridge/nbi.cfm) (`fhwa-bridge`) | No | No | No | Yes |
| [Fatality Analysis Reporting System](https://www.nhtsa.gov/research-data/fatality-analysis-reporting-system-fars) (`nhtsa-crash`) | No | No | No | Yes |

</details>

<details><summary>International — 3 programs; 0 with imported feeds</summary>

| Target source program | Imported | Analyzed | Published | Pending |
|---|---|---|---|---|
| [OECD Data](https://data.oecd.org/) (`oecd-indicators`) | No | No | No | Yes |
| [Our World in Data Series Explorer](https://ourworldindata.org/) (`owid-explorer`) | No | No | No | Yes |
| [World Bank Open Data](https://data.worldbank.org/) (`worldbank-indicators`) | No | No | No | Yes |

</details>

<details><summary>Justice — 5 programs; 0 with imported feeds</summary>

| Target source program | Imported | Analyzed | Published | Pending |
|---|---|---|---|---|
| [Corrections Data](https://bjs.ojp.gov/topics/corrections) (`bjs-corrections`) | No | No | No | Yes |
| [NIBRS National Estimates](https://bjs.ojp.gov/national-incident-based-reporting-system-nibrs-national-estimates-api) (`bjs-nibrs`) | No | No | No | Yes |
| [National Crime Victimization Survey](https://bjs.ojp.gov/data-collection/ncvs) (`bjs-ncvs`) | No | No | No | Yes |
| [Civil Rights Division](https://www.justice.gov/crt) (`doj-civil-rights`) | No | No | No | Yes |
| [Crime Data Explorer](https://cde.ucr.cjis.gov/) (`fbi-crime`) | No | No | No | Yes |

</details>

<details><summary>Labor — 9 programs; 1 with imported feeds</summary>

| Target source program | Imported | Analyzed | Published | Pending |
|---|---|---|---|---|
| [Employment Cost Index](https://www.bls.gov/eci/) (`bls-eci`) | No | No | No | Yes |
| [Employment Projections](https://www.bls.gov/emp/) (`bls-projections`) | No | No | No | Yes |
| [Job Openings and Labor Turnover](https://www.bls.gov/jlt/) (`bls-jolts`) | No | No | No | Yes |
| [Local Area Unemployment Statistics](https://www.bls.gov/lau/) (`bls-lau`) | Release only | Curated | 1 release | Expansion |
| [Occupational Employment and Wage Statistics](https://www.bls.gov/oes/) (`bls-oews`) | No | No | No | Yes |
| [Quarterly Census of Employment and Wages](https://www.bls.gov/cew/) (`bls-qcew`) | 21 feeds | No | No | Expansion |
| [Economic Policy Institute Data](https://www.epi.org/data/) (`epi-wages`) | No | No | No | Yes |
| [Current Population Survey](https://www.census.gov/programs-surveys/cps.html) (`census-cps`) | No | No | No | Yes |
| [Longitudinal Employer Household Dynamics](https://lehd.ces.census.gov/data/) (`census-lehd`) | No | No | No | Yes |

</details>

<details><summary>Research — 9 programs; 0 with imported feeds</summary>

| Target source program | Imported | Analyzed | Published | Pending |
|---|---|---|---|---|
| [Bipartisan Policy Center Research](https://bipartisanpolicy.org/) (`bpc-research`) | No | No | No | Yes |
| [Brookings Research Outputs](https://www.brookings.edu/) (`brookings-research`) | No | No | No | Yes |
| [ICPSR Research Data Archive](https://www.icpsr.umich.edu/) (`icpsr-archive`) | No | No | No | Yes |
| [IPUMS Harmonized Census and Survey Microdata](https://www.ipums.org/) (`ipums-integrated`) | No | No | No | Yes |
| [General Social Survey](https://gss.norc.org/) (`norc-gss`) | No | No | No | Yes |
| [Opportunity Insights Research Data](https://opportunityinsights.org/data/) (`opportunity-mobility`) | No | No | No | Yes |
| [Pew Research Data](https://www.pewresearch.org/datasets/) (`pew-survey`) | No | No | No | Yes |
| [RAND Public Research Outputs](https://www.rand.org/) (`rand-public-research`) | No | No | No | Yes |
| [Urban Institute Data Catalog](https://datacatalog.urban.org/) (`urban-data`) | No | No | No | Yes |

</details>

<details><summary>Resilience — 5 programs; 0 with imported feeds</summary>

| Target source program | Imported | Analyzed | Published | Pending |
|---|---|---|---|---|
| [Flood Map Service Center](https://msc.fema.gov/portal/home) (`fema-flood`) | No | No | No | Yes |
| [National Risk Index](https://hazards.fema.gov/nri/) (`fema-risk`) | No | No | No | Yes |
| [OpenFEMA](https://www.fema.gov/about/openfema) (`fema-open`) | No | No | No | Yes |
| [National Center for Veterans Analysis and Statistics](https://www.va.gov/vetdata/) (`va-veteran-pop`) | No | No | No | Yes |
| [VA Open Data](https://www.data.va.gov/) (`va-open-data`) | No | No | No | Yes |

</details>

<details><summary>Science — 1 programs; 0 with imported feeds</summary>

| Target source program | Imported | Analyzed | Published | Pending |
|---|---|---|---|---|
| [National Center for Science and Engineering Statistics](https://ncses.nsf.gov/surveys) (`nsf-science-statistics`) | No | No | No | Yes |

</details>

To extend coverage: add a *reviewed candidate* to `catalog/source-programs.json`; add exact import identity mapping to `tools/source_inventory.py` only when a verified original/source mirror exists; admit originals independently; then regenerate. The scheduled inventory-sync workflow proposes README updates when the rolling source ledger changes.

<!-- SOURCE-INVENTORY:END -->

## Developer quickstart

Install Python 3.12+, then:

    python -m pip install -r requirements.txt
    python tools/validate.py --catalog-only
    python -m unittest discover -s tests -v
    python pipelines/census_state_population.py
    python tools/validate.py
    python -m http.server 8000

Open http://localhost:8000/examples/choropleth.html to see real source-backed choropleth and historical trends **after** publication exists locally. The browser demo fetches published files relative to this repository and cryptographically verifies their SHA-256s. Its hosted ECharts CDN is demo-only; the ARFI production website should bundle ECharts locally.

The initial pipeline downloads official static files directly over HTTPS. No Census API key, cloud database or managed mapping API is needed.

## Releasing to the website

The monthly (and manually triggered) Census refresh workflow generates data and opens a **review PR**, not a direct production write. An authorized reviewer checks original source revision, 312 observations, 52 boundary joins, completeness, interpretations, potential license issues, checksums and CI, then merges.

The ARFI website should consume the immutable approved commit, or copy assets at build time after verifying release manifests. Do **not** serve mutable source registries as if they were validated data or silently connect to arbitrary user-provided APIs. The site-facing contract and example map are documented under docs/WEBSITE-INTEGRATION.md.

Website repository: https://github.com/American-Republic-Futures-Institute/afri-website

## Status / limitations

- Nine source families are currently mirrored on the rolling data branch, but many cataloged federal data programs are **discovery entries only**. The current 238-feed snapshot is a bounded set of source-native subsets, not a census of all federal data.
- No private/restricted microdata and no derived or fabricated rates.
- No automated cross-publisher trust scoring or claim that 501(c)(3) sources are intrinsically impartial.
- Reviewed data publication and visual website integration are distinct activities.
- Source materials may have their own reuse requirements; see DATA-RIGHTS.md.

### Evidence release governance (D-10)

The current published evidence has an independent [append-only review ledger](governance/index.json); its five historic entries document **owner authorization only** and **pending independent methodological review**. [D-10 governance and release-diff runbook](docs/D10-REVIEW-LEDGER.md) describes exact source binding, canonical revision reports, contributor/reviewer trust boundaries, and required operator gates. Independent review enrollment has not yet been authorized, so an empty designated-reviewer roster fails closed.
