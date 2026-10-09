#!/usr/bin/env python3
"""Run basic completeness and integrity checks against the SQLite database."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data" / "reviews.sqlite"

QUERIES = {
    "reviews_by_category": "SELECT a.category, COUNT(*) AS reviews, ROUND(AVG(r.rating), 2) AS avg_rating FROM reviews r JOIN apps a USING(app_id) GROUP BY a.category ORDER BY reviews DESC",
    "missing_required_fields": "SELECT SUM(review_text = '') AS blank_text, SUM(rating NOT BETWEEN 1 AND 5) AS invalid_rating, SUM(source_review_id IS NULL) AS missing_source_id FROM reviews",
    "duplicate_keys": "SELECT COUNT(*) - COUNT(DISTINCT app_id || ':' || source_review_id) AS duplicate_keys FROM reviews",
    "optional_metadata_coverage": "SELECT COUNT(*) AS reviews, SUM(app_version IS NOT NULL) AS with_app_version, SUM(reply_text IS NOT NULL) AS with_developer_reply FROM reviews",
    "foreign_key_violations": "PRAGMA foreign_key_check",
}

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DATABASE)
    args = parser.parse_args()
    if not args.database.exists():
        raise SystemExit(f"Database not found: {args.database}. Run load_database.py first.")
    with sqlite3.connect(args.database) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        for name, query in QUERIES.items():
            print(f"\n[{name}]")
            rows = connection.execute(query).fetchall()
            if rows:
                for row in rows:
                    print(row)
            elif name == "foreign_key_violations":
                print("No violations found.")


if __name__ == "__main__":
    main()
