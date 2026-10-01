#!/usr/bin/env python3
"""Load cleaned review records into the normalized SQLite prototype database."""

from __future__ import annotations

import argparse
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data" / "processed" / "reviews_clean.csv"
DEFAULT_DB = ROOT / "data" / "reviews.sqlite"
SCHEMA = ROOT / "src" / "schema.sql"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    if not args.input.exists():
        raise SystemExit(f"Cleaned input not found: {args.input}. Run clean_reviews.py first.")
    data = pd.read_csv(args.input)
    if data.empty:
        raise SystemExit("Cleaned CSV is empty; nothing to load.")
    args.database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(args.database)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    run_id = args.run_id or "load_" + uuid.uuid4().hex[:12]
    started = datetime.now(UTC).isoformat()
    try:
        with connection:
            connection.execute(
                "INSERT INTO collection_runs (run_id, started_at, requested_reviews_per_app, source_name, collector_version, status, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, started, 0 + max(1, int(data.groupby("package_name").size().max())), "google_play_unofficial_google_play_scraper", "1.0", "running", "ETL load of cleaned CSV"),
            )
            for app in data[["package_name", "app_name", "category", "country", "language"]].drop_duplicates().itertuples(index=False):
                connection.execute(
                    "INSERT INTO apps (package_name, app_name, category, country, language) VALUES (?, ?, ?, ?, ?) ON CONFLICT(package_name) DO UPDATE SET app_name=excluded.app_name, category=excluded.category, country=excluded.country, language=excluded.language",
                    tuple(app),
                )
            app_ids = dict(connection.execute("SELECT package_name, app_id FROM apps").fetchall())
            inserted = 0
            for row in data.itertuples(index=False):
                cursor = connection.execute(
                    """INSERT INTO reviews (app_id, source_review_id, review_text, rating, review_created_at, review_updated_at, thumbs_up_count, app_version, reply_text, reply_created_at, language, raw_file, first_collected_run_id, collected_at, text_length)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(app_id, source_review_id) DO UPDATE SET review_text=excluded.review_text, rating=excluded.rating, review_updated_at=excluded.review_updated_at, thumbs_up_count=excluded.thumbs_up_count, app_version=excluded.app_version, reply_text=excluded.reply_text, reply_created_at=excluded.reply_created_at, collected_at=excluded.collected_at, text_length=excluded.text_length""",
                    (app_ids[row.package_name], row.source_review_id, row.review_text, int(row.rating), row.review_created_at, row.review_updated_at, int(row.thumbs_up_count), row.app_version, row.reply_text, row.reply_created_at, row.language, row.raw_file, run_id, row.collected_at, int(row.review_text_length)),
                )
                inserted += int(cursor.rowcount == 1)
            connection.execute("UPDATE collection_runs SET finished_at=?, status='completed' WHERE run_id=?", (datetime.now(UTC).isoformat(), run_id))
    except Exception:
        with connection:
            connection.execute("UPDATE collection_runs SET finished_at=?, status='failed' WHERE run_id=?", (datetime.now(UTC).isoformat(), run_id))
        raise
    finally:
        connection.close()
    print(f"Loaded {len(data)} cleaned rows into {args.database}; {inserted} rows inserted or updated.")


if __name__ == "__main__":
    main()

