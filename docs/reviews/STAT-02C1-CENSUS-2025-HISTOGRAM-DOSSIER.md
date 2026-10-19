# STAT-02C.1 — Census Vintage 2025 Histogram Methodology Review Dossier

**State: DRAFT FOR FOUNDER REVIEW — NOT AUTHORIZED**

The *data engineering* can calculate the candidate and enforce an authenticated gate. It cannot truthfully assert the founder has evaluated all six review domains or declare their conflicts. This dossier prepares the evidence only; it does not contain an approved event or public analytical release.

## Source and measurement evidence

| Property | Canonical evidence |
|---|---|
| Published source | United States Census Bureau, Vintage 2025 State population estimates |
| Original national state table | `https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/state/totals/NST-EST2025-ALLDATA.csv` |
| Original boundaries | `https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_state_20m.zip` |
| Source year | July 1, 2025 estimate |
| Geography | Exactly 50 states, District of Columbia, Puerto Rico, each exactly one unweighted observation |
| Observations in source release | 312 rows (2020–2025 inclusive); the 2025 subset contains exactly 52 |
| Source release | `census-state-population-v2025` |
| Original source commitment | `f9e9d3cdcab573d41526d2fb1893860774636c13` |
| Original source decision | `census-state-population-v2025-owner-authorization` |
| Original manifest SHA-256 | `5ea73893a9d343f907979c67ac7fe4d7b85784483ff36df94d6311fc7499c4de` |
| Original observation SHA-256 | `e37483bbce3564f8737bc6db132cda90df1402e46237bbf42aaa69bf2b7b994d` |

The canonical `tools.stat_founder_packet inspect` command reproduces the source-bound histogram with ARFI StatKit and returns the **calculated** candidate SHA-256 and chart SHA-256. Copy neither number manually from a previous run: use the exact output from the packet-generation command, and preserve `python`, NumPy 2.3.5, StatKit source digests and bin coordinates for replay.

## Six methodological review domains — founder to evaluate

1. **Rights and licensing.** The published input identifies a federal Census Bureau resource and preserves original URLs and hashes. Federal government authored source data are generally public domain under 17 U.S.C. §105, subject to potential third-party rights. Verify the actual source notice and whether ARFI's derived visualization implies publisher endorsement (it must not).
2. **Methodology.** This is ARFI StatKit `numpy.histogram/1` with the Freedman–Diaconis (`bins=fd`) rule, scale=count, 52 positive integer Census estimates; no person-level weighting, extrapolation, data imputation, new confidence intervals or cross-source joins. Check how the binning rule affects apparent comparisons. Reproduce all bin edges and counts.
3. **Temporal interpretation.** July 1, 2025 estimated resident population, Vintage 2025, not the 2020 decennial enumeration, a daily measurement, or a future forecast. Cross-vintage comparisons are **not** authorized by this method approval.
4. **Geographic universe.** Every Census state-equivalent FIPS identifier is included exactly once: 50 states, DC and PR. A count of 52 alone does not prove geographic completeness; the replay checks exact membership. The distribution is weighted **per jurisdiction**, not per resident.
5. **Permitted public uses.** Descriptive educational histogram and equivalent accessible bin-count table only. It is not a scientific study of residents, a statistical significance test, an appraisal of state policies, a causal outcome, or an independently certified method.
6. **Cautions.** Census totals are estimates and have publisher-specific limitations. Display 52 as the denominator, show explicit missingness (expected zero for this source-year) and original limitations. The FD binning is a presentation choice, not an uncertainty model.

## Actual conflict-of-interest declaration — required, not yet provided

The reviewer is ARFI's founder and sole reviewer; therefore the organizational author–reviewer separation and independent scientific review controls are **not** present. The founder has an institutional interest in the Institute's publication. This is a known structural conflict and must be disclosed.

**HOLD:** The founder must personally disclose any other actual relevant financial, consulting, research, governance or personal interests, or expressly state that none exist beyond the organizational conflict, based on their own knowledge. Do not infer or fabricate a complete conflicts declaration from repository or prior discussions. No packet may be signed while this confirmation is outstanding.

## Exact production steps after founder supplies the conflicts statement

1. On the current canonical data commit run `python -m tools.stat_founder_packet inspect`. Confirm 2025 and the 52 jurisdictions, source digest and reproduced chart digest.
2. Create the packet directory: `mkdir -p governance/stat-founder/packets` (the shell opens redirection files before invoking Python).
3. Run `python -m tools.stat_founder_packet packet --conflict-disclosure '<YOUR TRUTHFUL COMPLETE STATEMENT>' > governance/stat-founder/packets/census-2025-histogram.json`.
4. Review the method and every source statement. Submit the **packet-only** PR containing this JSON.
5. Once the PR HEAD is final, compute its exact raw `packetSha256`, candidate hash and HEAD SHA, and personally post **only** the exact `ARFI-FOUNDER-METHOD-APPROVAL/1.0.0` attestation from `tools.stat_founder.attestation` on that PR.
6. Issue a subsequent authenticated governance event PR and then a **separate** publication PR. Founder review permits descriptive owner-reviewed publication, **never** independent certification.
7. Only after separate immutable publication and read-only website API acceptance may the Census Distribution Workbench be publicly linked.

No approval, statistical release or website evidence pin change is included in this preparation dossier.
