import { readSession } from "../../lib/access.js";
import { getTestModeReadiness } from "../../lib/test-mode.js";

function json(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store, private",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

export async function onRequestGet({ request, env, params }) {
  const session = await readSession(request, env);
  if (!session) return json({ error: "Owner authentication required." }, 401);

  const runId = typeof params?.runId === "string" ? params.runId : "";
  if (!/^tmr_[0-9a-f-]{36}$/i.test(runId)) return json({ error: "Invalid run ID." }, 400);

  const readiness = await getTestModeReadiness(env);
  if (!readiness.available) return json({ error: "Test Mode run storage is not ready." }, 503);

  try {
    const run = await env.TEST_MODE_DB.prepare(
      "SELECT run_id, mode, status, source_release_id, source_id, source_url, source_event_id, " +
      "started_at, completed_at, duration_ms, workflow_run_id, pull_request_number, head_sha, " +
      "merge_sha, deployment_id, deployment_url, report_sha256, created_at, updated_at " +
      "FROM test_runs WHERE run_id = ? AND requested_by_owner_uid = ?"
    ).bind(runId, session.firebase_uid).first();
    if (!run) return json({ error: "Test Mode run not found." }, 404);

    const result = await env.TEST_MODE_DB.prepare(
      "SELECT step_id, run_id, stage_number, attempt, status, started_at, completed_at, " +
      "duration_ms, expected_summary, actual_summary, failure_code, failure_message_redacted, " +
      "idempotency_key, created_at FROM test_run_steps WHERE run_id = ? ORDER BY stage_number, attempt"
    ).bind(runId).all();
    return json({ run, steps: result.results || [] });
  } catch {
    return json({ error: "Test Mode run details are unavailable." }, 503);
  }
}
