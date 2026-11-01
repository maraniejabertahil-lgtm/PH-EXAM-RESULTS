CREATE TABLE IF NOT EXISTS source_states (
  source_id TEXT PRIMARY KEY,
  etag TEXT,
  last_modified TEXT,
  checked_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS monitoring_logs (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  status TEXT NOT NULL,
  run_timestamp TEXT NOT NULL,
  error_details TEXT,
  etag TEXT,
  last_modified TEXT
);

CREATE TABLE IF NOT EXISTS import_batches (
  batch_id TEXT PRIMARY KEY,
  authority TEXT NOT NULL,
  exam TEXT NOT NULL,
  year INTEGER NOT NULL,
  total_records INTEGER NOT NULL DEFAULT 0,
  valid_records INTEGER NOT NULL DEFAULT 0,
  invalid_records INTEGER NOT NULL DEFAULT 0,
  exact_duplicates INTEGER NOT NULL DEFAULT 0,
  fuzzy_candidates INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  source_reference TEXT,
  report_path TEXT
);

CREATE TABLE IF NOT EXISTS release_predictions (
  authority TEXT NOT NULL,
  exam TEXT NOT NULL,
  year INTEGER NOT NULL,
  predicted_date TEXT,
  actual_date TEXT,
  data_points INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (authority, exam, year)
);

CREATE TABLE IF NOT EXISTS publication_versions (
  version_id TEXT PRIMARY KEY,
  authority TEXT NOT NULL,
  exam TEXT NOT NULL,
  year INTEGER NOT NULL,
  manifest_hash TEXT NOT NULL,
  record_count INTEGER NOT NULL,
  published_at TEXT NOT NULL,
  git_commit TEXT
);
