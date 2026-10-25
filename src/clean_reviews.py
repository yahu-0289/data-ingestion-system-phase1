#!/usr/bin/env python3
"""Validate raw review records and run manifests, then create clean outputs.

Review rows are deduplicated for analysis and storage, but collection-run
manifests are deliberately retained independently. This makes a no-result,
duplicate-only, or partial collection visible in SQLite even when it adds no
new review rows.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
QUALITY_DIR = ROOT / "data" / "quality"
MANIFEST_SUFFIX = "__run_manifest.json"
OUTPUT_COLUMNS = [
    "source_review_id", "package_name", "app_name", "category", "country", "language",
    "review_text", "rating", "review_created_at", "review_updated_at", "thumbs_up_count",
    "app_version", "reply_text", "reply_created_at", "collected_at", "run_id",
    "first_collected_run_id", "source_name", "requested_reviews_per_app", "raw_file",
]
RUN_COLUMNS = [
    "run_id", "started_at", "finished_at", "requested_reviews_per_app", "source_name",
    "collector_version", "status", "notes",
]
RUN_STATUSES = {"completed", "partial", "failed"}
DEFAULT_SOURCE = "google_play_unofficial_google_play_scraper"


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def iso_or_null(value: object) -> str | None:
    if value is None or value == "":
        return None
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    return None if pd.isna(parsed) else parsed.isoformat()


def _manifest_row(manifest: dict, filename: str) -> dict:
    run_id = str(manifest.get("run_id", "")).strip()
    if not run_id:
        raise ValueError("run_id is required")
    status = str(manifest.get("status", "completed")).strip().lower()
    if status not in RUN_STATUSES:
        raise ValueError(f"invalid run status: {status}")
    outcomes = manifest.get("outcomes", [])
    if not isinstance(outcomes, list):
        raise ValueError("outcomes must be a list")
    attempted = len(outcomes)
    returned = sum(int(item.get("returned_reviews", 0) or 0) for item in outcomes if isinstance(item, dict))
    failed = sum(1 for item in outcomes if isinstance(item, dict) and item.get("status") == "failed")
    notes = f"manifest={filename}; apps_attempted={attempted}; returned_reviews={returned}; failed_apps={failed}"
    return {
        "run_id": run_id,
        "started_at": iso_or_null(manifest.get("started_at")),
        "finished_at": iso_or_null(manifest.get("finished_at")),
        "requested_reviews_per_app": manifest.get("requested_reviews_per_app"),
        "source_name": normalize_text(manifest.get("source_name")) or DEFAULT_SOURCE,
        "collector_version": normalize_text(manifest.get("collector_version")) or None,
        "status": status,
        "notes": notes,
    }


def load_raw(raw_dir: Path) -> tuple[pd.DataFrame, int, pd.DataFrame, int]:
    """Read review JSONL plus independent collection-run manifest files."""
    rows: list[dict] = []
    invalid_lines = 0
    invalid_manifests = 0
    run_rows: list[dict] = []
    observation_order = 0
    for manifest_path in sorted(raw_dir.glob(f"*{MANIFEST_SUFFIX}")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            run_rows.append(_manifest_row(manifest, manifest_path.name))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            invalid_manifests += 1
            print(f"Skipping invalid run manifest {manifest_path.name}: {exc}")
    for path in sorted(raw_dir.glob("*.jsonl")):
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    source = json.loads(line)
                    ingestion = source.get("_ingestion", {})
                    observation_order += 1
                    rows.append({
                        "source_review_id": source.get("reviewId"),
                        "package_name": ingestion.get("package_name"),
                        "app_name": ingestion.get("app_name"),
                        "category": ingestion.get("category"),
                        "country": ingestion.get("country"),
                        "language": ingestion.get("language"),
                        "review_text": normalize_text(source.get("content")),
                        "rating": source.get("score"),
                        "review_created_at": iso_or_null(source.get("at")),
                        "review_updated_at": iso_or_null(source.get("updated")),
                        "thumbs_up_count": source.get("thumbsUpCount"),
                        "app_version": source.get("reviewCreatedVersion"),
                        "reply_text": normalize_text(source.get("replyContent")) or None,
                        "reply_created_at": iso_or_null(source.get("repliedAt")),
                        "collected_at": iso_or_null(ingestion.get("collected_at")),
                        "run_id": ingestion.get("run_id"),
                        "source_name": ingestion.get("source"),
                        "requested_reviews_per_app": ingestion.get("requested_reviews_per_app"),
                        "raw_file": path.name,
                        "_observation_order": observation_order,
                    })
                except (json.JSONDecodeError, TypeError, ValueError):
                    invalid_lines += 1
    raw = pd.DataFrame(rows, columns=OUTPUT_COLUMNS + ["_observation_order"])
    runs = pd.DataFrame(run_rows, columns=RUN_COLUMNS)
    return raw, invalid_lines, runs, invalid_manifests


def legacy_runs_from_observations(frame: pd.DataFrame, manifest_runs: pd.DataFrame) -> pd.DataFrame:
    """Provide a labelled compatibility path for old JSONL files without manifests."""
    if frame.empty:
        return pd.DataFrame(columns=RUN_COLUMNS)
    known = set(manifest_runs["run_id"].dropna().astype(str)) if not manifest_runs.empty else set()
    legacy = frame[frame["run_id"].notna() & ~frame["run_id"].astype(str).isin(known)].copy()
    rows: list[dict] = []
    for run_id, group in legacy.groupby("run_id", sort=False):
        timestamps = pd.to_datetime(group["collected_at"], utc=True, errors="coerce").dropna()
        requested = pd.to_numeric(group["requested_reviews_per_app"], errors="coerce").dropna()
        rows.append({
            "run_id": str(run_id),
            "started_at": timestamps.min().isoformat() if not timestamps.empty else datetime.now(timezone.utc).isoformat(),
            "finished_at": timestamps.max().isoformat() if not timestamps.empty else None,
            "requested_reviews_per_app": int(requested.iloc[0]) if not requested.empty else None,
            "source_name": normalize_text(group["source_name"].iloc[0]) or DEFAULT_SOURCE,
            "collector_version": None,
            "status": "completed",
            "notes": "Legacy compatibility record derived from raw review rows; no independent run manifest was available.",
        })
    return pd.DataFrame(rows, columns=RUN_COLUMNS)


def clean(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    initial = len(frame)
    if frame.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS + ["review_text_length"]), {
            "rows_read": 0, "rows_retained": 0, "invalid_rows": 0, "duplicates_removed": 0,
        }
    frame = frame.copy()
    frame["rating"] = pd.to_numeric(frame["rating"], errors="coerce").astype("Int64")
    frame["thumbs_up_count"] = pd.to_numeric(frame["thumbs_up_count"], errors="coerce").fillna(0).clip(lower=0).astype("Int64")
    frame["requested_reviews_per_app"] = pd.to_numeric(
        frame["requested_reviews_per_app"], errors="coerce"
    ).where(lambda values: values.gt(0)).astype("Int64")
    missing_id = int(frame["source_review_id"].isna().sum())
    blank_text = int(frame["review_text"].eq("").sum())
    invalid_rating = int((~frame["rating"].between(1, 5)).sum())
    valid = frame[
        frame["source_review_id"].notna()
        & frame["package_name"].notna()
        & frame["run_id"].notna()
        & frame["review_text"].ne("")
        & frame["rating"].between(1, 5)
    ].copy()
    before_dedupe = len(valid)
    valid["_observed_at"] = pd.to_datetime(valid["collected_at"], utc=True, errors="coerce")
    valid = valid.sort_values(["_observed_at", "_observation_order"], na_position="last", kind="stable")
    keys = ["package_name", "source_review_id"]
    first_seen = valid.drop_duplicates(subset=keys, keep="first").set_index(keys)["run_id"]
    latest = valid.drop_duplicates(subset=keys, keep="last").copy()
    latest["first_collected_run_id"] = [first_seen.loc[(row.package_name, row.source_review_id)] for row in latest.itertuples()]
    latest["review_text_length"] = latest["review_text"].str.len()
    latest = latest.sort_values(["category", "app_name", "review_created_at"], na_position="last")
    latest = latest.drop(columns=["_observation_order", "_observed_at"])
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows_read": initial,
        "rows_retained": len(latest),
        "invalid_or_missing_source_review_id": missing_id,
        "blank_review_text": blank_text,
        "invalid_rating": invalid_rating,
        "duplicates_removed": before_dedupe - len(latest),
        "missing_by_column": {key: int(value) for key, value in latest.isna().sum().items()},
        "reviews_by_category": latest["category"].value_counts(dropna=False).to_dict(),
        "reviews_by_app": latest["app_name"].value_counts(dropna=False).to_dict(),
    }
    return latest, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--processed-output", type=Path, default=PROCESSED_DIR / "reviews_clean.csv")
    parser.add_argument("--runs-output", type=Path, default=PROCESSED_DIR / "collection_runs_clean.csv")
    parser.add_argument("--quality-output", type=Path, default=QUALITY_DIR / "quality_report.json")
    args = parser.parse_args()
    raw, invalid_lines, manifest_runs, invalid_manifests = load_raw(args.raw_dir)
    cleaned, report = clean(raw)
    legacy_runs = legacy_runs_from_observations(raw, manifest_runs)
    runs = pd.concat([manifest_runs, legacy_runs], ignore_index=True).drop_duplicates(subset=["run_id"], keep="first")
    report.update({
        "malformed_jsonl_lines": invalid_lines,
        "invalid_run_manifests": invalid_manifests,
        "collection_runs_recorded": len(runs),
        "manifest_backed_runs": len(manifest_runs),
        "legacy_derived_runs": len(legacy_runs),
    })
    args.processed_output.parent.mkdir(parents=True, exist_ok=True)
    args.runs_output.parent.mkdir(parents=True, exist_ok=True)
    args.quality_output.parent.mkdir(parents=True, exist_ok=True)
    cleaned.to_csv(args.processed_output, index=False)
    runs.to_csv(args.runs_output, index=False)
    args.quality_output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "rows_read", "rows_retained", "duplicates_removed", "malformed_jsonl_lines",
        "collection_runs_recorded", "manifest_backed_runs",
    )}, indent=2))


if __name__ == "__main__":
    main()
