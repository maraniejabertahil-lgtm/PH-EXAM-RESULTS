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

const REQUIRED_AUDIT_TABLES = [
  "test_runs",
  "test_run_steps",
  "test_mode_publication_approvals",
];

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
    reasons.push("SOURCE_URL_NOT_APPROVED_PRCC_HOST");
  }

  return { valid: reasons.length === 0, reasons };
}

export async function getTestModeReadiness(env) {
  const reasons = [];
  if (env.TEST_MODE_ENABLED !== "true") reasons.push("TEST_MODE_NOT_ENABLED");

  const sourceIds = allowedSourceIds(env);
  if (sourceIds.length === 0) reasons.push("NO_PR C_SOURCE_ALLOWLIST".replace(" ", ""));

  const db = env.TEST_MODE_DB;
  if (!db || typeof db.prepare !== "function") {
    reasons.push("TEST_MODE_DATABASE_NOT_BOUND");
  } else {
    try {
      for (const table of REQUIRED_AUDIT_TABLES) {
        const row = await db.prepare(
          "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?"
        ).bind(table).first();
        if (!row || row.name !== table) reasons.push("TEST_MODE_SCHEMA_INCOMPLETE");
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
