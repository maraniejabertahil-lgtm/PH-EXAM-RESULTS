CREATE TABLE IF NOT EXISTS monitoring_logs (
  event_id TEXT PRIMARY KEY,
  execution_id TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  component TEXT NOT NULL,
  operation TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed', 'blocked', 'warning')),
  severity TEXT NOT NULL DEFAULT 'info' CHECK (severity IN ('info', 'warning', 'error', 'critical')),
  duration_ms INTEGER,
  message TEXT NOT NULL,
  error_code TEXT,
  error_message TEXT,
  source TEXT NOT NULL DEFAULT 'system',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_monitoring_logs_occurred_at ON monitoring_logs(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_monitoring_logs_execution_id ON monitoring_logs(execution_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_monitoring_logs_status ON monitoring_logs(status, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_monitoring_logs_component ON monitoring_logs(component, occurred_at DESC);
CREATE TABLE IF NOT EXISTS import_batches (
  batch_id TEXT PRIMARY KEY, authority TEXT NOT NULL, exam TEXT NOT NULL, exam_year INTEGER NOT NULL,
  status TEXT NOT NULL, announced_count INTEGER, record_count INTEGER, greenlight_score INTEGER,
  provenance TEXT, started_at TEXT, completed_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS release_predictions (
  prediction_id TEXT PRIMARY KEY, authority TEXT NOT NULL, exam TEXT NOT NULL,
  predicted_release_date TEXT, source TEXT, status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
