## DATA-04B — large source history without truncation

Treasury MTS Table 5 full outlays history exceeded 7 MB for at least one single year. A 450,000-row and 600-page acquisition budget alone does not make those source records safe to serve through the website.

This increment retains full publisher rows and historic revisions, but partitions a source **by original year when the whole year fits a 3 MB serving budget, otherwise by original reported month**. Each period has its own SHA-256, byte and row count, first and last record dates. Current existing annual files are unchanged. Oversized months still fail explicitly; we never truncate publisher history to satisfy the serving budget.

Each monthly partition includes its canonical `YYYY-MM` identity and remains bound to its source year. The website supports exact `period=YYYY-MM` selection separately from existing `year=YYYY`; old deep links remain valid. The website consumer compatibility PR must merge **before** exposing monthly partitions in the rolling data branch.

On merge, the Monday weekly source refresh is also triggered by the source-library code change. It reconciles `data/source-library` with main and retries 11 feeds, preserving earlier published records if any single feed fails. Inspect `publication/source-library/health.json` for the exact outcome. The source-fetch/check run is the acceptance gate for the newly populated table.
