-- Step 3B: verified Watcher release-event ledger and idempotent run linkage.
-- Apply only to the dedicated TEST_MODE_DB. Never apply to production monitoring D1.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS test_mode_release_events (
  event_id TEXT PRIMARY KEY,
  authority TEXT NOT NULL CHECK (authority = 'PRC'),
  source_id TEXT NOT NULL,
  release_id TEXT NOT NULL,
  source_url TEXT NOT NULL,
  exam_code TEXT NOT NULL,
  exam_title TEXT NOT NULL,
  exam_year INTEGER NOT NULL CHECK (exam_year BETWEEN 2000 AND 2100),
  event_fingerprint TEXT NOT NULL UNIQUE CHECK (length(event_fingerprint) = 64),
  payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
  detected_at TEXT NOT NULL,
  verified_at TEXT NOT NULL,
  verification_status TEXT NOT NULL CHECK (verification_status IN ('VERIFIED','REJECTED')),
  verification_method TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE test_runs ADD COLUMN source_event_id TEXT;
ALTER TABLE test_runs ADD COLUMN idempotency_key TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_test_runs_owner_idempotency
  ON test_runs(requested_by_owner_uid, idempotency_key)
  WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_test_mode_release_events_recent
  ON test_mode_release_events(detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_test_mode_release_events_lookup
  ON test_mode_release_events(event_id, verification_status, source_id);
