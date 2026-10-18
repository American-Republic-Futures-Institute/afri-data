# STAT-02A — Reproducible, unsigned statistical analytical artifacts

**Status:** Engineering validation only. **Public derived analysis: denied.** **Independent scientific review: not performed.** This increment is not a Census pilot, policy finding or statistical inference engine.

## Decision

Re-use the existing pinned \`arfi_stats\` STAT-00 calculation primitives and STAT-01 eligibility architecture. Introduce a **new**, typed, deterministic, source-independent analysis artifact that can be computed and replayed from caller-declared **synthetic input**. Do not implement another histogram, ECDF, quantile, renderer, source adapter, numerical estimator or publisher approval mechanism.

Two new schemas define:

- \`contracts/stat-analysis-request.schema.json\`: exact synthetic fixture identity, explicit chart type and existing StatKit method ID/version, X/Y/segment and filter columns, method parameters, analysis population/period/denominator/uncertainty context, limitations and **all authority flags false**.
- \`contracts/stat-analysis-artifact.schema.json\`: original request, request and input digests, full unchanged StatKit chart model, quality/coverage context, dependencies and exact method source-code hashes, output digest and whole-artifact digest, with **all authority flags false** and no official release identity.

The implementation \`arfi_stats/artifacts.py\` has **only** the following operations:

- \`produce(request, rows)\`: validate a typed **caller-declared synthetic** request and normalized JSON observation list, call the exact existing StatKit primitive, validate the chart output schema, and return a content-addressed unsigned artifact.
- \`replay(artifact, rows)\`: validate the existing artifact and its digests, check exact original inputs, reproduce with the pinned installed implementation, and compare the **entire recomputed artifact**. Returns \`deterministic-match\` only when all data, methods, numerical dependencies, labels and qualification content match.
- \`python -m arfi_stats.artifacts produce|replay\`: CLI wrapper with strict JSON parser, finite scalar input checks, duplicate-key rejection, bounded files and exclusive creation of new artifact files.

Every artifact binds:

1. \`sourceIdentity\`: caller-declared synthetic fixture ID, SHA-256 of canonical JSON input, row count, canonicalization version; \`releaseId=null\` and \`sourceCommit=null\`. An input digest detects changes but does not authenticate an external source.
2. \`request\`: immutable in-artifact request, method kind/version/ID and all parameters, exact fields, segment, explicit filters and required context. \`requestSha256\` covers all of it.
3. \`computation\`: Python runtime version, installed NumPy version, StatKit library version, SHA-256 of \`arfi_stats/core.py\`, SHA-256 of \`arfi_stats/artifacts.py\`, \`stat-method-registry.json\` and \`requirements.txt\`, plus original StatKit chart output SHA-256 and \`inputFingerprint\`.
4. \`chart\`: full source-neutral output using the existing \`ARFI-StatChartPreview/1.0.0\` contract, not new analysis code. It includes shared histogram bin boundaries and segment counts, ECDF frequencies/cumulative proportions, or boxplot quantiles/outliers, as appropriate. Other existing seven StatKit operations are dispatched via fixed method IDs.
5. \`quality\`: complete selected-source availability counts (including \`not_available\` and \`no_record\`), segment sample denominators in the original chart, unit of analysis, analyst-declared target and reference population, period, no-estimated-uncertainty status and explicit limitations.
6. \`authority\`: all public source/publishing/inference/causal/cross-source approvals **false**. \`independentReviewStatus=not-applicable-to-synthetic-fixture\`. A caller cannot set flags to true.

### Integrity and reproducibility are not source authentication

The artifact checksum prevents undetected accidental modification. Recomputing its result, in an installation with the exact same source-code and numerical dependency versions, detects altered calculations. Nevertheless, an actor controlling both source input and artifact can create a different internally consistent synthetic preview. **This is not cryptographically signed publisher provenance, independent human certification or proof of absence of bias.**

If the computing code or dependency lock changes, the prior artifact no longer satisfies this engine's exact-environment replay criterion. It must be reproduced under its original pinned environment or explicitly version-migrated with independent review. No silent version upgrade is accepted.

Uncertainty ranges are only shown when supplied by the synthetic fixture and labeled as synthetic; no statistical interval, confidence level, population weighting, causal result, Bayesian posterior or correlation coefficient is computed by this orchestration layer.

## Demonstrations (synthetic only)

The existing \`examples/statkit-synthetic.json\` contains six fabricated regional values, including one explicitly unavailable value. Three example requests demonstrate distinct standard primitives:

\`\`\`bash
python -m pip install -r requirements.txt
python -m arfi_stats.artifacts produce \
  --input examples/statkit-synthetic.json \
  --request examples/stat02a-histogram-request.json \
  --output /tmp/arfi-stat02a-histogram.json
python -m arfi_stats.artifacts replay \
  --input examples/statkit-synthetic.json \
  --artifact /tmp/arfi-stat02a-histogram.json

python -m arfi_stats.artifacts produce \
  --input examples/statkit-synthetic.json \
  --request examples/stat02a-ecdf-request.json
python -m arfi_stats.artifacts produce \
  --input examples/statkit-synthetic.json \
  --request examples/stat02a-boxplot-request.json

python -m unittest discover -s tests -v
\`\`\`

The CLI uses **exclusive file creation**, never replaces a previously generated artifact, refuses published \`publication/\` source assets as *synthetic CLI input*, and cannot write generated artifacts into any existing publication, governance, catalog or contract directory. It never downloads source evidence. No dashboard entrypoint imports this module.

## Required denial and replay tests

- Changing any input—even a field not used in the selected histogram—changes the canonical full-input fingerprint. Reordering the array also changes the raw-input identity, rather than silently reinterpreting its input order.
- Changing any request, output numerical value, segment denominator, method parameter, warning, Python/NumPy version, method source SHA, lockfile hash or artifact digest fails replay.
- Trying to declare a real government release, cross-source join, causal model, statistical inference, public publication, arbitrary script or empirical-Bayes method fails typed input admission.
- Null/unavailable source observations remain missing, with explicit counts. No input may substitute NaN/Infinity for missing values.
- Binning is bounded and performed by the already merged STAT-00 implementation. The orchestration layer does **not** calculate a separate histogram, mean or mode.
- Synthetic frequency, scatter, source-period time series and originally provided intervals exercise the remaining existing primitive dispatches, without new analytical models.
- The complete existing evidence integrity suite must continue to pass. **No \`publication/\` source, decision ledger or government observation file may change.**

## Subsequent increments

**STAT-02B** should define an **independent, approval-bearing release analytics contract**, not mutate this synthetic preview contract to \`publicationAuthorized=true\`.

A bounded **read-only Census pilot** would take the current population source profile, reproducibly normalize its 52 estimates for a single specified year, invoke STAT-01 eligibility, and compute internal-only histogram/ECDF/quantiles using the same STAT-00 primitives. It must preserve whether its statistic describes **jurisdictions** rather than residents and record source-pinned hashes. Importantly, any future public distribution chart and plain-language interpretation require a separately approved methodology and verified reviewer authority; the D-11B independent human review activation is still not completed.

Only after authentic source binding, method suitability, independent review and source-qualified context are verified should \`afri-website\` consume an approved derived artifact via the existing STAT-00B ECharts adapter. The present source-neutral synthetic preview output must never be mistaken for an approved publisher evidence release.
