const API_ROOT = "https://api.cloudflare.com/client/v4";
const ALLOWED = new Set(["running", "success", "failed", "blocked", "warning"]);

export async function recordActivity(env, event, fetchImpl = fetch) {
  const token = env.CF_D1_API_TOKEN;
  const account = env.CF_ACCOUNT_ID;
  const database = env.CF_D1_DATABASE_ID;
  if (!token || !account || !database) return false;
  if (!event || !event.event_id || !event.execution_id || !ALLOWED.has(event.status)) return false;
  const metadata = {};
  for (const key of ["source_id", "authority", "exam", "checked_targets", "skipped_targets", "mode"]) {
    const value = event.metadata?.[key];
    if (["string", "number", "boolean"].includes(typeof value)) metadata[key] = value;
  }
  const sql = "INSERT OR IGNORE INTO monitoring_logs " +
    "(event_id, execution_id, occurred_at, component, operation, status, severity, duration_ms, message, error_code, error_message, source, metadata_json) " +
    "VALUES (?, ?, ?, ?, ?, ?, ?, NULLIF(?, ''), ?, NULLIF(?, ''), NULLIF(?, ''), ?, ?)";
  const params = [
    String(event.event_id).slice(0, 160), String(event.execution_id).slice(0, 160),
    String(event.occurred_at || new Date().toISOString()), "Cloudflare Watcher",
    String(event.operation || "scheduled_scan").slice(0, 120), event.status,
    event.status === "failed" ? "error" : "info",
    Number.isInteger(event.duration_ms) && event.duration_ms >= 0 ? String(event.duration_ms) : "",
    String(event.message || "Watcher activity").slice(0, 240),
    event.error_code ? String(event.error_code).slice(0, 80) : "",
    event.error_message ? String(event.error_message).slice(0, 1000) : "",
    "cloudflare_worker", JSON.stringify(metadata)
  ];
  try {
    const response = await fetchImpl(API_ROOT + "/accounts/" + account + "/d1/database/" + database + "/query", {
      method: "POST",
      headers: { Authorization: "Bearer " + token, "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ sql, params }),
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok || payload?.success !== true || payload.result?.some((item) => item?.success === false)) {
      throw new Error("D1 activity write failed (HTTP " + response.status + ").");
    }
    return true;
  } catch (error) {
    console.warn("ACTIVITY_LOG_WARNING", String(error?.message || error).slice(0, 240));
    return false;
  }
}
