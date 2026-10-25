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
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from google_play_scraper import Sort, reviews


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "apps.csv"
RAW_DIR = ROOT / "data" / "raw"
MANIFEST_SUFFIX = "__run_manifest.json"
COLLECTOR_VERSION = "collect_reviews.py"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def collect_one(app: pd.Series, count: int, run_id: str) -> tuple[int, str]:
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
                "requested_reviews_per_app": count,
            }
            stream.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")
    logging.info("Wrote %s reviews to %s", len(result), target.relative_to(ROOT))
    return len(result), target.name


def write_run_manifest(manifest: dict) -> Path:
    """Persist a run record even when no review rows were returned.

    Review JSONL files are intentionally append-only.  The adjacent manifest is
    the authoritative record that a collection attempt occurred; it prevents
    zero-result, duplicate-only, and partial runs from disappearing during
    later review-level deduplication.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    target = RAW_DIR / f"{manifest['run_id']}{MANIFEST_SUFFIX}"
    target.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def main() -> None:
    args = build_parser().parse_args()
    if args.count <= 0:
        raise SystemExit("--count must be positive")
    if args.delay_seconds < 0:
        raise SystemExit("--delay-seconds cannot be negative")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    apps = enabled_apps(args.config)
    started_at = utc_now()
    total = 0
    failures: list[str] = []
    outcomes: list[dict] = []
    for index, (_, app) in enumerate(apps.iterrows()):
        package_name = str(app["package_name"])
        try:
            returned_reviews, output_file = collect_one(app, args.count, run_id)
            total += returned_reviews
            outcomes.append({
                "package_name": package_name,
                "status": "completed",
                "returned_reviews": returned_reviews,
                "output_file": output_file,
            })
        except Exception as exc:  # preserve other app outputs if one fails
            logging.exception("Collection failed for %s: %s", package_name, exc)
            failures.append(package_name)
            outcomes.append({
                "package_name": package_name,
                "status": "failed",
                "returned_reviews": 0,
                "error": f"{type(exc).__name__}: {exc}",
            })
        if index < len(apps) - 1:
            time.sleep(args.delay_seconds)
    status = "completed" if not failures else ("failed" if len(failures) == len(apps) else "partial")
    manifest_path = write_run_manifest({
        "manifest_version": 1,
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": utc_now(),
        "requested_reviews_per_app": args.count,
        "source_name": "google_play_unofficial_google_play_scraper",
        "collector_version": COLLECTOR_VERSION,
        "status": status,
        "outcomes": outcomes,
    })
    logging.info("Wrote run manifest to %s", manifest_path.relative_to(ROOT))
    logging.info("Run %s finished: %s reviews across %s apps; failures: %s", run_id, total, len(apps), failures or "none")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
