const encoder = new TextEncoder();
let jwksCache = null;
let jwksFetchedAt = 0;
const JWKS_TTL_MS = 10 * 60 * 1000;

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store, max-age=0", "x-content-type-options": "nosniff" },
  });
}
function decodePart(value) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized + "=".repeat((4 - normalized.length % 4) % 4);
  return JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(padded), (char) => char.charCodeAt(0))));
}
function readAccessToken(request) {
  const header = request.headers.get("cf-access-jwt-assertion");
  if (header) return header;
  const cookie = request.headers.get("cookie") || "";
  const item = cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith("CF_Authorization="));
  return item ? item.slice("CF_Authorization=".length) : "";
}
async function getJwks(issuer) {
  if (jwksCache && Date.now() - jwksFetchedAt < JWKS_TTL_MS) return jwksCache;
  const response = await fetch(new URL("/cdn-cgi/access/certs", issuer), { headers: { accept: "application/json" } });
  if (!response.ok) throw new Error("Access key service unavailable");
  const body = await response.json();
  if (!Array.isArray(body.keys)) throw new Error("Access keys unavailable");
  jwksCache = body.keys;
  jwksFetchedAt = Date.now();
  return jwksCache;
}
async function verifyAccess(request, env) {
  const rawIssuer = String(env.CF_ACCESS_TEAM_DOMAIN || "");
  const issuer = rawIssuer.endsWith("/") ? rawIssuer.slice(0, -1) : rawIssuer;
  const audience = String(env.CF_ACCESS_AUD || "");
  if (!issuer.startsWith("https://") || !audience) return false;
  try {
    const token = readAccessToken(request);
    if (token.length > 12000) return false;
    const parts = token.split(".");
    if (parts.length !== 3) return false;
    const header = decodePart(parts[0]);
    const claims = decodePart(parts[1]);
    const now = Math.floor(Date.now() / 1000);
    const audiences = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
    if (header.alg !== "RS256" || !header.kid || claims.iss !== issuer || !audiences.includes(audience) ||
        !Number.isFinite(claims.exp) || claims.exp <= now ||
        (claims.nbf !== undefined && (!Number.isFinite(claims.nbf) || claims.nbf > now + 60))) return false;
    const keys = await getJwks(issuer);
    const jwk = keys.find((key) => key.kid === header.kid && key.kty === "RSA");
    if (!jwk) return false;
    const publicKey = await crypto.subtle.importKey("jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
    const signaturePart = parts[2].replace(/-/g, "+").replace(/_/g, "/");
    const signature = Uint8Array.from(atob(signaturePart + "=".repeat((4 - signaturePart.length % 4) % 4)), (char) => char.charCodeAt(0));
    return crypto.subtle.verify("RSASSA-PKCS1-v1_5", publicKey, signature, encoder.encode(parts[0] + "." + parts[1]));
  } catch { return false; }
}
async function d1Query(env, sql) {
  const account = String(env.CF_ACCOUNT_ID || "");
  const database = String(env.CF_D1_DATABASE_ID || "");
  const token = String(env.CF_D1_API_TOKEN || "");
  if (!account || !database || !token) throw new Error("D1 configuration unavailable");
  const endpoint = "https://api.cloudflare.com/client/v4/accounts/" + encodeURIComponent(account) +
    "/d1/database/" + encodeURIComponent(database) + "/query";
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { authorization: "Bearer " + token, "content-type": "application/json", accept: "application/json" },
    body: JSON.stringify({ sql, params: [] }),
  });
  if (!response.ok) throw new Error("D1 request failed");
  const body = await response.json();
  if (body.success !== true) throw new Error("D1 query failed");
  return Array.isArray(body.result?.[0]?.results) ? body.result[0].results : [];
}
export async function onRequestGet({ request, env }) {
  if (!(await verifyAccess(request, env))) return json({ error: "Authentication required." }, 401);
  try {
    const [events, batches, predictions] = await Promise.all([
      d1Query(env, "SELECT id,event_type,status,summary,authority,exam,exam_year,created_at FROM monitoring_logs ORDER BY created_at DESC LIMIT 50"),
      d1Query(env, "SELECT batch_id,authority,exam,exam_year,status,greenlight_score,announced_count,extracted_count,summary,updated_at FROM import_batches ORDER BY updated_at DESC LIMIT 50"),
      d1Query(env, "SELECT id,authority,exam,exam_year,predicted_release_date,method,confidence,evidence_count,created_at FROM release_predictions ORDER BY created_at DESC LIMIT 50"),
    ]);
    return json({ events, batches, predictions, generated_at: new Date().toISOString() });
  } catch {
    return json({ error: "Private activity data is temporarily unavailable." }, 503);
  }
}
