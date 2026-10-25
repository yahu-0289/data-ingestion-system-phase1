#!/usr/bin/env python3
"""Controlled lineage test for initial, repeat, overlap/new, and zero-result runs."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "google_play_unofficial_google_play_scraper"
APP = {
    "package_name": "com.example.lineage",
    "app_name": "Lineage Test App",
    "category": "Testing",
    "country": "us",
    "language": "en",
}


def review(review_id: str, text: str, score: int, run_id: str, collected_at: str) -> dict:
    return {
        "reviewId": review_id,
        "content": text,
        "score": score,
        "at": "2026-10-01T00:00:00Z",
        "updated": "2026-10-01T00:00:00Z",
        "thumbsUpCount": 0,
        "_ingestion": {
            **APP,
            "run_id": run_id,
            "collected_at": collected_at,
            "source": SOURCE,
            "requested_reviews_per_app": 2,
        },
    }


def write_run(raw_dir: Path, run_id: str, records: list[dict], status: str = "completed") -> None:
    started = records[0]["_ingestion"]["collected_at"] if records else f"2026-10-0{run_id[-1]}T00:00:00Z"
    manifest = {
        "manifest_version": 1,
        "run_id": run_id,
        "started_at": started,
        "finished_at": started,
        "requested_reviews_per_app": 2,
        "source_name": SOURCE,
        "collector_version": "controlled-test",
        "status": status,
        "outcomes": [{
            "package_name": APP["package_name"],
            "status": "completed",
            "returned_reviews": len(records),
            "output_file": f"{run_id}__reviews.jsonl",
        }],
    }
    (raw_dir / f"{run_id}__run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with (raw_dir / f"{run_id}__reviews.jsonl").open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record) + "\n")


class RepeatedIngestionLineageTest(unittest.TestCase):
    def run_pipeline(self, raw_dir: Path, work_dir: Path, database: Path) -> None:
        reviews_csv = work_dir / "reviews_clean.csv"
        runs_csv = work_dir / "collection_runs_clean.csv"
        report = work_dir / "quality_report.json"
        subprocess.run([
            sys.executable, str(ROOT / "src" / "clean_reviews.py"),
            "--raw-dir", str(raw_dir), "--processed-output", str(reviews_csv),
            "--runs-output", str(runs_csv), "--quality-output", str(report),
        ], check=True, cwd=ROOT)
        subprocess.run([
            sys.executable, str(ROOT / "src" / "load_database.py"),
            "--input", str(reviews_csv), "--runs-input", str(runs_csv), "--database", str(database),
        ], check=True, cwd=ROOT)

    def test_run_lineage_and_deduplication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "reviews.sqlite"

            # 1. Initial load: two reviews first observed in run-001.
            raw_1 = root / "raw_1"; raw_1.mkdir()
            write_run(raw_1, "run-001", [
                review("A", "First version of A", 5, "run-001", "2026-10-01T10:00:00Z"),
                review("B", "First version of B", 4, "run-001", "2026-10-01T10:01:00Z"),
            ])
            self.run_pipeline(raw_1, root / "processed_1", database)

            # 2. Repeat collection: only overlapping reviews, including one
            # duplicate source row; it must create a run but no new review.
            raw_2 = root / "raw_2"; raw_2.mkdir()
            write_run(raw_2, "run-002", [
                review("A", "Updated version of A", 5, "run-002", "2026-10-02T10:00:00Z"),
                review("A", "Updated version of A", 5, "run-002", "2026-10-02T10:00:01Z"),
                review("B", "Updated version of B", 4, "run-002", "2026-10-02T10:01:00Z"),
            ])
            self.run_pipeline(raw_2, root / "processed_2", database)

            # 3. Overlap plus new review: B keeps its original lineage; C is new.
            raw_3 = root / "raw_3"; raw_3.mkdir()
            write_run(raw_3, "run-003", [
                review("B", "Latest version of B", 3, "run-003", "2026-10-03T10:00:00Z"),
                review("C", "New review C", 5, "run-003", "2026-10-03T10:01:00Z"),
            ], status="partial")
            self.run_pipeline(raw_3, root / "processed_3", database)

            # 4. Zero-result run: the manifest must survive even without JSONL rows.
            raw_4 = root / "raw_4"; raw_4.mkdir()
            write_run(raw_4, "run-004", [])
            self.run_pipeline(raw_4, root / "processed_4", database)

            with sqlite3.connect(database) as connection:
                reviews = dict(connection.execute(
                    "SELECT source_review_id, first_collected_run_id FROM reviews"
                ).fetchall())
                run_statuses = dict(connection.execute(
                    "SELECT run_id, status FROM collection_runs"
                ).fetchall())
                review_count = connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
            self.assertEqual(review_count, 3)
            self.assertEqual(reviews, {"A": "run-001", "B": "run-001", "C": "run-003"})
            self.assertEqual(run_statuses, {
                "run-001": "completed", "run-002": "completed",
                "run-003": "partial", "run-004": "completed",
            })


if __name__ == "__main__":
    unittest.main(verbosity=2)
