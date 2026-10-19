# STAT-02C — Founder-reviewed descriptive analytical publication

**Contract status:** Engineering only; no methodology approval or public founder-reviewed analytical releases yet. D-11B independent review continues separately.

## Distinct classifications

**Independent methodology certification** retains STAT-02B.2, independent reviewer eligibility, protected controls, and a real non-author review. No founder sign-off substitutes for these.

**Founder-reviewed descriptive publication**, classified `founder-reviewed-not-independent`, is confined to the Census 2025 unweighted histogram for 52 state-equivalent jurisdictions. It may be published for descriptive educational use after actual founder review, but is **not** independently certified or peer-reviewed, and cannot authorize causal claims, individual-level inference or cross-source comparisons.

## Authenticated founder methodology process

The currently authenticated GitHub account is `jmsbooth`. It is recorded only as the founder reviewer, **not** an external independent reviewer.

1. Generate the original candidate with `python -m arfi_stats.publication_gate candidate --kind histogram` and separately reproduce it from immutable Census source.
2. Draft `ARFI-FounderStatMethodPacket/1.0.0` in `governance/stat-founder/packets/`, binding the exact candidate, source decision, source manifest, observations, chart digest, method version, date and 52-geography universe. Six review scopes and seven detailed findings must be written. The conflict-of-interest statement must truthfully describe institutional and actual financial interests.
3. Open a **packet-only** PR. The founder personally reviews the contents and posts the exact multiline GitHub comment produced by `tools.stat_founder.attestation(packet_sha, candidate_sha, pr_head)`. This attests to the specific packet and PR HEAD, not a chat conversation or an owner merge. Editing the comment invalidates the attestation.
4. A later governance PR must append a new `ARFI-FounderStatMethodEvent/1.0.0` to `governance/stat-founder/index.json`, recording the original packet PR, head, SHA, comment ID and later UTC recordedAt. Do not modify older decisions.
5. Run `python -m tools.stat_founder verify`. The gate checks the actual GitHub actor, exact unchanged comment, reviewed packet bytes at the signed PR head, source owner-authorization and deterministic numerical reproduction. Missing or forbidden GitHub access denies authority.
6. A later, separate publication PR issues `ARFI-FounderReviewedStatAnalysis/1.0.0` with `python -m tools.stat_founder issue` and registers its immutable bytes in `publication/analytics/founder-index.json`. Original publisher observations, historical source owner decision, and independent analytics index remain untouched.
7. A revocation appends a `revoked` event; old approval/release bytes remain auditable but must never be served as current.

The original Census vintage and method require source-specific substantive review. Document Census publication rights; statistical treatment and histogram binning; July 1, 2025 period; exact states/DC/Puerto Rico; permitted descriptive-only use; uncertainty and missingness; and the founder's **actual** conflicts. The unweighted histogram describes jurisdictions, **not** the distribution of persons.

## CI and deployment boundary

CI validates the founder event and registry against actual GitHub records when entries exist, and verifies append-only method packets, decisions and releases. An empty founder index passes while reporting **zero authorized public analytics**. No runtime website route should treat this class as independent review. A website consumer must display an explicit `Founder reviewed · Not independently certified` label.

### Commands

```bash
python -m unittest tests.test_stat_founder -v
python -m tools.stat_founder verify
python -m tools.stat_founder registry
# Only after a real reviewed packet + event has been verified:
python -m tools.stat_founder issue > /tmp/owner-reviewed-census-histogram.json
```

**Current disposition:** engineering implementation only, no independently certified result, no authenticated founder method-review event, and no approved founder-reviewed analytical publication.
