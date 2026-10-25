# Controlled repeated-ingestion test

This document records the regression test added for the collection-run
lineage correction requested after the Phase I schema review. The test is
implemented in [`tests/test_repeated_ingestion.py`](../tests/test_repeated_ingestion.py)
and uses temporary synthetic records only; no Google Play review text is
committed to the repository.

## How to run

From the repository root, with the project dependencies installed:

```bash
python -m unittest tests/test_repeated_ingestion.py -v
```

The test runs `clean_reviews.py` and `load_database.py` against a temporary
SQLite database for each controlled collection attempt.

## Test sequence and observed results

| Step | Collection run | Input | Expected and verified outcome |
| --- | --- | --- | --- |
| 1 | `run-001` | Initial collection containing reviews A and B | 2 reviews; A and B have `first_collected_run_id = run-001`. |
| 2 | `run-002` | Repeat collection containing A twice and B | 2 retained reviews; one within-run duplicate removed; `run-002` is stored even though it produces no new unique review. A and B retain `run-001`. |
| 3 | `run-003` | Overlap B plus new review C; status `partial` | 3 retained reviews; B retains `run-001`, C receives `run-003`, and the partial run is retained. |
| 4 | `run-004` | Zero returned reviews | 3 retained reviews and 4 stored `collection_runs`; `run-004` remains present despite no JSONL rows. |

The test was executed successfully on 2026-10-25. Its final assertions verify
the three review IDs and their first-observed run IDs (`A → run-001`,
`B → run-001`, `C → run-003`) and all four run statuses.

## Implementation behavior

`collect_reviews.py` now writes one `*_run_manifest.json` per collection
attempt. The manifest records timing, source, requested count, status, and
per-app outcome counts independently of the review JSONL files.

`clean_reviews.py` emits `collection_runs_clean.csv` from those manifests.
`load_database.py` loads that file before reviews. A review conflict may update
the latest review fields but never updates `first_collected_run_id`, preserving
the first observed lineage. Older raw data without a manifest remains readable
through an explicitly labelled legacy-compatibility path.
