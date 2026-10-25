# Data Ingestion System - Phase I

Reusable prototype for collecting Google Play reviews, cleaning them, loading a normalized SQLite database, and conducting exploratory analysis. It supports the Phase I brief's three core capabilities: automated acquisition, repeatable structuring/validation, and SQL-queryable storage.

## Scope and source decision

Google Play reviews are the selected research/prototype source. The collector uses the **unofficial third-party** [`google-play-scraper`](https://pypi.org/project/google-play-scraper/) package, not an official Google API. Availability, response fields, and permitted use can change, so keep this limitation visible in any report and respect applicable Google Play terms and rate limits.

The supplied `config/apps.csv` starts with 12 apps across seven categories and a target of up to 500 reviews per app (about 6,000 records before availability, duplicates, and cleaning). This is a project sampling decision, not a requirement from John.

## Project layout

```text
config/apps.csv              App-level collection configuration
src/collect_reviews.py       Configurable acquisition into append-only JSONL
src/clean_reviews.py         Validation, normalization, deduplication, and run manifests
src/schema.sql               SQLite relational schema: apps, runs, reviews
docs/DATABASE_SCHEMA.md       Schema guide, field mappings, ERD, design choices
docs/REPEATED_INGESTION_TEST.md  Controlled lineage-test results
src/load_database.py         Repeatable cleaned-data loader (upsert-safe)
src/verify_database.py       Basic quality and integrity queries
tests/test_repeated_ingestion.py  Controlled repeated-ingestion lineage test
analysis/google_play_eda.ipynb  EDA: characteristics, coverage, quality, comparisons
findings/EDA_FINDINGS_TEMPLATE.md  Findings report structure
```

Generated review data and the database are ignored by Git because review text and potential user metadata should not be committed without an approved data-governance decision.

## Setup

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run the pipeline

Review and edit `config/apps.csv` first. Then run the following from the repository root:

```bash
python src/collect_reviews.py --count 500 --delay-seconds 1.5
python src/clean_reviews.py
python src/load_database.py
python src/verify_database.py
jupyter lab analysis/google_play_eda.ipynb
```

The collector writes one JSONL file per app/run and one independent run manifest to `data/raw/`. The manifest is written even if an app returns zero reviews or part of the run fails, so collection attempts are not lost after review-level deduplication. It returns a non-zero exit code if an app fails, but retains successful app outputs and the run manifest for investigation. Re-running cleaning is safe; database loading uses `(app_id, source_review_id)` as its unique key, upserts changed review fields, and preserves each review's original `first_collected_run_id`.

## Collection-run lineage check

Each collection attempt is represented by an immutable `*_run_manifest.json`,
separate from the review JSONL output. `clean_reviews.py` produces both
`reviews_clean.csv` and `collection_runs_clean.csv`; the database loader loads
the latter first. This means all-zero, duplicate-only, and partial runs remain
queryable even when no new review is inserted.

Run the controlled regression test after changing ingestion logic:

```bash
python -m unittest tests/test_repeated_ingestion.py -v
```

It verifies an initial load, a repeat collection, an overlapping/new-review
run, and a zero-result run. Expected result: three retained reviews; A and B
keep `run-001` as their first collection run, C receives `run-003`, and all
four collection runs remain stored.

The checked-in [controlled test record](docs/REPEATED_INGESTION_TEST.md)
explains the inputs, assertions, and outcome without publishing review data.

## Schema rationale

`apps` stores product metadata, `collection_runs` records source-collection batches, and `reviews` stores normalized records linked to each app and the Google Play collection run in which each review was first seen. This avoids repeating product fields in every review while retaining source-file and collection-run provenance. SQLite is appropriate for local prototyping; PostgreSQL can replace it later without changing the data model substantially.

See [the database schema guide](docs/DATABASE_SCHEMA.md) for the implemented columns, keys, Google Play field mapping, ERD, and collection-run lineage rules.

## Quality rules

The cleaning step removes rows with missing review IDs, blank review text, or ratings outside 1-5; normalizes whitespace/timestamps; clips invalid helpful-vote counts to zero; and deduplicates by app plus source review ID. It writes `data/quality/quality_report.json` so the EDA and findings can report what changed.

## Privacy and reporting

Do not publish raw review text, reviewer identifiers, or screenshots containing them without approval. The EDA is for aggregate analysis. In the final update, include collection time, actual sample sizes, cleaning outcomes, and the unofficial-source limitation.
