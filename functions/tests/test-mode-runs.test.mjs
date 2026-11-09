import test from "node:test";
import assert from "node:assert/strict";
import { onRequestGet as listRuns, onRequestPost as createRun } from "../api/test-runs.js";
import { onRequestGet as getRun } from "../api/test-runs/[runId].js";
import { signSession, COOKIE_NAMES } from "../lib/access.js";

const OWNER_EMAIL = "owner@example.com";
const SIGNING_KEY = "s".repeat(40);
const CSRF = "c".repeat(40);
const SOURCE_EVENT = {
  event_id: "watcher-prc-2026-001",
  authority: "PRC",
  source_id: "prc-official-main",
  release_id: "LEPT-2026-03",
  source_url: "https://www.prc.gov.ph/examination-results",
  exam_code: "LEPT",
  exam_title: "Licensure Examination for Professional Teachers",
  exam_year: 2026,
  event_fingerprint: "b".repeat(64),
  payload_sha256: "a".repeat(64),
  detected_at: "2026-11-09T00:00:00.000Z",
  verified_at: "2026-11-09T00:01:00.000Z",
  verification_status: "VERIFIED",
  verification_method: "watcher-contract-v1",
};

const tableSchemas = {
  test_runs: {
    columns: ["run_id", "mode", "status", "requested_by_owner_uid", "source_release_id", "source_id",
      "source_url", "started_at", "completed_at", "duration_ms", "workflow_run_id", "pull_request_number",
      "head_sha", "merge_sha", "deployment_id", "deployment_url", "report_sha256", "source_event_id",
      "idempotency_key", "created_at", "updated_at"],
    sql: "CHECK (mode = 'REAL_WORLD') CHECK (status IN ('RUNNING','PASS','FAIL','BLOCKED','COMPLETED'))",
  },
  test_run_steps: {
    columns: ["step_id", "run_id", "stage_number", "attempt", "status", "started_at", "completed_at",
      "duration_ms", "expected_summary", "actual_summary", "evidence_json", "failure_code",
      "failure_message_redacted", "idempotency_key", "created_at"],
    sql: "REFERENCES test_runs(run_id) CHECK (stage_number BETWEEN 1 AND 10) UNIQUE (run_id, stage_number, attempt) UNIQUE (run_id, idempotency_key)",
  },
  test_mode_publication_approvals: {
    columns: ["approval_id", "run_id", "action", "status", "approved_by_owner_uid", "approved_at",
      "approved_action_sha", "artifact_manifest_sha256", "target_ref", "created_at"],
    sql: "REFERENCES test_runs(run_id) CHECK (action IN ('MERGE','PRODUCTION_DEPLOYMENT')) CHECK (status IN ('PENDING','APPROVED','INVALIDATED','CONSUMED'))",
  },
  test_mode_release_events: {
    columns: ["event_id", "authority", "source_id", "release_id", "source_url", "exam_code", "exam_title",
      "exam_year", "event_fingerprint", "payload_sha256", "detected_at", "verified_at",
      "verification_status", "verification_method", "created_at"],
    sql: "CHECK (authority = 'PRC') CHECK (verification_status IN ('VERIFIED','REJECTED')) UNIQUE (event_fingerprint) CHECK (length(event_fingerprint) = 64) CHECK (length(payload_sha256) = 64)",
  },
};

