#!/usr/bin/env python3
"""Run basic completeness and integrity checks against the SQLite database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data" / "reviews.sqlite"

QUERIES = {
    "reviews_by_category": "SELECT a.category, COUNT(*) AS reviews, ROUND(AVG(r.rating), 2) AS avg_rating FROM reviews r JOIN apps a USING(app_id) GROUP BY a.category ORDER BY reviews DESC",
    "missing_required_fields": "SELECT SUM(review_text = '') AS blank_text, SUM(rating NOT BETWEEN 1 AND 5) AS invalid_rating, SUM(source_review_id IS NULL) AS missing_source_id FROM reviews",
    "duplicate_keys": "SELECT COUNT(*) - COUNT(DISTINCT app_id || ':' || source_review_id) AS duplicate_keys FROM reviews",
}

with sqlite3.connect(DATABASE) as connection:
    for name, query in QUERIES.items():
        print(f"\n[{name}]")
        for row in connection.execute(query):
            print(row)

