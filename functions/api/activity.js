import { isOwnerAccessRequest } from "../lib/access.js";

const API_ROOT = "https://api.cloudflare.com/client/v4";
const STATUS_SQL = "CASE WHEN status = 'started' THEN 'running' " +
  "WHEN status = 'passed' THEN 'success' " +
  "WHEN status = 'completed' AND severity = 'warning' THEN 'warning' " +
  "WHEN status = 'completed' THEN 'success' " +
  "WHEN status = 'failed' AND error_code LIKE 'BLOCKED%' THEN 'blocked' " +
  "WHEN status = 'failed' THEN 'failed' ELSE 'warning' END";

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

export async function onRequestGet({ request, env }) {
  if (!(await isOwnerAccessRequest(request, env))) {
    return json({ error: "Owner authentication required." }, 401);
  }
  const token = env.CF_D1_READ_API_TOKEN;
  const account = env.CF_ACCOUNT_ID;
  const database = env.CF_D1_DATABASE_ID;
  if (!token || !account || !database) {
    return json({ error: "Private activity storage is not configured." }, 503);
  }

  const url = new URL(request.url);
  const limitValue = Number(url.searchParams.get("limit") || 100);
  const limit = Number.isInteger(limitValue) ? Math.max(1, Math.min(100, limitValue)) : 100;
  const status = url.searchParams.get("status") || "";
  const component = url.searchParams.get("component") || "";
  const allowedStatuses = new Set(["running", "success", "failed", "blocked", "warning"]);
  if (status && !allowedStatuses.has(status)) return json({ error: "Invalid status filter." }, 400);
  if (component.length > 80) return json({ error: "Invalid component filter." }, 400);

  const where = [];
  const params = [];
  if (status) { where.push(STATUS_SQL + " = ?"); params.push(status); }
  if (component) { where.push("COALESCE(component, event_type) = ?"); params.push(component); }
  params.push(String(limit));
  const sql = "SELECT COALESCE(event_id, id) AS event_id, " +
    "COALESCE(execution_id, correlation_id) AS execution_id, " +
    "COALESCE(occurred_at, created_at) AS occurred_at, " +
    "COALESCE(component, event_type) AS component, " +
    "COALESCE(operation, event_type) AS operation, " +
    STATUS_SQL + " AS status, severity, duration_ms, " +
    "COALESCE(message, summary) AS message, error_code, error_message, source, metadata_json " +
    "FROM monitoring_logs " + (where.length ? "WHERE " + where.join(" AND ") + " " : "") +
    "ORDER BY COALESCE(occurred_at, created_at) DESC LIMIT ?";

  try {
    const response = await fetch(API_ROOT + "/accounts/" + encodeURIComponent(account) +
      "/d1/database/" + encodeURIComponent(database) + "/query", {
      method: "POST",
      headers: {
        Authorization: "Bearer " + token,
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ sql, params }),
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok || payload?.success !== true ||
        payload.result?.some((item) => item?.success === false)) {
      return json({ error: "Activity history is temporarily unavailable." }, 502);
    }
    const rows = payload.result?.[0]?.results;
    if (!Array.isArray(rows)) return json({ error: "Activity history returned an invalid response." }, 502);
    const events = rows.map((row) => {
      let metadata = {};
      try { metadata = JSON.parse(row.metadata_json || "{}"); } catch { metadata = {}; }
      return { ...row, metadata };
    });
    return json({ events, generated_at: new Date().toISOString() });
  } catch {
    return json({ error: "Activity history is temporarily unavailable." }, 502);
  }
}
