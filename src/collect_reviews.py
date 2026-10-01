#!/usr/bin/env python3
"""Collect configurable Google Play reviews into append-only JSONL files.

This is a prototype collector that uses the unofficial `google-play-scraper`
package.  It is not a Google-supported API client; availability and fields can
change without notice.  Use only in accordance with Google Play's terms and
rate-limit the collection.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from google_play_scraper import Sort, reviews


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "apps.csv"
RAW_DIR = ROOT / "data" / "raw"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=500, help="Target reviews per enabled app.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--delay-seconds", type=float, default=1.5, help="Pause between apps.")
    parser.add_argument("--run-id", default=None, help="Optional ID for repeatable run tracking.")
    return parser


def enabled_apps(config_path: Path) -> pd.DataFrame:
    apps = pd.read_csv(config_path, dtype={"package_name": "string"})
    required = {"package_name", "app_name", "category", "country", "language", "enabled"}
    missing = required - set(apps.columns)
    if missing:
        raise ValueError(f"Config is missing columns: {sorted(missing)}")
    enabled = apps[apps["enabled"].astype(str).str.upper().eq("TRUE")].copy()
    if enabled.empty:
        raise ValueError("No enabled apps found in config.")
    return enabled


def collect_one(app: pd.Series, count: int, run_id: str) -> int:
    package = str(app["package_name"])
    logging.info("Collecting up to %s reviews for %s", count, package)
    result, _ = reviews(
        package,
        lang=str(app["language"]),
        country=str(app["country"]),
        sort=Sort.NEWEST,
        count=count,
    )
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    target = RAW_DIR / f"{run_id}__{package.replace('.', '_')}.jsonl"
    with target.open("w", encoding="utf-8") as stream:
        for record in result:
            record["_ingestion"] = {
                "run_id": run_id,
                "collected_at": utc_now(),
                "package_name": package,
                "app_name": str(app["app_name"]),
                "category": str(app["category"]),
                "country": str(app["country"]),
                "language": str(app["language"]),
                "source": "google_play_unofficial_google_play_scraper",
            }
            stream.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")
    logging.info("Wrote %s reviews to %s", len(result), target.relative_to(ROOT))
    return len(result)


def main() -> None:
    args = build_parser().parse_args()
    if args.count <= 0:
        raise SystemExit("--count must be positive")
    if args.delay_seconds < 0:
        raise SystemExit("--delay-seconds cannot be negative")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    apps = enabled_apps(args.config)
    total = 0
    failures: list[str] = []
    for index, (_, app) in enumerate(apps.iterrows()):
        try:
            total += collect_one(app, args.count, run_id)
        except Exception as exc:  # preserve other app outputs if one fails
            logging.exception("Collection failed for %s: %s", app["package_name"], exc)
            failures.append(str(app["package_name"]))
        if index < len(apps) - 1:
            time.sleep(args.delay_seconds)
    logging.info("Run %s finished: %s reviews across %s apps; failures: %s", run_id, total, len(apps), failures or "none")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

