# Live repeated-ingestion validation

This document records the end-to-end validation requested after the collection-run lineage correction. It uses a small live Google Play sample via the unofficial `google-play-scraper` package. Raw reviews and manifests remain ignored by Git because they may contain review text or user metadata; this document contains aggregate results only.

## Scope

- **Date:** 2026-11-05 (UTC)
- **Apps:** Spotify (`com.spotify.music`), Duolingo (`com.duolingo`), and Airbnb (`com.airbnb.android`)
- **Storefront / language:** US / English
- **Request per app per run:** 25 newest reviews
- **Runs:** three separately invoked collections, each with its own manifest and run ID

## Run results

| Run ID | UTC start | UTC finish | Returned rows | New unique reviews vs. prior live runs | Previously seen reviews | Status |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `live-20261105-a` | 20:14:49 | 20:14:52 | 75 | 75 | 0 | completed |
| `live-20261105-b` | 20:17:11 | 20:17:13 | 75 | 4 | 71 | completed |
| `live-20261105-c` | 20:17:55 | 20:17:58 | 75 | 0 | 75 | completed |

All three manifests recorded three attempted apps, 75 returned rows, and zero failures. The live runs contained 79 distinct `(package_name, reviewId)` pairs in total. The second run produced both new and repeated reviews; the third run was duplicate-only relative to the earlier live runs.

## End-to-end checks

The database loader processed each separate raw collection in order. Final quality and integrity checks reported:

- zero blank required review fields;
- zero invalid ratings;
- zero duplicate `(app_id, source_review_id)` database keys; and
- zero foreign-key violations.

For all 79 live review keys, the database value of `first_collected_run_id` matched the earliest observation across raw files (**79 / 79**, zero mismatches). Of 75 repeated live keys, all retained `live-20261105-a`; 4 new second-run keys retained `live-20261105-b`.

## Compatibility check

The previous local SQLite prototype schema required a requested review count and did not allow a `partial` status. The loader now migrates that older schema transactionally before loading independent manifests. A migration test on a temporary copy preserved 5,575 prior review rows and produced zero foreign-key violations.

## Interpretation

This is a behavioral validation, not a claim that three short runs capture a representative longitudinal sample. Because the collector requests newest reviews over a short interval, repeat observations are expected. The test demonstrates that the corrected pipeline records actual collection attempts and preserves first-seen lineage end to end.
