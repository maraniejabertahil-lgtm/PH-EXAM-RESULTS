import test from "node:test";
import assert from "node:assert/strict";
import { onRequestGet } from "../api/test-mode/config.js";
import { signSession, COOKIE_NAMES } from "../lib/access.js";
import {
  getTestModeReadiness,
  TEST_MODE_STAGES,
  validateTestModeSource,
} from "../lib/test-mode.js";

const baseEnv = {
  TEST_MODE_ENABLED: "true",
  TEST_MODE_ALLOWED_SOURCE_IDS: JSON.stringify(["prc-official-main"]),
};

function readyDb() {
  const schemas = {
    test_runs: {
      columns: ["run_id", "mode", "status", "requested_by_owner_uid", "source_release_id",
        "source_id", "source_url", "started_at", "completed_at", "duration_ms",
        "workflow_run_id", "pull_request_number", "head_sha", "merge_sha",
        "deployment_id", "deployment_url", "report_sha256", "created_at", "updated_at"],
      sql: "CHECK (mode = 'REAL_WORLD') CHECK (status IN ('RUNNING','PASS','FAIL','BLOCKED','COMPLETED'))",
    },
    test_run_steps: {
      columns: ["step_id", "run_id", "stage_number", "attempt", "status", "started_at",
        "completed_at", "duration_ms", "expected_summary", "actual_summary", "evidence_json",
        "failure_code", "failure_message_redacted", "idempotency_key", "created_at"],
      sql: "REFERENCES test_runs(run_id) CHECK (stage_number BETWEEN 1 AND 10) UNIQUE (run_id, stage_number, attempt) UNIQUE (run_id, idempotency_key)",
    },
    test_mode_publication_approvals: {
      columns: ["approval_id", "run_id", "action", "status", "approved_by_owner_uid",
        "approved_at", "approved_action_sha", "artifact_manifest_sha256", "target_ref", "created_at"],
      sql: "REFERENCES test_runs(run_id) CHECK (action IN ('MERGE','PRODUCTION_DEPLOYMENT')) CHECK (status IN ('PENDING','APPROVED','INVALIDATED','CONSUMED'))",
    },
  };
  return {
    prepare(sql) {
      return {
        bind(name) {
          return {
            async first() {
              const schema = schemas[name];
              return schema ? { name, sql: schema.sql } : null;
            },
          };
        },
        async all() {
          const table = sql.match(/PRAGMA table_info\\(([^)]+)\\)/)?.[1];
          return { results: (schemas[table]?.columns || []).map((name) => ({ name })) };
        },
      };
    },
  };
}

async function ownerRequest(envOverrides = {}) {
  const env = {
    ...baseEnv,
    OWNER_EMAIL: "owner@example.com",
    SESSION_SIGNING_KEY: "s".repeat(40),
    TEST_MODE_DB: readyDb(),
    ...envOverrides,
  };
  const now = Math.floor(Date.now() / 1000);
  const token = await signSession({
    firebase_uid: "owner-uid",
    firebase_email: "owner@example.com",
    firebase_role: "owner",
    csrf: "c".repeat(40),
    iat: now,
    exp: now + 300,
  }, env.SESSION_SIGNING_KEY);
  const request = new Request("https://example.pages.dev/api/test-mode/config", {
    headers: { Cookie: `${COOKIE_NAMES.session}=${token}` },
  });
  return { request, env };
}

test("Test Mode has exactly ten ordered real-world stages", () => {
  assert.equal(TEST_MODE_STAGES.length, 10);
  assert.deepEqual(TEST_MODE_STAGES.map((stage) => stage.number),
    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
});

test("source validation accepts only explicitly allowlisted PRC official HTTPS hosts", () => {
  const result = validateTestModeSource({
    authority: "PRC",
    source_id: "prc-official-main",
    release_id: "LEPT-2026-03",
    source_url: "https://www.prc.gov.ph/examination-results",
  }, baseEnv);
  assert.equal(result.valid, true);
  assert.deepEqual(result.reasons, []);
});

test("source validation rejects non-PRC authorities, unknown sources and arbitrary hosts", () => {
  const result = validateTestModeSource({
    authority: "CSC",
    source_id: "unknown-source",
    release_id: "LEPT-2026",
    source_url: "https://attacker.example/results",
  }, baseEnv);
  assert.equal(result.valid, false);
  assert.ok(result.reasons.includes("SOURCE_NOT_ALLOWLISTED"));
  assert.ok(result.reasons.includes("AUTHORITY_NOT_ALLOWED"));
  assert.ok(result.reasons.includes("SOURCE_URL_NOT_APPROVED_PRC_HOST"));
});

test("source validation rejects insecure URLs and credential-bearing URLs", () => {
  for (const sourceUrl of [
    "http://www.prc.gov.ph/results",
    "https://user:password@www.prc.gov.ph/results",
    "https://www.prc.gov.ph.evil.example/results",
  ]) {
    const result = validateTestModeSource({
      authority: "PRC",
      source_id: "prc-official-main",
      release_id: "LEPT-2026",
      source_url: sourceUrl,
    }, baseEnv);
    assert.equal(result.valid, false, sourceUrl);
  }
});

test("readiness fails closed when Test Mode is disabled or its isolated DB is missing", async () => {
  const disabled = await getTestModeReadiness({
    ...baseEnv,
    TEST_MODE_ENABLED: "false",
    TEST_MODE_DB: readyDb(),
  });
  assert.equal(disabled.available, false);
  assert.ok(disabled.reasons.includes("TEST_MODE_NOT_ENABLED"));

  const noDb = await getTestModeReadiness(baseEnv);
  assert.equal(noDb.available, false);
  assert.ok(noDb.reasons.includes("TEST_MODE_DATABASE_NOT_BOUND"));
});

test("readiness fails closed when an audit table is missing required columns or constraints", async () => {
  const incompleteDb = {
    prepare(sql) {
      return {
        bind(name) {
          return { first: async () => ({ name, sql: "CREATE TABLE " + name + " (id TEXT)" }) };
        },
        all: async () => ({ results: [{ name: "id" }] }),
      };
    },
  };
  const readiness = await getTestModeReadiness({
    ...baseEnv,
    TEST_MODE_DB: incompleteDb,
  });
  assert.equal(readiness.available, false);
  assert.ok(readiness.reasons.includes("TEST_MODE_SCHEMA_INCOMPLETE"));
});

test("authenticated readiness reports the isolated configuration without production fallback", async () => {
  const { request, env } = await ownerRequest();
  const response = await onRequestGet({ request, env });
  const payload = await response.json();
  assert.equal(response.status, 200);
  assert.equal(payload.available, true);
  assert.equal(payload.mode, "REAL_WORLD");
  assert.equal(payload.stages.length, 10);
  assert.equal(payload.publication_gates.merge_requires_owner_approval, true);
  assert.equal(payload.publication_gates.production_deployment_requires_separate_owner_approval, true);
});

test("readiness endpoint rejects unauthenticated requests", async () => {
  const response = await onRequestGet({
    request: new Request("https://example.pages.dev/api/test-mode/config"),
    env: { ...baseEnv, TEST_MODE_DB: readyDb() },
  });
  assert.equal(response.status, 401);
  assert.deepEqual(await response.json(), { error: "Owner authentication required." });
});
