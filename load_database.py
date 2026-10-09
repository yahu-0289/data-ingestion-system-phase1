#!/usr/bin/env python3
"""Load cleaned review records into the normalized SQLite prototype database."""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data" / "processed" / "reviews_clean.csv"
DEFAULT_DB = ROOT / "data" / "reviews.sqlite"
SCHEMA = ROOT / "src" / "schema.sql"
DEFAULT_SOURCE = "google_play_unofficial_google_play_scraper"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--run-id",
        default=None,
        help="Fallback source collection run ID for legacy cleaned CSVs that lack run_id.",
    )
    args = parser.parse_args()
    if not args.input.exists():
        raise SystemExit(f"Cleaned input not found: {args.input}. Run clean_reviews.py first.")
    data = pd.read_csv(args.input)
    if data.empty:
        raise SystemExit("Cleaned CSV is empty; nothing to load.")
    required = {
        "source_review_id", "package_name", "app_name", "category", "country", "language",
        "review_text", "rating", "review_created_at", "review_updated_at", "thumbs_up_count",
        "app_version", "reply_text", "reply_created_at", "collected_at", "raw_file",
        "review_text_length",
    }
    missing = required - set(data.columns)
    if missing:
        raise SystemExit(f"Cleaned input is missing columns: {sorted(missing)}")

    fallback_run_id = args.run_id or "legacy_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if "run_id" not in data:
        data["run_id"] = fallback_run_id
    data["run_id"] = data["run_id"].fillna("").astype(str).str.strip().replace("", fallback_run_id)
    if "source_name" not in data:
        data["source_name"] = DEFAULT_SOURCE
    data["source_name"] = data["source_name"].fillna(DEFAULT_SOURCE).astype(str).str.strip().replace("", DEFAULT_SOURCE)
    if "requested_reviews_per_app" not in data:
        data["requested_reviews_per_app"] = pd.NA
    data["requested_reviews_per_app"] = pd.to_numeric(
        data["requested_reviews_per_app"], errors="coerce"
    ).where(lambda values: values.gt(0))

    args.database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(args.database)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    try:
        with connection:
            for run_id, run_rows in data.groupby("run_id", sort=False):
                timestamps = pd.to_datetime(run_rows["collected_at"], utc=True, errors="coerce").dropna()
                started_at = timestamps.min().isoformat() if not timestamps.empty else datetime.now(timezone.utc).isoformat()
                finished_at = timestamps.max().isoformat() if not timestamps.empty else None
                requested = run_rows["requested_reviews_per_app"].dropna()
                requested_count = int(requested.iloc[0]) if not requested.empty else None
                source_name = run_rows["source_name"].iloc[0]
                connection.execute(
                    """INSERT INTO collection_runs
                    (run_id, started_at, finished_at, requested_reviews_per_app, source_name, status, notes)
                    VALUES (?, ?, ?, ?, ?, 'completed', ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                        finished_at=excluded.finished_at,
                        requested_reviews_per_app=COALESCE(excluded.requested_reviews_per_app, collection_runs.requested_reviews_per_app),
                        source_name=excluded.source_name,
                        status='completed'""",
                    (run_id, started_at, finished_at, requested_count, source_name, "Derived from cleaned review records"),
                )
            for app in data[["package_name", "app_name", "category", "country", "language"]].drop_duplicates().itertuples(index=False):
                connection.execute(
                    "INSERT INTO apps (package_name, app_name, category, country, language) VALUES (?, ?, ?, ?, ?) ON CONFLICT(package_name) DO UPDATE SET app_name=excluded.app_name, category=excluded.category, country=excluded.country, language=excluded.language",
                    tuple(app),
                )
            app_ids = dict(connection.execute("SELECT package_name, app_id FROM apps").fetchall())
            for row in data.itertuples(index=False):
                connection.execute(
                    """INSERT INTO reviews (app_id, source_review_id, review_text, rating, review_created_at, review_updated_at, thumbs_up_count, app_version, reply_text, reply_created_at, language, raw_file, first_collected_run_id, collected_at, text_length)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(app_id, source_review_id) DO UPDATE SET review_text=excluded.review_text, rating=excluded.rating, review_updated_at=excluded.review_updated_at, thumbs_up_count=excluded.thumbs_up_count, app_version=excluded.app_version, reply_text=excluded.reply_text, reply_created_at=excluded.reply_created_at, collected_at=excluded.collected_at, text_length=excluded.text_length""",
                    (app_ids[row.package_name], row.source_review_id, row.review_text, int(row.rating), row.review_created_at, row.review_updated_at, int(row.thumbs_up_count), row.app_version, row.reply_text, row.reply_created_at, row.language, row.raw_file, row.run_id, row.collected_at, int(row.review_text_length)),
                )
    finally:
        connection.close()
    print(f"Loaded {len(data)} cleaned rows across {data['run_id'].nunique()} source collection run(s) into {args.database}.")


if __name__ == "__main__":
    main()
