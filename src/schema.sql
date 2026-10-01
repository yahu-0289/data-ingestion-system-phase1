PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS apps (
    app_id INTEGER PRIMARY KEY,
    package_name TEXT NOT NULL UNIQUE,
    app_name TEXT NOT NULL,
    category TEXT NOT NULL,
    country TEXT NOT NULL,
    language TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS collection_runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    requested_reviews_per_app INTEGER NOT NULL CHECK (requested_reviews_per_app > 0),
    source_name TEXT NOT NULL,
    collector_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id INTEGER PRIMARY KEY,
    app_id INTEGER NOT NULL REFERENCES apps(app_id),
    source_review_id TEXT NOT NULL,
    review_text TEXT NOT NULL,
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    review_created_at TEXT,
    review_updated_at TEXT,
    thumbs_up_count INTEGER CHECK (thumbs_up_count >= 0),
    app_version TEXT,
    reply_text TEXT,
    reply_created_at TEXT,
    language TEXT,
    raw_file TEXT NOT NULL,
    first_collected_run_id TEXT NOT NULL REFERENCES collection_runs(run_id),
    collected_at TEXT NOT NULL,
    text_length INTEGER NOT NULL CHECK (text_length >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(app_id, source_review_id)
);

CREATE INDEX IF NOT EXISTS idx_reviews_app_id ON reviews(app_id);
CREATE INDEX IF NOT EXISTS idx_reviews_rating ON reviews(rating);
CREATE INDEX IF NOT EXISTS idx_reviews_created_at ON reviews(review_created_at);

