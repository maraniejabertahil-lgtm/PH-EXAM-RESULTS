const API_ROOT = "https://api.cloudflare.com/client/v4";
const ACTIVITY_PREFLIGHT_SQL = "SELECT id, event_id, execution_id, correlation_id, occurred_at, created_at, " +
  "component, event_type, operation, status, severity, duration_ms, message, summary, " +
  "error_code, error_message, source, metadata_json FROM monitoring_logs LIMIT 0";

function configurationChecks(env) {
  return {
    firebase_project: Boolean(env.FIREBASE_PROJECT_ID),
    firebase_api_key: Boolean(env.FIREBASE_API_KEY),
    public_site_origin: /^https:\/\/[a-z0-9.-]+$/.test(String(env.PUBLIC_SITE_ORIGIN || "")),
    owner_email: /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(env.OWNER_EMAIL || "")),
    owner_github_id: /^\d+$/.test(String(env.OWNER_GITHUB_ID || "")),
    github_oauth_client_id: Boolean(env.GITHUB_OAUTH_CLIENT_ID),
    github_oauth_client_secret: Boolean(env.GITHUB_OAUTH_CLIENT_SECRET),
    session_signing_key: typeof env.SESSION_SIGNING_KEY === "string" && env.SESSION_SIGNING_KEY.length >= 32,
    cloudflare_account_id: Boolean(env.CF_ACCOUNT_ID),
    d1_database_id: Boolean(env.CF_D1_DATABASE_ID),
    d1_read_api_token: Boolean(env.CF_D1_READ_API_TOKEN),
  };
}

function errorCodes(payload) {
  const errors = [
    ...(Array.isArray(payload?.errors) ? payload.errors : []),
    ...(Array.isArray(payload?.result?.[0]?.errors) ? payload.result[0].errors : []),
  ];
  return [...new Set(errors.map((item) => item?.code).filter((code) => code !== undefined && code !== null).map(String))];
}

export async function onRequestGet({ env }) {
  const checks = configurationChecks(env);
  const configurationReady = Object.values(checks).every(Boolean);
  const d1 = {
    attempted: false,
    http_status: null,
    api_success: false,
    statement_success: false,
    results_array: false,
    error_codes: [],
    transport_error: false,
    ready: false,
  };

  if (configurationReady) {
    d1.attempted = true;
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
      d1.http_status = response.status;
      const payload = await response.json().catch(() => null);
      d1.api_success = response.ok && payload?.success === true;
      d1.statement_success = Array.isArray(payload?.result) && payload.result[0]?.success !== false;
      d1.results_array = Array.isArray(payload?.result?.[0]?.results);
      d1.error_codes = errorCodes(payload);
      d1.ready = d1.api_success && d1.statement_success && d1.results_array;
    } catch {
      d1.transport_error = true;
    }
  }

  const ready = configurationReady && d1.ready;
  return new Response(JSON.stringify({ ready, checks, d1 }), {
    status: ready ? 200 : 503,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