function makeDb(event = SOURCE_EVENT) {
  const runs = [];
  const steps = [];
  const events = event ? [event] : [];
  const db = {
    prepare(sql) {
      let values = [];
      const statement = {
        sql,
        bind(...args) { values = args; return statement; },
        async first() {
          if (sql.includes("type = 'table'")) {
            const name = values[0], schema = tableSchemas[name];
            return schema ? { name, sql: schema.sql } : null;
          }
          if (sql.includes("type = 'index'")) {
            return { name: values[0], sql: "CREATE UNIQUE INDEX idx_test_runs_owner_idempotency" };
          }
          if (sql.includes("FROM test_mode_release_events")) {
            return events.find((item) => item.event_id === values[0]) || null;
          }
          if (sql.includes("FROM test_runs") && sql.includes("idempotency_key")) {
            return runs.find((item) => item.requested_by_owner_uid === values[0] &&
              item.idempotency_key === values[1]) || null;
          }
          if (sql.includes("FROM test_runs") && sql.includes("run_id = ?")) {
            return runs.find((item) => item.run_id === values[0] &&
              item.requested_by_owner_uid === values[1]) || null;
          }
          return null;
        },
        async all() {
          if (sql.startsWith("PRAGMA table_info(")) {
            const name = sql.match(/PRAGMA table_info\(([^)]+)\)/)?.[1];
            return { results: (tableSchemas[name]?.columns || []).map((name) => ({ name })) };
          }
          if (sql.includes("FROM test_runs")) {
            return { results: runs.filter((item) => item.requested_by_owner_uid === values[0])
              .slice(0, Number(values[1])) };
          }
          if (sql.includes("FROM test_run_steps")) {
            return { results: steps.filter((item) => item.run_id === values[0])
              .sort((a, b) => a.stage_number - b.stage_number) };
          }
          return { results: [] };
        },
        async run() {
          if (sql.includes("INSERT INTO test_runs")) {
            if (runs.some((item) => item.requested_by_owner_uid === values[1] &&
                item.idempotency_key === values[6])) throw new Error("UNIQUE constraint failed");
            runs.push({
              run_id: values[0], mode: "REAL_WORLD", status: "RUNNING",
              requested_by_owner_uid: values[1], source_release_id: values[2],
              source_id: values[3], source_url: values[4], source_event_id: values[5],
              idempotency_key: values[6], started_at: values[7], created_at: values[8],
              updated_at: values[9],
            });
          } else if (sql.includes("INSERT INTO test_run_steps")) {
            steps.push({
              step_id: values[0], run_id: values[1], stage_number: values[2],
              attempt: values[3], status: "NOT RUN", idempotency_key: values[4],
            });
          }
          return { success: true };
        },
      };
      return statement;
    },
    async batch(statements) {
      const runCount = runs.length, stepCount = steps.length;
      try {
        for (const statement of statements) await statement.run();
      } catch (error) {
        runs.length = runCount;
        steps.length = stepCount;
        throw error;
      }
      return statements.map(() => ({ success: true }));
    },
    _runs: runs,
    _steps: steps,
    _events: events,
  };
  return db;
}

async function ownerEnv(uid = "owner-uid", event = SOURCE_EVENT) {
  const env = {
    TEST_MODE_ENABLED: "true",
    TEST_MODE_ALLOWED_SOURCE_IDS: JSON.stringify(["prc-official-main"]),
    TEST_MODE_DB: makeDb(event),
    OWNER_EMAIL,
    SESSION_SIGNING_KEY: SIGNING_KEY,
  };
  const now = Math.floor(Date.now() / 1000);
  const token = await signSession({
    firebase_uid: uid, firebase_email: OWNER_EMAIL, firebase_role: "owner",
    csrf: CSRF, iat: now, exp: now + 300,
  }, SIGNING_KEY);
  return { env, cookie: COOKIE_NAMES.session + "=" + token };
}

function postRequest(cookie, options = {}) {
  const csrf = options.csrf === undefined ? CSRF : options.csrf;
  const key = options.key === undefined ? "test-run-key-0001" : options.key;
  const body = options.body === undefined ? { event_id: SOURCE_EVENT.event_id } : options.body;
  const headers = {
    Cookie: cookie,
    Origin: "https://example.pages.dev",
    "Content-Type": "application/json",
    "Idempotency-Key": key,
  };
  if (csrf !== null) headers["X-CSRF-Token"] = csrf;
  return new Request("https://example.pages.dev/api/test-runs", {
    method: "POST", headers, body: JSON.stringify(body),
  });
}

test("run creation requires Owner authentication and CSRF", async () => {
  const { env, cookie } = await ownerEnv();
  const unauth = await createRun({ request: postRequest(""), env });
  assert.equal(unauth.status, 401);
  const noCsrf = await createRun({ request: postRequest(cookie, { csrf: "wrong-token" }), env });
  assert.equal(noCsrf.status, 403);
});

