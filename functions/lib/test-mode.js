export const TEST_MODE_STAGES = Object.freeze([
  { number: 1, id: "release-detection", name: "Release Detection" },
  { number: 2, id: "webhook-dispatch", name: "Webhook Dispatch" },
  { number: 3, id: "event-verification", name: "Event Verification" },
  { number: 4, id: "content-acquisition", name: "Content Acquisition" },
  { number: 5, id: "data-extraction", name: "Data Extraction" },
  { number: 6, id: "data-normalization", name: "Data Normalization" },
  { number: 7, id: "greenlight-validation", name: "Greenlight Validation" },
  { number: 8, id: "dataset-gitops-pr", name: "Dataset & GitOps PR" },
  { number: 9, id: "ci-verification-merge", name: "CI Verification & Merge" },
  { number: 10, id: "website-deployment", name: "Website Deployment" },
]);

const REQUIRED_AUDIT_SCHEMA = {
  test_runs: {
    columns: ["run_id", "mode", "status", "requested_by_owner_uid", "source_release_id",
      "source_id", "source_url", "started_at", "completed_at", "duration_ms",
      "workflow_run_id", "pull_request_number", "head_sha", "merge_sha",
      "deployment_id", "deployment_url", "report_sha256", "created_at", "updated_at"],
    sql: ["CHECK (mode = 'REAL_WORLD')", "CHECK (status IN ('RUNNING','PASS','FAIL','BLOCKED','COMPLETED'))"],
  },
  test_run_steps: {
    columns: ["step_id", "run_id", "stage_number", "attempt", "status", "started_at",
      "completed_at", "duration_ms", "expected_summary", "actual_summary", "evidence_json",
      "failure_code", "failure_message_redacted", "idempotency_key", "created_at"],
    sql: ["REFERENCES test_runs(run_id)", "CHECK (stage_number BETWEEN 1 AND 10)",
      "UNIQUE (run_id, stage_number, attempt)", "UNIQUE (run_id, idempotency_key)"],
  },
  test_mode_publication_approvals: {
    columns: ["approval_id", "run_id", "action", "status", "approved_by_owner_uid",
      "approved_at", "approved_action_sha", "artifact_manifest_sha256", "target_ref", "created_at"],
    sql: ["REFERENCES test_runs(run_id)", "CHECK (action IN ('MERGE','PRODUCTION_DEPLOYMENT'))",
      "CHECK (status IN ('PENDING','APPROVED','INVALIDATED','CONSUMED'))"],
  },
};

function allowedSourceIds(env) {
  if (typeof env.TEST_MODE_ALLOWED_SOURCE_IDS !== "string") return [];
  try {
    const parsed = JSON.parse(env.TEST_MODE_ALLOWED_SOURCE_IDS);
    if (!Array.isArray(parsed)) return [];
    return [...new Set(parsed.filter((value) =>
      typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9_-]{0,59}$/.test(value)
    ))];
  } catch {
    return [];
  }
}

export function validateTestModeSource(input, env) {
  const reasons = [];
  if (!input || typeof input !== "object") {
    return { valid: false, reasons: ["INVALID_SOURCE_DESCRIPTOR"] };
  }

  const sourceId = typeof input.source_id === "string" ? input.source_id : "";
  const allowed = allowedSourceIds(env);
  if (!sourceId || !allowed.includes(sourceId)) reasons.push("SOURCE_NOT_ALLOWLISTED");
  if (input.authority !== "PRC") reasons.push("AUTHORITY_NOT_ALLOWED");

  const releaseId = typeof input.release_id === "string" ? input.release_id : "";
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$/.test(releaseId)) {
    reasons.push("INVALID_RELEASE_ID");
  }

  let parsed;
  try {
    parsed = new URL(input.source_url);
  } catch {
    parsed = null;
  }
  const host = parsed?.hostname.toLowerCase() || "";
  const officialHost = host === "prc.gov.ph" || host.endsWith(".prc.gov.ph");
  if (!parsed || parsed.protocol !== "https:" || !officialHost ||
      parsed.username || parsed.password || parsed.port && parsed.port !== "443" ||
      parsed.hash) {
    reasons.push("SOURCE_URL_NOT_APPROVED_PRC_HOST");
  }

  return { valid: reasons.length === 0, reasons };
}

export async function getTestModeReadiness(env) {
  const reasons = [];
  if (env.TEST_MODE_ENABLED !== "true") reasons.push("TEST_MODE_NOT_ENABLED");

  const sourceIds = allowedSourceIds(env);
  if (sourceIds.length === 0) reasons.push("NO_PRC_SOURCE_ALLOWLIST");

  const db = env.TEST_MODE_DB;
  if (!db || typeof db.prepare !== "function") {
    reasons.push("TEST_MODE_DATABASE_NOT_BOUND");
  } else {
    try {
      for (const [table, expected] of Object.entries(REQUIRED_AUDIT_SCHEMA)) {
        const row = await db.prepare(
          "SELECT name, sql FROM sqlite_master WHERE type = 'table' AND name = ?"
        ).bind(table).first();
        if (!row || row.name !== table || typeof row.sql !== "string") {
          reasons.push("TEST_MODE_SCHEMA_INCOMPLETE");
          continue;
        }
        const definition = row.sql.replace(/\s+/g, " ").toLowerCase();
        if (!expected.sql.every((fragment) => definition.includes(fragment.toLowerCase()))) {
          reasons.push("TEST_MODE_SCHEMA_INCOMPLETE");
          continue;
        }
        const columns = await db.prepare("PRAGMA table_info(" + table + ")").all();
        const names = columns?.results?.map((column) => column.name) || [];
        if (!expected.columns.every((column) => names.includes(column))) {
          reasons.push("TEST_MODE_SCHEMA_INCOMPLETE");
        }
      }
    } catch {
      reasons.push("TEST_MODE_DATABASE_UNAVAILABLE");
    }
  }

  return {
    available: reasons.length === 0,
    status: reasons.length === 0 ? "READY" : "BLOCKED",
    reasons: [...new Set(reasons)],
    mode: "REAL_WORLD",
    stages: TEST_MODE_STAGES,
    publication_gates: {
      merge_requires_owner_approval: true,
      production_deployment_requires_separate_owner_approval: true,
    },
  };
}
