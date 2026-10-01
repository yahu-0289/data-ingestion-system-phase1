# Data Ingestion System - Phase I

Reusable prototype for collecting Google Play reviews, cleaning them, loading a normalized SQLite database, and conducting exploratory analysis. It supports the Phase I brief's three core capabilities: automated acquisition, repeatable structuring/validation, and SQL-queryable storage.

## Scope and source decision

Google Play reviews are the selected research/prototype source. The collector uses the **unofficial third-party** [`google-play-scraper`](https://pypi.org/project/google-play-scraper/) package, not an official Google API. Availability, response fields, and permitted use can change, so keep this limitation visible in any report and respect applicable Google Play terms and rate limits.

The supplied `config/apps.csv` starts with 12 apps across seven categories and a target of up to 500 reviews per app (about 6,000 records before availability, duplicates, and cleaning). This is a project sampling decision, not a requirement from John.

## Project layout

```text
config/apps.csv              App-level collection configuration
src/collect_reviews.py       Configurable acquisition into append-only JSONL
src/clean_reviews.py         Validation, normalization, and deduplication
src/schema.sql               SQLite relational schema: apps, runs, reviews
src/load_database.py         Repeatable cleaned-data loader (upsert-safe)
src/verify_database.py       Basic quality and integrity queries
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

The collector writes one JSONL file per app/run to `data/raw/`. It returns a non-zero exit code if an app fails, but retains successful app outputs so the failure can be investigated without losing work. Re-running cleaning is safe; database loading uses `(app_id, source_review_id)` as its unique key and upserts changed fields.

## Schema rationale

`apps` stores durable product metadata, `collection_runs` provides run-level lineage, and `reviews` stores normalized records linked to each app and initial collection run. This avoids repeating product fields in the database while retaining raw-file provenance. SQLite is appropriate for local prototyping; PostgreSQL can replace it later without changing the data model substantially.

## Quality rules

The cleaning step removes rows with missing review IDs, blank review text, or ratings outside 1-5; normalizes whitespace/timestamps; clips invalid helpful-vote counts to zero; and deduplicates by app plus source review ID. It writes `data/quality/quality_report.json` so the EDA and findings can report what changed.

## Privacy and reporting

Do not publish raw review text, reviewer identifiers, or screenshots containing them without approval. The EDA is for aggregate analysis. In the final update, include collection time, actual sample sizes, cleaning outcomes, and the unofficial-source limitation.
