let cachedKeys = null;
let cachedAt = 0;

function base64UrlToBytes(value) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized + "=".repeat((4 - normalized.length % 4) % 4);
  return Uint8Array.from(atob(padded), (character) => character.charCodeAt(0));
}

function normalizeTeamDomain(value) {
  const raw = String(value || "").trim().replace(/^https?:\/\//, "").replace(/\/$/, "");
  return raw && /^[a-z0-9.-]+$/i.test(raw) ? raw : null;
}

async function getKeys(teamDomain) {
  if (cachedKeys && Date.now() - cachedAt < 5 * 60 * 1000) return cachedKeys;
  const response = await fetch("https://" + teamDomain + "/cdn-cgi/access/certs", {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error("Access signing keys could not be loaded.");
  const payload = await response.json();
  const keys = Array.isArray(payload.keys) ? payload.keys : [];
  if (!keys.length) throw new Error("Access signing-key response was invalid.");
  cachedKeys = keys;
  cachedAt = Date.now();
  return keys;
}

export async function isOwnerAccessRequest(request, env) {
  const teamDomain = normalizeTeamDomain(env.CF_ACCESS_TEAM_DOMAIN);
  const audience = String(env.CF_ACCESS_AUD || "").trim();
  const ownerEmail = String(env.OWNER_EMAIL || "").trim().toLowerCase();
  const token = request.headers.get("cf-access-jwt-assertion");
  if (!teamDomain || !audience || !ownerEmail || !token) return false;
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return false;
    const header = JSON.parse(new TextDecoder().decode(base64UrlToBytes(parts[0])));
    const claims = JSON.parse(new TextDecoder().decode(base64UrlToBytes(parts[1])));
    if (header.alg !== "RS256" || typeof header.kid !== "string") return false;
    const now = Math.floor(Date.now() / 1000);
    const aud = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
    if (claims.iss !== "https://" + teamDomain || !aud.includes(audience)) return false;
    if (!Number.isFinite(claims.exp) || claims.exp <= now || (Number.isFinite(claims.nbf) && claims.nbf > now)) return false;
    if (String(claims.email || "").toLowerCase() !== ownerEmail) return false;
    const jwk = (await getKeys(teamDomain)).find((key) => key.kid === header.kid && key.kty === "RSA");
    if (!jwk) return false;
    const key = await crypto.subtle.importKey("jwk", jwk,
      { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
    return crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, base64UrlToBytes(parts[2]),
      new TextEncoder().encode(parts[0] + "." + parts[1]));
  } catch {
    return false;
  }
}
