-- Private operational metadata only. Never store examinee names or result rows here.
CREATE TABLE IF NOT EXISTS monitoring_logs (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL CHECK (event_type IN ('processing_started','greenlight_passed','greenlight_failed','publication_completed','publication_failed')),
  status TEXT NOT NULL CHECK (status IN ('started','passed','failed','completed')),
  summary TEXT NOT NULL DEFAULT '',
  authority TEXT,
  exam TEXT,
  exam_year INTEGER,
  source_id TEXT,
  correlation_id TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_monitoring_logs_created ON monitoring_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_monitoring_logs_correlation ON monitoring_logs(correlation_id);

CREATE TABLE IF NOT EXISTS import_batches (
  batch_id TEXT PRIMARY KEY,
  authority TEXT NOT NULL,
  exam TEXT NOT NULL,
  exam_year INTEGER NOT NULL,
  source_id TEXT,
  status TEXT NOT NULL CHECK (status IN ('processing','greenlight_passed','greenlight_failed','published','failed')),
  greenlight_score INTEGER,
  announced_count INTEGER,
  extracted_count INTEGER,
  summary TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_import_batches_updated ON import_batches(updated_at DESC);

CREATE TABLE IF NOT EXISTS release_predictions (
  id TEXT PRIMARY KEY,
  authority TEXT NOT NULL,
  exam TEXT NOT NULL,
  exam_year INTEGER NOT NULL,
  predicted_release_date TEXT NOT NULL,
  method TEXT NOT NULL,
  confidence REAL,
  evidence_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_release_predictions_date ON release_predictions(predicted_release_date);
