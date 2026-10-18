# ARFI-StatKit — reusable statistical chart models (STAT-00)

Status: **engineering prototype — calculations are NOT approved for public publication**. This is a library and method-contract increment, not a new data release, a new government-source analysis, or an independent methodology certification.

## Why this exists

ARFI already uses **Apache ECharts 6.1.0** to render maps, bars, lines and scatter plots on the Observatory. The website also has \`createHistogram(values, count=8)\` in \`scripts/data-projection.mjs\`, currently limited to fixed bins without grouping, uncertainty semantics or missingness. Those are presentation capabilities, not a source-neutral numerical-analysis framework.

STAT-00 provides an explicit data-agnostic layer around the mature **NumPy 2.3.5** implementation of histogram binning, quantiles, uniqueness and distributions, plus deterministic source-preserving grouping. It makes no statistical significance, model-selection or causal claims.

**Do not build a custom renderer or implement new inference routines here.** ECharts will render a reviewed version of the resulting JSON chart contract in a subsequent website adapter PR. Any advanced inferential method (hierarchical/empirical-Bayes, bootstrap, survey variance, smoothing, regression or forecasts) needs its own reviewed method profile and may use established SciPy/statsmodels implementations later.

## Public API

\`\`\`python
from arfi_stats import histogram, ecdf, boxplot, frequency, scatter, time_series, intervals

sample = [
    {"value": 12.0, "region": "East", "availability": "available"},
    {"value": 17.0, "region": "West", "availability": "available"},
    {"value": None, "region": "East", "availability": "not_available"}
]
result = histogram(sample, x="value", segment="region", bins="fd", unit="percent")
assert result["kind"] == "ARFI-StatChartPreview/1.0.0"
assert result["authority"]["publicationAuthorized"] is False
\`\`\`

### Command-line

\`\`\`bash
python -m pip install -r requirements.txt
python -m arfi_stats --chart histogram --input examples/statkit-synthetic.json \
  --x value --segment region --bins fd --unit percent
python -m arfi_stats --chart ecdf --input examples/statkit-synthetic.json \
  --x value --segment region --unit percent
python -m unittest discover -s tests -v
\`\`\`

The example contains **synthetic** numbers, not actual Census/BLS/Treasury/CDC records. The CLI accepts a JSON list (or stdin), emits a pure data contract, and rejects nonfinite numbers, duplicate JSON keys, unbounded inputs, arbitrary expressions and unsupported methods. It does not read or write publication records.

## Model contract

The model's JSON structure is validated by \`contracts/stat-chart-preview.schema.json\`. The fixed method registry is \`contracts/stat-method-registry.json\`.

- \`chartType\`: one of \`histogram\`, \`ecdf\`, \`boxplot\`, \`frequency\`, \`scatter\`, \`time-series\`, \`interval\`.
- \`fields\`: caller-selected X, optional Y, optional segment key, availability column and unit.
- \`selection\`: original row count, explicitly filtered row count, equality-only filter selections and separate source missingness categories.
- \`algorithm\`: immutable method ID, pinned NumPy implementation version and fixed options.
- \`inputFingerprint\`: SHA-256 of the normalized selected values and parameters. This is **only a reproducibility fingerprint**, never proof of government-source admission or source cryptographic integrity.
- \`series\`: typed group records, original availability counts, observed numerical distribution points and optional descriptive quantiles.
- \`authority\`: \`sourceVerified=false\`, \`publicationAuthorized=false\`, \`crossSourceAuthorized=false\`, \`statisticalInferenceAuthorized=false\`, \`causalInferenceAuthorized=false\`. Callers cannot use an approval flag to override these fields.
- \`limitations\`: explicit interpretation bounds, including approximation of floating-point money.

All missingness classifications are retained: \`available\`, \`not_available\`, \`no_record\`, \`suppressed\`, \`not_applicable\`, \`unknown\`. Non-available numerical measures must be null, never substituted with zero. A nonexistent record cannot be inferred from the rows supplied: a caller must explicitly supply a \`no_record\` row after verified coverage assessment.

### Method semantics

| Callable | Accepted question | Key safeguards |
|---|---|---|
| \`histogram(rows,x,segment,bins,scale)\` | Numeric distribution across common X bins | NumPy \`histogram\`/bin edges; common bins between groups; Y is count or proportion of available observations **within each group**; no weighting |
| \`ecdf(rows,x,segment)\` | Cumulative distribution of observed values | NumPy unique/count/cumsum; identical values retained in counts |
| \`boxplot(rows,x,segment)\` | P10/P25/P50/P75/P90, IQR and Tukey outlier candidates | NumPy linear quantiles, actual observed extrema, outliers not discarded, no confidence claims |
| \`frequency(rows,x,segment)\` | Distribution of categories/ordinal responses | Categories not averaged or coerced into quantitative quality scores |
| \`scatter(rows,x,y,segment)\` | Paired observations in a single submitted table | No automatic regression, correlation significance or inference that sources can be joined |
| \`time_series(rows,x,y,segment)\` | Published observations by explicit year/date | Source gaps remain null, no temporal interpolation, no duplicate-period aggregation |
| \`intervals(rows,x,y,lower,upper)\` | Display previously published interval bounds | Requires original lower/upper and interval interpretation; **never computes new confidence intervals** |

The implementation is deliberately limited to descriptive **calculation primitives**, which may still constitute **derived analysis** requiring methodological approval before public use. It is not an inference library, and the absence of a published review decision is not evidence that a model is statistically appropriate.

## Safety and reproducibility requirements

1. Input values must be normalized by a reviewed source adapter before statistical processing; this package does not establish that a dataset is authentic or compatible with another.
2. Filters accept only explicit field/value sets, never executable expressions or calculated predicates. A filter does not silently redefine the reference cohort for future statistical shrinkage.
3. Group segmentation is limited to 64 categories; histograms to 64 bins; categorical frequencies to 500 categories; records to 100,000. These are engineering bounds, not sampling adequacy thresholds.
4. No person-level sampling weight or effective sample size is assumed. Population- and design-weighted estimates require an independently approved method and correct denominators.
5. Histogram auto binning is exploratory and not proof that the distribution has a particular shape. All segments use identical edges to permit legible presentations; small samples retain their low sample counts.
6. Boxplot Tukey outliers are **candidates for inspection**, not grounds for deletion or evidence of data errors.
7. Publisher-provided interval bounds stay attached to original values; their statistical meaning (confidence interval, prediction interval, credible interval, other) comes from the publisher and must not be invented.
8. Currency is displayed as floating-point distribution input, which cannot support exact financial accounting or financial reconciliation. Original decimal amounts remain authoritative and may require integer-minor-unit/Decimal methodology.
9. Output must be treated as preview-only until STAT-01 binds a source profile, an approved method decision, reference population and independent review when required.
10. A chart renderer must escape all labels, preserve source uncertainty and never silently replace the declared model algorithm with ECharts client-side transforms.

## Next related PRs

- **STAT-00B**: small \`afri-website\` ECharts chart-model adapter that consumes *only* a validated \`ARFI-StatChartPreview/1.0.0\` as a **synthetic preview** (no source publication); full visual types, accessible table fallback, no independent-model claims. No source dataset integration.
- **STAT-01**: source profile schema, eligibility gates and method authorization that prevents preview models from being promoted without actual review.
- **STAT-02**: distribution-first approved widgets using the existing ECharts engine with the newly approved library operations and contextual descriptions.

No existing source asset, \`publication/index.json\`, \`governance/decisions/\` historical record or website viewer is changed by STAT-00.
