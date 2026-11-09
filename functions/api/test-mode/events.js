import {
  getTestModeReadiness,
  isTestModeEventIngestAuthorized,
  validateTestModeSource,
} from "../../lib/test-mode.js";

function json(value, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store, private",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
  }});
}
async function sha256Hex(value) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}
function validEvent(body) {
  return body && typeof body === "object" && !Array.isArray(body) &&
    Object.keys(body).every((key) => ["authority","source_id","article_url","exam_code","exam_title","exam_year","detected_at"].includes(key)) &&
    body.authority === "PRC" && typeof body.source_id === "string" &&
    typeof body.article_url === "string" && /^[A-Z0-9_-]{2,24}$/.test(body.exam_code || "") &&
    typeof body.exam_title === "string" && body.exam_title.trim().length >= 8 &&
    body.exam_title.trim().length <= 240 && Number.isInteger(body.exam_year) &&
    body.exam_year >= 2000 && body.exam_year <= 2100 &&
    typeof body.detected_at === "string" && Number.isFinite(Date.parse(body.detected_at));
}
export async function onRequestPost({ request, env }) {
  if (request.method !== "POST") return json({ error: "Method not allowed." }, 405);
  if (!isTestModeEventIngestAuthorized(request, env)) return json({ error: "Watcher authentication required." }, 401);
  const readiness = await getTestModeReadiness(env);
  if (!readiness.available) return json({ error: "Test Mode event storage is not ready.", reasons: readiness.reasons }, 503);
  let raw, body;
  try {
    raw = await request.text();
    if (raw.length > 4096) return json({ error: "Request body is too large." }, 413);
    body = JSON.parse(raw);
  } catch { return json({ error: "A valid JSON event is required." }, 400); }
  if (!validEvent(body)) return json({ error: "The PRC release event is malformed." }, 400);
  const sourceCheck = validateTestModeSource({
    authority: body.authority, source_id: body.source_id,
    release_id: body.source_id + ":" + body.exam_code + ":" + body.exam_year,
    source_url: body.article_url,
  }, env);
  if (!sourceCheck.valid) return json({ error: "The PRC source is not approved for Test Mode.", reasons: sourceCheck.reasons }, 403);
  const detectedAt = Date.parse(body.detected_at);
  if (detectedAt > Date.now() + 5 * 60 * 1000) return json({ error: "The detection timestamp is in the future." }, 400);
  try {
    const articleUrl = new URL(body.article_url).href;
    const canonical = JSON.stringify({
      authority: "PRC", source_id: body.source_id, article_url: articleUrl,
      exam_code: body.exam_code, exam_title: body.exam_title.trim(),
      exam_year: body.exam_year, detected_at: new Date(detectedAt).toISOString(),
    });
    const fingerprint = await sha256Hex(canonical);
    const payloadHash = await sha256Hex(raw);
    const eventId = "prc_" + fingerprint.slice(0, 32);
    const releaseId = body.source_id + ":" + body.exam_code + ":" + body.exam_year + ":" + fingerprint.slice(0, 16);
    const verifiedAt = new Date().toISOString();
    const db = env.TEST_MODE_DB;
    const inserted = await db.prepare(
      "INSERT OR IGNORE INTO test_mode_release_events " +
      "(event_id, authority, source_id, release_id, source_url, exam_code, exam_title, exam_year, " +
      "event_fingerprint, payload_sha256, detected_at, verified_at, verification_status, verification_method) " +
      "VALUES (?, 'PRC', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'VERIFIED', ?)"
    ).bind(eventId, body.source_id, releaseId, articleUrl, body.exam_code, body.exam_title.trim(),
      body.exam_year, fingerprint, payloadHash, new Date(detectedAt).toISOString(), verifiedAt,
      "watcher-shared-token+official-prc-metadata-v1").run();
    const saved = await db.prepare(
      "SELECT event_id FROM test_mode_release_events WHERE event_fingerprint = ?"
    ).bind(fingerprint).first();
    if (!saved) return json({ error: "The Test Mode event could not be confirmed in storage." }, 503);
    const duplicate = inserted?.meta?.changes === 0;
    return json({ event_id: saved.event_id, duplicate }, duplicate ? 200 : 201);
  } catch { return json({ error: "Test Mode event storage is temporarily unavailable." }, 503); }
}
