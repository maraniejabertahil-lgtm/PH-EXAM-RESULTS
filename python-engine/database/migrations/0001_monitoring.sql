-- Superset schema compatible with the private D1 metadata foundation.
-- Operational metadata only: never store examinee names or result rows.
CREATE TABLE IF NOT EXISTS monitoring_logs (
  id TEXT PRIMARY KEY,
  event_id TEXT UNIQUE,
  event_type TEXT NOT NULL CHECK (event_type IN ('processing_started', 'greenlight_passed', 'greenlight_failed', 'publication_completed', 'publication_failed')),
  status TEXT NOT NULL CHECK (status IN ('started', 'passed', 'failed', 'completed')),
  summary TEXT NOT NULL DEFAULT '',
  authority TEXT,
  exam TEXT,
  exam_year INTEGER,
  source_id TEXT,
  correlation_id TEXT,
  created_at TEXT NOT NULL,
  execution_id TEXT,
  occurred_at TEXT,
  component TEXT,
  operation TEXT,
  severity TEXT NOT NULL DEFAULT 'info',
  duration_ms INTEGER,
  message TEXT,
  error_code TEXT,
  error_message TEXT,
  source TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS import_batches (
  batch_id TEXT PRIMARY KEY,
  authority TEXT NOT NULL,
  exam TEXT NOT NULL,
  exam_year INTEGER NOT NULL,
  source_id TEXT,
  status TEXT NOT NULL CHECK (status IN ('processing', 'greenlight_passed', 'greenlight_failed', 'published', 'failed')),
  greenlight_score INTEGER,
  announced_count INTEGER,
  extracted_count INTEGER,
  record_count INTEGER,
  summary TEXT NOT NULL DEFAULT '',
  provenance TEXT,
  started_at TEXT,
  completed_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS release_predictions (
  id TEXT PRIMARY KEY,
  prediction_id TEXT UNIQUE,
  authority TEXT NOT NULL,
  exam TEXT NOT NULL,
  exam_year INTEGER NOT NULL,
  predicted_release_date TEXT NOT NULL,
  method TEXT NOT NULL,
  confidence REAL,
  evidence_count INTEGER NOT NULL DEFAULT 0,
  source TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL,
  updated_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_monitoring_logs_event_id ON monitoring_logs(event_id);
CREATE INDEX IF NOT EXISTS idx_monitoring_logs_occurred_at ON monitoring_logs(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_monitoring_logs_execution_id ON monitoring_logs(execution_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_monitoring_logs_status ON monitoring_logs(status, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_monitoring_logs_component ON monitoring_logs(component, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_monitoring_logs_created ON monitoring_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_import_batches_updated ON import_batches(updated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_release_predictions_prediction_id ON release_predictions(prediction_id);
CREATE INDEX IF NOT EXISTS idx_release_predictions_date ON release_predictions(predicted_release_date);
