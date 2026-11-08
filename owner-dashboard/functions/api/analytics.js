import { isOwnerAccessRequest } from "../lib/access.js";

const API_ROOT = "https://api.cloudflare.com/client/v4";
const json = (value, status = 200) => new Response(JSON.stringify(value), {
  status,
  headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff" },
});

async function queryD1(env, sql, params = []) {
  const response = await fetch(API_ROOT + "/accounts/" + encodeURIComponent(env.CF_ACCOUNT_ID) +
    "/d1/database/" + encodeURIComponent(env.CF_D1_DATABASE_ID) + "/query", {
    method: "POST",
    headers: { Authorization: "Bearer " + env.CF_D1_READ_API_TOKEN, "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ sql, params }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload?.success !== true || payload.result?.some((item) => item?.success === false)) {
    throw new Error("D1 analytics query failed.");
  }
  const rows = payload.result?.[0]?.results;
  if (!Array.isArray(rows)) throw new Error("D1 analytics response is invalid.");
  return rows;
}

export async function onRequestGet({ request, env }) {
  if (!(await isOwnerAccessRequest(request, env))) return json({ error: "Owner authentication required." }, 401);
  if (!env.CF_D1_READ_API_TOKEN || !env.CF_ACCOUNT_ID || !env.CF_D1_DATABASE_ID) {
    return json({ error: "Private analytics storage is not configured." }, 503);
  }
  const url = new URL(request.url);
  const requested = Number(url.searchParams.get("days") || 30);
  const days = [7, 30, 90].includes(requested) ? requested : 30;
  const window = "-" + days + " days";
  try {
    const [daily, batches, predictions, latestWatcher] = await Promise.all([
      queryD1(env,
        "SELECT substr(COALESCE(occurred_at,created_at),1,10) AS day, COUNT(*) AS events, " +
        "SUM(CASE WHEN event_type='watcher_scan' THEN 1 ELSE 0 END) AS watcher_scans, " +
        "SUM(CASE WHEN event_type='release_detected' THEN 1 ELSE 0 END) AS releases, " +
        "SUM(CASE WHEN event_type IN ('processing_started','greenlight_passed','greenlight_failed') THEN 1 ELSE 0 END) AS extraction_events, " +
        "SUM(CASE WHEN event_type IN ('publication_completed','publication_failed') THEN 1 ELSE 0 END) AS publication_events " +
        "FROM monitoring_logs WHERE datetime(COALESCE(occurred_at,created_at)) >= datetime('now', ?) " +
        "GROUP BY substr(COALESCE(occurred_at,created_at),1,10) ORDER BY day ASC", [window]),
      queryD1(env,
        "SELECT substr(COALESCE(completed_at,started_at,updated_at,created_at),1,10) AS day, COUNT(*) AS batches, " +
        "SUM(CASE WHEN status='published' THEN 1 ELSE 0 END) AS published, " +
        "SUM(CASE WHEN status IN ('greenlight_passed','published') THEN COALESCE(record_count,extracted_count,0) ELSE 0 END) AS validated_records " +
        "FROM import_batches WHERE datetime(COALESCE(completed_at,started_at,updated_at,created_at)) >= datetime(?) " +
        "GROUP BY substr(COALESCE(completed_at,started_at,updated_at,created_at),1,10) ORDER BY day ASC", [new Date(Date.now() - days * 86400000).toISOString()]),
      queryD1(env, "SELECT COUNT(*) AS active, MIN(predicted_release_date) AS next_release FROM release_predictions WHERE status='active' AND date(predicted_release_date)>=date('now')"),
      queryD1(env, "SELECT COALESCE(occurred_at,created_at) AS occurred_at FROM monitoring_logs WHERE event_type='watcher_scan' ORDER BY COALESCE(occurred_at,created_at) DESC LIMIT 1"),
    ]);
    const latest = latestWatcher[0]?.occurred_at || null;
    const age = latest ? Date.now() - Date.parse(latest) : Infinity;
    return json({
      days, generated_at: new Date().toISOString(), daily, batches,
      predictions: predictions[0] || { active: 0, next_release: null },
      monitor: { last_watcher_scan: latest, status: age <= 10 * 60 * 1000 ? "active" : latest ? "stale" : "no_data" },
      integrations: { visitors: "not_connected", adsense: "not_connected" },
    });
  } catch {
    return json({ error: "Private analytics are temporarily unavailable." }, 502);
  }
}
