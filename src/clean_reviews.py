#!/usr/bin/env python3
"""Validate raw JSONL review files and produce a clean, deduplicated CSV."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
QUALITY_DIR = ROOT / "data" / "quality"
OUTPUT_COLUMNS = [
    "source_review_id", "package_name", "app_name", "category", "country", "language",
    "review_text", "rating", "review_created_at", "review_updated_at", "thumbs_up_count",
    "app_version", "reply_text", "reply_created_at", "collected_at", "run_id", "raw_file",
]


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def iso_or_null(value: object) -> str | None:
    if value is None or value == "":
        return None
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    return None if pd.isna(parsed) else parsed.isoformat()


def load_raw(raw_dir: Path) -> tuple[pd.DataFrame, int]:
    rows: list[dict] = []
    invalid_lines = 0
    for path in sorted(raw_dir.glob("*.jsonl")):
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                try:
                    source = json.loads(line)
                    ingestion = source.get("_ingestion", {})
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
                        "collected_at": ingestion.get("collected_at"),
                        "run_id": ingestion.get("run_id"),
                        "raw_file": path.name,
                    })
                except (json.JSONDecodeError, TypeError, ValueError):
                    invalid_lines += 1
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS), invalid_lines


def clean(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    initial = len(frame)
    if frame.empty:
        return frame, {"rows_read": 0, "rows_retained": 0, "invalid_rows": 0}
    frame["rating"] = pd.to_numeric(frame["rating"], errors="coerce").astype("Int64")
    frame["thumbs_up_count"] = pd.to_numeric(frame["thumbs_up_count"], errors="coerce").fillna(0).clip(lower=0).astype("Int64")
    missing_id = int(frame["source_review_id"].isna().sum())
    blank_text = int(frame["review_text"].eq("").sum())
    invalid_rating = int((~frame["rating"].between(1, 5)).sum())
    valid = frame[
        frame["source_review_id"].notna()
        & frame["review_text"].ne("")
        & frame["rating"].between(1, 5)
    ].copy()
    before_dedupe = len(valid)
    valid = valid.drop_duplicates(subset=["package_name", "source_review_id"], keep="last")
    valid["review_text_length"] = valid["review_text"].str.len()
    valid = valid.sort_values(["category", "app_name", "review_created_at"], na_position="last")
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "rows_read": initial,
        "rows_retained": len(valid),
        "invalid_or_missing_source_review_id": missing_id,
        "blank_review_text": blank_text,
        "invalid_rating": invalid_rating,
        "duplicates_removed": before_dedupe - len(valid),
        "missing_by_column": {key: int(value) for key, value in valid.isna().sum().items()},
        "reviews_by_category": valid["category"].value_counts(dropna=False).to_dict(),
        "reviews_by_app": valid["app_name"].value_counts(dropna=False).to_dict(),
    }
    return valid, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    args = parser.parse_args()
    raw, invalid_lines = load_raw(args.raw_dir)
    cleaned, report = clean(raw)
    report["malformed_jsonl_lines"] = invalid_lines
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    QUALITY_DIR.mkdir(parents=True, exist_ok=True)
    cleaned.to_csv(PROCESSED_DIR / "reviews_clean.csv", index=False)
    (QUALITY_DIR / "quality_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("rows_read", "rows_retained", "duplicates_removed", "malformed_jsonl_lines")}, indent=2))


if __name__ == "__main__":
    main()