test("run creation rejects unverified Watcher events", async () => {
  const rejectedEvent = { ...SOURCE_EVENT, verification_status: "REJECTED" };
  const { env, cookie } = await ownerEnv("owner-uid", rejectedEvent);
  const response = await createRun({ request: postRequest(cookie), env });
  assert.equal(response.status, 409);
});

test("run creation accepts only a verified allowlisted PRC event and creates ten NOT RUN stages", async () => {
  const { env, cookie } = await ownerEnv();
  const response = await createRun({ request: postRequest(cookie), env });
  const payload = await response.json();
  assert.equal(response.status, 201);
  assert.equal(payload.stages_created, 10);
  assert.equal(env.TEST_MODE_DB._runs.length, 1);
  assert.equal(env.TEST_MODE_DB._steps.length, 10);
  assert.ok(env.TEST_MODE_DB._steps.every((step) => step.status === "NOT RUN"));
  assert.deepEqual(env.TEST_MODE_DB._steps.map((step) => step.stage_number), [1,2,3,4,5,6,7,8,9,10]);
});

test("same Owner idempotency key returns the existing run without creating duplicates", async () => {
  const { env, cookie } = await ownerEnv();
  const first = await createRun({ request: postRequest(cookie), env });
  const firstPayload = await first.json();
  const second = await createRun({ request: postRequest(cookie), env });
  const secondPayload = await second.json();
  assert.equal(first.status, 201);
  assert.equal(second.status, 200);
  assert.equal(secondPayload.replayed, true);
  assert.equal(secondPayload.run.run_id, firstPayload.run.run_id);
  assert.equal(env.TEST_MODE_DB._runs.length, 1);
  assert.equal(env.TEST_MODE_DB._steps.length, 10);
});

test("same idempotency key cannot be replayed for a different event", async () => {
  const { env, cookie } = await ownerEnv();
  await createRun({ request: postRequest(cookie), env });
  const replay = await createRun({
    request: postRequest(cookie, {
      key: "test-run-key-0001",
      body: { event_id: "different-watcher-event" },
    }),
    env,
  });
  assert.equal(replay.status, 409);
});

test("browser cannot provide arbitrary source URLs or release metadata", async () => {
  const { env, cookie } = await ownerEnv();
  const response = await createRun({
    request: postRequest(cookie, {
      body: { event_id: SOURCE_EVENT.event_id, source_url: "https://evil.example" },
    }),
    env,
  });
  assert.equal(response.status, 400);
});

test("run history and detail are scoped to the authenticated Owner UID", async () => {
  const firstOwner = await ownerEnv("owner-uid");
  const created = await createRun({ request: postRequest(firstOwner.cookie), env: firstOwner.env });
  const payload = await created.json();
  const list = await listRuns({
    request: new Request("https://example.pages.dev/api/test-runs", {
      headers: { Cookie: firstOwner.cookie },
    }),
    env: firstOwner.env,
  });
  assert.equal((await list.json()).runs.length, 1);

  const otherOwner = await ownerEnv("other-owner");
  otherOwner.env.TEST_MODE_DB = firstOwner.env.TEST_MODE_DB;
  const detail = await getRun({
    request: new Request("https://example.pages.dev/api/test-runs/" + payload.run.run_id, {
      headers: { Cookie: otherOwner.cookie },
    }),
    params: { runId: payload.run.run_id },
    env: otherOwner.env,
  });
  assert.equal(detail.status, 404);
});

test("invalid idempotency keys and unknown events fail closed", async () => {
  const { env, cookie } = await ownerEnv();
  const invalidKey = await createRun({ request: postRequest(cookie, { key: "x" }), env });
  assert.equal(invalidKey.status, 400);
  const unknown = await createRun({
    request: postRequest(cookie, {
      body: { event_id: "watcher-event-not-present" },
      key: "test-run-key-0002",
    }),
    env,
  });
  assert.equal(unknown.status, 409);
});
