-- Dedicated Test Mode audit database only. Never bind this migration to production monitoring D1.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS test_runs (
  run_id TEXT PRIMARY KEY,
  mode TEXT NOT NULL CHECK (mode = 'REAL_WORLD'),
  status TEXT NOT NULL CHECK (status IN ('RUNNING','PASS','FAIL','BLOCKED','COMPLETED')),
  requested_by_owner_uid TEXT NOT NULL,
  source_release_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  source_url TEXT NOT NULL,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  duration_ms INTEGER,
  workflow_run_id TEXT,
  pull_request_number INTEGER,
  head_sha TEXT,
  merge_sha TEXT,
  deployment_id TEXT,
  deployment_url TEXT,
  report_sha256 TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS test_run_steps (
  step_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES test_runs(run_id) ON DELETE CASCADE,
  stage_number INTEGER NOT NULL CHECK (stage_number BETWEEN 1 AND 10),
  attempt INTEGER NOT NULL CHECK (attempt >= 1),
  status TEXT NOT NULL CHECK (status IN ('NOT RUN','RUNNING','PASS','FAIL','BLOCKED','SKIPPED')),
  started_at TEXT,
  completed_at TEXT,
  duration_ms INTEGER,
  expected_summary TEXT,
  actual_summary TEXT,
  evidence_json TEXT,
  failure_code TEXT,
  failure_message_redacted TEXT,
  idempotency_key TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (run_id, stage_number, attempt),
  UNIQUE (run_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS test_mode_publication_approvals (
  approval_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES test_runs(run_id) ON DELETE CASCADE,
  action TEXT NOT NULL CHECK (action IN ('MERGE','PRODUCTION_DEPLOYMENT')),
  status TEXT NOT NULL CHECK (status IN ('PENDING','APPROVED','INVALIDATED','CONSUMED')),
  approved_by_owner_uid TEXT,
  approved_at TEXT,
  approved_action_sha TEXT NOT NULL,
  artifact_manifest_sha256 TEXT NOT NULL,
  target_ref TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (run_id, action, approved_action_sha)
);

CREATE INDEX IF NOT EXISTS idx_test_runs_recent
  ON test_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_run_steps_order
  ON test_run_steps(run_id, stage_number, attempt);
CREATE INDEX IF NOT EXISTS idx_test_mode_approvals_run
  ON test_mode_publication_approvals(run_id, action, status);
