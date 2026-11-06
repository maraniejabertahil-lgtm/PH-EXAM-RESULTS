const API_ROOT = "https://api.cloudflare.com/client/v4";

function json(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store, private" },
  });
}

export async function onRequestGet({ request, env }) {
  const token = env.CF_D1_READ_API_TOKEN;
  const account = env.CF_ACCOUNT_ID;
  const database = env.CF_D1_DATABASE_ID;
  if (!token || !account || !database) return json({ error: "Owner monitoring storage is not configured." }, 503);
  const url = new URL(request.url);
  const limitValue = Number(url.searchParams.get("limit") || 50);
  const limit = Number.isInteger(limitValue) ? Math.max(1, Math.min(100, limitValue)) : 50;
  const status = url.searchParams.get("status") || "";
  const component = url.searchParams.get("component") || "";
  const allowedStatuses = new Set(["running", "success", "failed", "blocked", "warning"]);
  if (status && !allowedStatuses.has(status)) return json({ error: "Invalid status filter." }, 400);
  if (component.length > 80) return json({ error: "Invalid component filter." }, 400);
  const where = [];
  const params = [];
  if (status) { where.push("status = ?"); params.push(status); }
  if (component) { where.push("component = ?"); params.push(component); }
  params.push(String(limit));
  const sql = "SELECT event_id, execution_id, occurred_at, component, operation, status, severity, " +
    "duration_ms, message, error_code, error_message, source, metadata_json FROM monitoring_logs " +
    (where.length ? "WHERE " + where.join(" AND ") + " " : "") +
    "ORDER BY occurred_at DESC LIMIT ?";
  try {
    const response = await fetch(API_ROOT + "/accounts/" + account + "/d1/database/" + database + "/query", {
      method: "POST",
      headers: { Authorization: "Bearer " + token, "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ sql, params }),
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok || payload?.success !== true || payload.result?.some((item) => item?.success === false)) return json({ error: "Activity history is temporarily unavailable." }, 502);
    const rows = payload.result?.[0]?.results;
    if (!Array.isArray(rows)) return json({ error: "Activity history returned an invalid response." }, 502);
    return json({ events: rows.map((row) => ({
      ...row,
      metadata: (() => { try { return JSON.parse(row.metadata_json || "{}"); } catch { return {}; } })(),
    })) });
  } catch {
    return json({ error: "Activity history is temporarily unavailable." }, 502);
  }
}
