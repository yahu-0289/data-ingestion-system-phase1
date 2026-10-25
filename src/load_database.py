#!/usr/bin/env python3
"""Load cleaned reviews and independently recorded collection runs into SQLite."""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data" / "processed" / "reviews_clean.csv"
DEFAULT_RUNS_CSV = ROOT / "data" / "processed" / "collection_runs_clean.csv"
DEFAULT_DB = ROOT / "data" / "reviews.sqlite"
SCHEMA = ROOT / "src" / "schema.sql"
DEFAULT_SOURCE = "google_play_unofficial_google_play_scraper"
REVIEW_REQUIRED = {
    "source_review_id", "package_name", "app_name", "category", "country", "language",
    "review_text", "rating", "review_created_at", "review_updated_at", "thumbs_up_count",
    "app_version", "reply_text", "reply_created_at", "collected_at", "raw_file",
    "review_text_length",
}
RUN_REQUIRED = {"run_id", "started_at", "source_name", "status"}


def sqlite_value(value: object) -> object | None:
    """Convert pandas missing values to SQLite NULL before parameter binding."""
    return None if pd.isna(value) else value


def read_csv_or_empty(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def normalize_runs(runs: pd.DataFrame) -> pd.DataFrame:
    if runs.empty:
        return pd.DataFrame(columns=[
            "run_id", "started_at", "finished_at", "requested_reviews_per_app", "source_name",
            "collector_version", "status", "notes",
        ])
    missing = RUN_REQUIRED - set(runs.columns)
    if missing:
        raise SystemExit(f"Collection-run input is missing columns: {sorted(missing)}")
    normalized = runs.copy()
    for column in ("finished_at", "requested_reviews_per_app", "collector_version", "notes"):
        if column not in normalized:
            normalized[column] = pd.NA
    normalized["run_id"] = normalized["run_id"].fillna("").astype(str).str.strip()
    normalized["source_name"] = normalized["source_name"].fillna(DEFAULT_SOURCE).astype(str).str.strip().replace("", DEFAULT_SOURCE)
    normalized["started_at"] = normalized["started_at"].fillna("").astype(str).str.strip()
    normalized["status"] = normalized["status"].fillna("completed").astype(str).str.lower().str.strip()
    invalid_status = set(normalized["status"]) - {"completed", "partial", "failed"}
    if normalized["run_id"].eq("").any() or normalized["started_at"].eq("").any() or invalid_status:
        raise SystemExit("Collection-run input has a blank run ID/start time or invalid status.")
    normalized["requested_reviews_per_app"] = pd.to_numeric(
        normalized["requested_reviews_per_app"], errors="coerce"
    ).where(lambda values: values.gt(0))
    return normalized.drop_duplicates(subset=["run_id"], keep="first")


def normalize_reviews(data: pd.DataFrame, fallback_run_id: str) -> pd.DataFrame:
    if data.empty:
        return data
    missing = REVIEW_REQUIRED - set(data.columns)
    if missing:
        raise SystemExit(f"Cleaned input is missing columns: {sorted(missing)}")
    normalized = data.copy()
    if "run_id" not in normalized:
        normalized["run_id"] = fallback_run_id
    normalized["run_id"] = normalized["run_id"].fillna("").astype(str).str.strip().replace("", fallback_run_id)
    if "first_collected_run_id" not in normalized:
        normalized["first_collected_run_id"] = normalized["run_id"]
    normalized["first_collected_run_id"] = normalized["first_collected_run_id"].fillna("").astype(str).str.strip()
    normalized.loc[normalized["first_collected_run_id"].eq(""), "first_collected_run_id"] = (
        normalized.loc[normalized["first_collected_run_id"].eq(""), "run_id"]
    )
    if "source_name" not in normalized:
        normalized["source_name"] = DEFAULT_SOURCE
    normalized["source_name"] = normalized["source_name"].fillna(DEFAULT_SOURCE).astype(str).str.strip().replace("", DEFAULT_SOURCE)
    if "requested_reviews_per_app" not in normalized:
        normalized["requested_reviews_per_app"] = pd.NA
    normalized["requested_reviews_per_app"] = pd.to_numeric(
        normalized["requested_reviews_per_app"], errors="coerce"
    ).where(lambda values: values.gt(0))
    return normalized


def runs_fallback_from_reviews(data: pd.DataFrame, known_run_ids: set[str]) -> pd.DataFrame:
    """Keep old cleaned CSVs loadable, clearly labelled as a legacy fallback."""
    rows: list[dict] = []
    if data.empty:
        return pd.DataFrame()
    for run_id in sorted(set(data["run_id"]) | set(data["first_collected_run_id"])):
        if run_id in known_run_ids:
            continue
        group = data[data["run_id"] == run_id]
        if group.empty:
            group = data[data["first_collected_run_id"] == run_id]
        timestamps = pd.to_datetime(group["collected_at"], utc=True, errors="coerce").dropna()
        requested = group["requested_reviews_per_app"].dropna()
        rows.append({
            "run_id": run_id,
            "started_at": timestamps.min().isoformat() if not timestamps.empty else datetime.now(timezone.utc).isoformat(),
            "finished_at": timestamps.max().isoformat() if not timestamps.empty else None,
            "requested_reviews_per_app": int(requested.iloc[0]) if not requested.empty else None,
            "source_name": group["source_name"].iloc[0] if not group.empty else DEFAULT_SOURCE,
            "collector_version": None,
            "status": "completed",
            "notes": "Legacy compatibility record derived from cleaned reviews; no run manifest was supplied.",
        })
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--runs-input", type=Path, default=DEFAULT_RUNS_CSV)
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--run-id", default=None, help="Fallback run ID for legacy cleaned CSVs.")
    args = parser.parse_args()
    if not args.input.exists() and not args.runs_input.exists():
        raise SystemExit("No cleaned reviews or collection-run manifest output found. Run clean_reviews.py first.")
    fallback_run_id = args.run_id or "legacy_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    reviews = normalize_reviews(read_csv_or_empty(args.input), fallback_run_id)
    runs = normalize_runs(read_csv_or_empty(args.runs_input))
    fallback_runs = runs_fallback_from_reviews(reviews, set(runs["run_id"]))
    if not fallback_runs.empty:
        runs = pd.concat([runs, normalize_runs(fallback_runs)], ignore_index=True)
    if reviews.empty and runs.empty:
        raise SystemExit("Both cleaned reviews and collection-run records are empty; nothing to load.")

    args.database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(args.database)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    try:
        with connection:
            # Runs are loaded first and never inferred solely from retained review rows.
            for run in runs.itertuples(index=False):
                connection.execute(
                    """INSERT INTO collection_runs
                    (run_id, started_at, finished_at, requested_reviews_per_app, source_name, collector_version, status, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                        finished_at=COALESCE(excluded.finished_at, collection_runs.finished_at),
                        requested_reviews_per_app=COALESCE(excluded.requested_reviews_per_app, collection_runs.requested_reviews_per_app),
                        source_name=excluded.source_name,
                        collector_version=COALESCE(excluded.collector_version, collection_runs.collector_version),
                        status=excluded.status,
                        notes=COALESCE(excluded.notes, collection_runs.notes)""",
                    (run.run_id, run.started_at, sqlite_value(run.finished_at),
                     sqlite_value(run.requested_reviews_per_app), run.source_name,
                     sqlite_value(run.collector_version), run.status, sqlite_value(run.notes)),
                )
            if not reviews.empty:
                for app in reviews[["package_name", "app_name", "category", "country", "language"]].drop_duplicates().itertuples(index=False):
                    connection.execute(
                        "INSERT INTO apps (package_name, app_name, category, country, language) VALUES (?, ?, ?, ?, ?) ON CONFLICT(package_name) DO UPDATE SET app_name=excluded.app_name, category=excluded.category, country=excluded.country, language=excluded.language",
                        tuple(app),
                    )
                app_ids = dict(connection.execute("SELECT package_name, app_id FROM apps").fetchall())
                for row in reviews.itertuples(index=False):
                    connection.execute(
                        """INSERT INTO reviews (app_id, source_review_id, review_text, rating, review_created_at, review_updated_at, thumbs_up_count, app_version, reply_text, reply_created_at, language, raw_file, first_collected_run_id, collected_at, text_length)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(app_id, source_review_id) DO UPDATE SET
                            review_text=excluded.review_text,
                            rating=excluded.rating,
                            review_updated_at=excluded.review_updated_at,
                            thumbs_up_count=excluded.thumbs_up_count,
                            app_version=excluded.app_version,
                            reply_text=excluded.reply_text,
                            reply_created_at=excluded.reply_created_at,
                            raw_file=excluded.raw_file,
                            collected_at=excluded.collected_at,
                            text_length=excluded.text_length""",
                        (app_ids[row.package_name], row.source_review_id, row.review_text, int(row.rating),
                         sqlite_value(row.review_created_at), sqlite_value(row.review_updated_at),
                         int(row.thumbs_up_count), sqlite_value(row.app_version),
                         sqlite_value(row.reply_text), sqlite_value(row.reply_created_at),
                         sqlite_value(row.language), row.raw_file, row.first_collected_run_id,
                         row.collected_at, int(row.review_text_length)),
                    )
    finally:
        connection.close()
    print(f"Loaded {len(reviews)} cleaned review row(s) and {len(runs)} collection run record(s) into {args.database}.")


if __name__ == "__main__":
    main()
