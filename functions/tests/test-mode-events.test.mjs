import test from "node:test";
import assert from "node:assert/strict";
import { onRequestPost } from "../api/test-mode/events.js";

const TOKEN = "test-mode-ingest-token-".padEnd(40, "x");
const SOURCE = {
  authority: "PRC", source_id: "prc-official-main",
  article_url: "https://www.prc.gov.ph/article/october-2026-exam-results",
  exam_code: "CPALE",
  exam_title: "October 2026 Certified Public Accountants Licensure Examination Results",
  exam_year: 2026, detected_at: new Date(Date.now() - 60_000).toISOString(),
};
const schemas = {
  test_runs: { columns: ["run_id","mode","status","requested_by_owner_uid","source_release_id","source_id","source_url","started_at","completed_at","duration_ms","workflow_run_id","pull_request_number","head_sha","merge_sha","deployment_id","deployment_url","report_sha256","source_event_id","idempotency_key","created_at","updated_at"], sql: "CHECK (mode = 'REAL_WORLD') CHECK (status IN ('RUNNING','PASS','FAIL','BLOCKED','COMPLETED'))" },
  test_run_steps: { columns: ["step_id","run_id","stage_number","attempt","status","started_at","completed_at","duration_ms","expected_summary","actual_summary","evidence_json","failure_code","failure_message_redacted","idempotency_key","created_at"], sql: "REFERENCES test_runs(run_id) CHECK (stage_number BETWEEN 1 AND 10) UNIQUE (run_id, stage_number, attempt) UNIQUE (run_id, idempotency_key)" },
  test_mode_release_events: { columns: ["event_id","authority","source_id","release_id","source_url","exam_code","exam_title","exam_year","event_fingerprint","payload_sha256","detected_at","verified_at","verification_status","verification_method","created_at"], sql: "CHECK (authority = 'PRC') CHECK (verification_status IN ('VERIFIED','REJECTED')) UNIQUE (event_fingerprint) CHECK (length(event_fingerprint) = 64) CHECK (length(payload_sha256) = 64)" },
  test_mode_publication_approvals: { columns: ["approval_id","run_id","action","status","approved_by_owner_uid","approved_at","approved_action_sha","artifact_manifest_sha256","target_ref","created_at"], sql: "REFERENCES test_runs(run_id) CHECK (action IN ('MERGE','PRODUCTION_DEPLOYMENT')) CHECK (status IN ('PENDING','APPROVED','INVALIDATED','CONSUMED'))" },
};
function makeDb() {
  const events = [];
  return { prepare(sql) {
    let values = [];
    const statement = {
      bind(...args) { values = args; return statement; },
      async first() {
        if (sql.includes("type = 'table'")) { const schema = schemas[values[0]]; return schema ? { name: values[0], sql: schema.sql } : null; }
        if (sql.includes("type = 'index'")) return { name: values[0], sql: "CREATE UNIQUE INDEX idx_test_runs_owner_idempotency" };
        if (sql.includes("SELECT event_id FROM test_mode_release_events")) return events.find((event) => event.event_fingerprint === values[0]) || null;
        return null;
      },
      async all() {
        if (sql.startsWith("PRAGMA table_info(")) { const name = sql.match(/PRAGMA table_info\(([^)]+)\)/)?.[1]; return { results: (schemas[name]?.columns || []).map((name) => ({ name })) }; }
        return { results: [] };
      },
      async run() {
        if (sql.includes("INSERT OR IGNORE INTO test_mode_release_events")) {
          const event = { event_id: values[0], authority: "PRC", source_id: values[1], release_id: values[2], source_url: values[3], exam_code: values[4], exam_title: values[5], exam_year: values[6], event_fingerprint: values[7], payload_sha256: values[8], detected_at: values[9], verified_at: values[10], verification_status: "VERIFIED", verification_method: values[11] };
          if (!events.some((item) => item.event_fingerprint === event.event_fingerprint)) {
            events.push(event);
            return { success: true, meta: { changes: 1 } };
          }
          return { success: true, meta: { changes: 0 } };
        }
        return { success: true, meta: { changes: 0 } };
      },
    };
    return statement;
  }, _events: events };
}
function env() { return { TEST_MODE_ENABLED: "true", TEST_MODE_ALLOWED_SOURCE_IDS: JSON.stringify(["prc-official-main"]), TEST_MODE_EVENT_INGEST_TOKEN: TOKEN, TEST_MODE_DB: makeDb() }; }
function request(body = SOURCE, token = TOKEN) { return new Request("https://example.pages.dev/api/test-mode/events", { method: "POST", headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" }, body: JSON.stringify(body) }); }

test("event ingestion requires the dedicated Watcher token", async () => {
  const environment = env();
  const response = await onRequestPost({ request: request(SOURCE, "wrong-token"), env: environment });
  assert.equal(response.status, 401);
  assert.equal(environment.TEST_MODE_DB._events.length, 0);
});
test("event ingestion rejects non-PRC, unapproved sources and non-official URLs", async () => {
  const environment = env();
  for (const body of [{ ...SOURCE, authority: "CSC" }, { ...SOURCE, source_id: "not-allowlisted" }, { ...SOURCE, article_url: "https://evil.example/results" }]) {
    const response = await onRequestPost({ request: request(body), env: environment });
    assert.ok([400, 403].includes(response.status));
  }
  assert.equal(environment.TEST_MODE_DB._events.length, 0);
});
test("genuine PRC metadata is stored with hashes and duplicate protection", async () => {
  const environment = env();
  const first = await onRequestPost({ request: request(), env: environment });
  const retry = { ...SOURCE, detected_at: new Date(Date.now() - 30_000).toISOString() };
  const second = await onRequestPost({ request: request(retry), env: environment });
  assert.equal(first.status, 201);
  assert.equal(second.status, 200);
  assert.equal(environment.TEST_MODE_DB._events.length, 1);
  const saved = environment.TEST_MODE_DB._events[0];
  assert.equal(saved.authority, "PRC");
  assert.equal(saved.verification_status, "VERIFIED");
  assert.match(saved.event_fingerprint, /^[a-f0-9]{64}$/);
  assert.match(saved.payload_sha256, /^[a-f0-9]{64}$/);
});
test("event ingestion fails closed when the dedicated database is unavailable", async () => {
  const environment = env(); delete environment.TEST_MODE_DB;
  const response = await onRequestPost({ request: request(), env: environment });
  assert.equal(response.status, 503);
});
