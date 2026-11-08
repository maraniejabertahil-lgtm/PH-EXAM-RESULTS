const API_ROOT = "https://api.cloudflare.com/client/v4";
const ALLOWED = new Set(["running", "success", "failed", "blocked", "warning"]);
const LEGACY_EVENT_TYPES = new Set([
  "processing_started", "greenlight_passed", "greenlight_failed",
  "publication_completed", "publication_failed", "watcher_scan", "release_detected",
]);

function toStatement(event) {
  if (!event || !event.event_id || !event.execution_id || !ALLOWED.has(event.status)) return null;
  const metadata = {};
  for (const key of ["source_id", "authority", "exam", "exam_year", "checked_targets", "skipped_targets", "mode", "schedule_status", "upcoming_count", "nearest_release_exam", "nearest_release_date"]) {
    const value = event.metadata?.[key];
    if (["string", "number", "boolean"].includes(typeof value)) metadata[key] = value;
  }
  const operation = String(event.operation || "scheduled_scan").slice(0, 120);
  let eventType = event.event_type;
  if (!LEGACY_EVENT_TYPES.has(eventType)) {
    if (operation.toLowerCase().includes("release_detected")) {
      eventType = "release_detected";
    } else if (operation.toLowerCase().includes("scheduled_scan") || operation.toLowerCase().includes("source_check")) {
      eventType = "watcher_scan";
    } else if (operation.toLowerCase().includes("greenlight")) {
      eventType = event.status === "failed" || event.status === "blocked" ? "greenlight_failed" : "greenlight_passed";
    } else if (event.status === "failed") {
      eventType = "publication_failed";
    } else if (event.status === "blocked") {
      eventType = "greenlight_failed";
    } else if (event.status === "success") {
      eventType = "publication_completed";
    } else {
      eventType = "processing_started";
    }
  }
  const storedStatus = ({
    running: "started", success: "completed", failed: "failed",
    blocked: "failed", warning: "completed",
  })[event.status];
  let severity = event.severity || (event.status === "failed" ? "error" : "info");
  if ((event.status === "blocked" || event.status === "warning") && severity === "info") severity = "warning";
  const errorCode = event.status === "blocked" && !String(event.error_code || "").startsWith("BLOCKED")
    ? ("BLOCKED:" + String(event.error_code || "")).slice(0, 80)
    : (event.error_code || "");
  const message = String(event.message || "Watcher activity").slice(0, 240);
  const sql = "INSERT OR IGNORE INTO monitoring_logs " +
    "(id,event_id,event_type,status,summary,authority,exam,exam_year,source_id,correlation_id,created_at," +
    "execution_id,occurred_at,component,operation,severity,duration_ms,message,error_code,error_message,source,metadata_json) " +
    "VALUES (?, ?, ?, ?, ?, NULLIF(?,''), NULLIF(?,''), NULLIF(?,''), NULLIF(?,''), ?, ?, ?, ?, ?, ?, ?, NULLIF(?,''), ?, NULLIF(?,''), NULLIF(?,''), ?, ?)";
  const params = [
    String(event.event_id).slice(0, 160), String(event.event_id).slice(0, 160),
    eventType, storedStatus, message,
    metadata.authority || "", metadata.exam || "", metadata.exam_year === undefined ? "" : String(metadata.exam_year),
    metadata.source_id || "", String(event.execution_id).slice(0, 160),
    String(event.occurred_at || new Date().toISOString()), String(event.execution_id).slice(0, 160),
    String(event.occurred_at || new Date().toISOString()), "Cloudflare Watcher", operation, severity,
    Number.isInteger(event.duration_ms) && event.duration_ms >= 0 ? String(event.duration_ms) : "",
    message, String(errorCode).slice(0, 80),
    event.error_message ? String(event.error_message).slice(0, 1000) : "",
    "cloudflare_worker", JSON.stringify(metadata),
  ];
  return { sql, params };
}

export async function recordActivities(env, events, fetchImpl = fetch) {
  const token = env.CF_D1_API_TOKEN;
  const account = env.CF_ACCOUNT_ID;
  const database = env.CF_D1_DATABASE_ID;
  if (!token || !account || !database || !Array.isArray(events)) return false;
  const batch = events.map(toStatement).filter(Boolean);
  if (!batch.length) return false;
  try {
    const response = await fetchImpl(API_ROOT + "/accounts/" + account + "/d1/database/" + database + "/query", {
      method: "POST",
      headers: { Authorization: "Bearer " + token, "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ batch }),
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok || payload?.success !== true || payload.result?.some((item) => item?.success === false)) {
      throw new Error("D1 activity batch write failed (HTTP " + response.status + ").");
    }
    return true;
  } catch (error) {
    console.warn("ACTIVITY_LOG_WARNING", String(error?.message || error).slice(0, 240));
    return false;
  }
}

export async function recordActivity(env, event, fetchImpl = fetch) {
  return recordActivities(env, [event], fetchImpl);
}
