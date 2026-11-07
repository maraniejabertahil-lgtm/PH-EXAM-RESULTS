const API_ROOT = "https://api.cloudflare.com/client/v4";
const ACTIVITY_PREFLIGHT_SQL = "SELECT id, event_id, execution_id, correlation_id, occurred_at, created_at, " +
  "component, event_type, operation, status, severity, duration_ms, message, summary, " +
  "error_code, error_message, source, metadata_json FROM monitoring_logs LIMIT 0";

function configured(env) {
  return Boolean(
    env.FIREBASE_PROJECT_ID &&
    env.FIREBASE_API_KEY &&
    /^https:\/\/[a-z0-9.-]+$/.test(String(env.PUBLIC_SITE_ORIGIN || "")) &&
    /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(env.OWNER_EMAIL || "")) &&
    /^\d+$/.test(String(env.OWNER_GITHUB_ID || "")) &&
    env.GITHUB_OAUTH_CLIENT_ID &&
    env.GITHUB_OAUTH_CLIENT_SECRET &&
    typeof env.SESSION_SIGNING_KEY === "string" &&
    env.SESSION_SIGNING_KEY.length >= 32 &&
    env.CF_ACCOUNT_ID &&
    env.CF_D1_DATABASE_ID &&
    env.CF_D1_READ_API_TOKEN
  );
}

export async function onRequestGet({ env }) {
  let ready = configured(env);
  let reason = ready ? "" : "configuration";
  let upstreamStatus = null;
  if (ready) {
    try {
      const response = await fetch(
        API_ROOT + "/accounts/" + encodeURIComponent(env.CF_ACCOUNT_ID) +
        "/d1/database/" + encodeURIComponent(env.CF_D1_DATABASE_ID) + "/query",
        {
          method: "POST",
          headers: {
            Authorization: "Bearer " + env.CF_D1_READ_API_TOKEN,
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: JSON.stringify({ sql: ACTIVITY_PREFLIGHT_SQL, params: [] }),
          signal: AbortSignal.timeout(8000),
        },
      );
      upstreamStatus = response.status;
      const payload = await response.json().catch(() => null);
      ready = response.ok &&
        payload?.success === true &&
        Array.isArray(payload.result) &&
        payload.result[0]?.success !== false &&
        Array.isArray(payload.result[0]?.results);
      if (!ready) reason = response.ok ? "d1_response" : "d1_http";
    } catch {
      ready = false;
      reason = "d1_network";
    }
  }
  const result = ready ? { ready: true } : {
    ready: false,
    reason,
    ...(upstreamStatus === null ? {} : { upstream_status: upstreamStatus }),
  };
  return new Response(JSON.stringify(result), {
    status: ready ? 200 : 503,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
