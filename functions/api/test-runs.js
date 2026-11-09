import { readSession, requireCsrf } from "../lib/access.js";
import {
  createTestRunId,
  createTestRunStepRows,
  getTestModeReadiness,
  validateTestModeSource,
} from "../lib/test-mode.js";

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

function validIdempotencyKey(value) {
  return typeof value === "string" && /^[A-Za-z0-9._:-]{8,128}$/.test(value);
}

async function readyDatabase(env) {
  const readiness = await getTestModeReadiness(env);
  return readiness.available ? env.TEST_MODE_DB : null;
}

export async function onRequestGet({ request, env }) {
  const session = await readSession(request, env);
  if (!session) return json({ error: "Owner authentication required." }, 401);
  const db = await readyDatabase(env);
  if (!db) return json({ error: "Test Mode run storage is not ready." }, 503);

  const url = new URL(request.url);
  const rawLimit = Number(url.searchParams.get("limit") || 25);
  const limit = Number.isInteger(rawLimit) ? Math.max(1, Math.min(50, rawLimit)) : 25;
  try {
    const result = await db.prepare(
      "SELECT run_id, mode, status, source_release_id, source_id, source_url, " +
      "started_at, completed_at, duration_ms, workflow_run_id, pull_request_number, " +
      "head_sha, merge_sha, deployment_id, deployment_url, report_sha256, created_at, updated_at " +
      "FROM test_runs WHERE requested_by_owner_uid = ? ORDER BY created_at DESC LIMIT ?"
    ).bind(session.firebase_uid, limit).all();
    return json({ runs: result.results || [] });
  } catch {
    return json({ error: "Test Mode run history is unavailable." }, 503);
  }
}

export async function onRequestPost({ request, env }) {
  const session = await readSession(request, env);
  if (!session) return json({ error: "Owner authentication required." }, 401);
  if (!(await requireCsrf(request, env))) return json({ error: "CSRF validation failed." }, 403);

  const db = await readyDatabase(env);
  if (!db) return json({ error: "Test Mode run storage is not ready." }, 503);

  const idempotencyKey = request.headers.get("Idempotency-Key") || "";
  if (!validIdempotencyKey(idempotencyKey)) {
    return json({ error: "A valid Idempotency-Key header is required." }, 400);
  }

  let body;
  try {
    const raw = await request.text();
    if (raw.length > 2048) return json({ error: "Request body is too large." }, 413);
    body = JSON.parse(raw);
  } catch {
    return json({ error: "A valid JSON request body is required." }, 400);
  }
  if (!body || typeof body !== "object" || Array.isArray(body) ||
      Object.keys(body).some((key) => key !== "event_id") ||
      typeof body.event_id !== "string" ||
      !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$/.test(body.event_id)) {
    return json({ error: "Only a verified event_id may be supplied." }, 400);
  }

  try {
    const existing = await db.prepare(
      "SELECT run_id, status, source_release_id, source_id, source_url, source_event_id, started_at " +
      "FROM test_runs WHERE requested_by_owner_uid = ? AND idempotency_key = ?"
    ).bind(session.firebase_uid, idempotencyKey).first();
    if (existing) {
      if (existing.source_event_id !== body.event_id) {
        return json({ error: "Idempotency-Key was already used for a different release event." }, 409);
      }
      return json({ run: existing, replayed: true }, 200);
    }

    const event = await db.prepare(
      "SELECT event_id, authority, source_id, release_id, source_url, exam_code, exam_title, " +
      "exam_year, event_fingerprint, payload_sha256, detected_at, verified_at, " +
      "verification_status, verification_method FROM test_mode_release_events WHERE event_id = ?"
    ).bind(body.event_id).first();

    if (!event || event.verification_status !== "VERIFIED") {
      return json({ error: "A verified Watcher release event was not found." }, 409);
    }

    const sourceCheck = validateTestModeSource({
      authority: event.authority,
      source_id: event.source_id,
      release_id: event.release_id,
      source_url: event.source_url,
    }, env);
    if (!sourceCheck.valid || event.authority !== "PRC" ||
        !event.event_fingerprint || !/^[a-f0-9]{64}$/i.test(event.payload_sha256 || "") ||
        !event.detected_at || !event.verified_at || !event.verification_method ||
        !event.exam_code || !event.exam_title ||
        !Number.isInteger(Number(event.exam_year)) ||
        Number(event.exam_year) < 2000 || Number(event.exam_year) > 2100 ||
        !Number.isFinite(Date.parse(event.detected_at)) ||
        !Number.isFinite(Date.parse(event.verified_at)) ||
        Date.parse(event.verified_at) < Date.parse(event.detected_at)) {
      return json({ error: "The release event failed Test Mode source verification." }, 409);
    }

    const runId = createTestRunId();
    const now = new Date().toISOString();
    const steps = createTestRunStepRows(runId);
    const statements = [
      db.prepare(
        "INSERT INTO test_runs (run_id, mode, status, requested_by_owner_uid, source_release_id, " +
        "source_id, source_url, source_event_id, idempotency_key, started_at, created_at, updated_at) " +
        "VALUES (?, 'REAL_WORLD', 'RUNNING', ?, ?, ?, ?, ?, ?, ?, ?, ?)"
      ).bind(runId, session.firebase_uid, event.release_id, event.source_id, event.source_url,
        event.event_id, idempotencyKey, now, now, now),
      ...steps.map((step) => db.prepare(
        "INSERT INTO test_run_steps (step_id, run_id, stage_number, attempt, status, idempotency_key) " +
        "VALUES (?, ?, ?, ?, 'NOT RUN', ?)"
      ).bind(step.step_id, runId, step.stage_number, step.attempt, step.idempotency_key)),
    ];

    try {
      await db.batch(statements);
    } catch {
      const raced = await db.prepare(
        "SELECT run_id, status, source_release_id, source_id, source_url, source_event_id, started_at " +
        "FROM test_runs WHERE requested_by_owner_uid = ? AND idempotency_key = ?"
      ).bind(session.firebase_uid, idempotencyKey).first();
      if (raced && raced.source_event_id === body.event_id) {
        return json({ run: raced, replayed: true }, 200);
      }
      if (raced) return json({ error: "Idempotency-Key was already used for a different release event." }, 409);
      return json({ error: "The Test Mode run could not be created safely." }, 409);
    }

    return json({
      run: {
        run_id: runId,
        mode: "REAL_WORLD",
        status: "RUNNING",
        source_release_id: event.release_id,
        source_id: event.source_id,
        source_url: event.source_url,
        source_event_id: event.event_id,
        started_at: now,
      },
      stages_created: steps.length,
      replayed: false,
    }, 201);
  } catch {
    return json({ error: "Test Mode run creation is temporarily unavailable." }, 503);
  }
}
