import { randomToken, signSession } from "./access.js";

const JWKS_URL = "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com";
const SIGN_IN_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword";
const PROOF_SECONDS = 10 * 60;

function json(value, status = 200, origin = "") {
  const headers = {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Vary": "Origin",
  };
  if (origin) {
    headers["Access-Control-Allow-Origin"] = origin;
  }
  return new Response(JSON.stringify(value), { status, headers });
}
function allowedOrigin(request, env) {
  const configured = String(env.PUBLIC_SITE_ORIGIN || "").replace(/\/$/, "");
  const incoming = request.headers.get("Origin") || "";
  return configured && incoming === configured ? configured : "";
}
function decodePart(value) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const bytes = Uint8Array.from(atob(normalized + "=".repeat((4 - normalized.length % 4) % 4)), c => c.charCodeAt(0));
  return JSON.parse(new TextDecoder().decode(bytes));
}
async function verifyFirebaseToken(token, projectId) {
  if (typeof token !== "string" || token.length > 12000) throw new Error("Invalid token");
  const parts = token.split(".");
  if (parts.length !== 3) throw new Error("Invalid token");
  const header = decodePart(parts[0]);
  const claims = decodePart(parts[1]);
  if (header.alg !== "RS256" || typeof header.kid !== "string") throw new Error("Invalid token header");

  const response = await fetch(JWKS_URL, {
    headers: { Accept: "application/json" },
    cf: { cacheTtl: 300, cacheEverything: true },
  });
  if (!response.ok) throw new Error("Firebase signing keys unavailable");
  const keys = await response.json();
  const jwk = Array.isArray(keys.keys) ? keys.keys.find(key => key.kid === header.kid && key.kty === "RSA") : null;
  if (!jwk) throw new Error("Unknown Firebase signing key");
  const publicKey = await crypto.subtle.importKey(
    "jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]
  );
  const signature = Uint8Array.from(
    atob(parts[2].replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - parts[2].length % 4) % 4)),
    c => c.charCodeAt(0)
  );
  const signed = new TextEncoder().encode(parts[0] + "." + parts[1]);
  if (!await crypto.subtle.verify("RSASSA-PKCS1-v1_5", publicKey, signature, signed)) throw new Error("Invalid Firebase signature");

  const now = Math.floor(Date.now() / 1000);
  if (claims.iss !== "https://securetoken.google.com/" + projectId ||
      claims.aud !== projectId || typeof claims.sub !== "string" || !claims.sub ||
      claims.sub.length > 128 || !Number.isInteger(claims.exp) || claims.exp <= now ||
      !Number.isInteger(claims.iat) || claims.iat > now + 60 ||
      !Number.isInteger(claims.auth_time) || claims.auth_time > now + 60 ||
      now - claims.auth_time > 10 * 60 || claims.email_verified !== true ||
      typeof claims.email !== "string") throw new Error("Invalid Firebase identity claims");
  return claims;
}
export async function establishFirebaseProof({ request, env }) {
  const origin = allowedOrigin(request, env);
  if (!origin) return json({ error: "Origin not allowed." }, 403);
  if (!env.FIREBASE_PROJECT_ID || !env.FIREBASE_API_KEY || !env.OWNER_EMAIL ||
      !env.SESSION_SIGNING_KEY || env.SESSION_SIGNING_KEY.length < 32) {
    return json({ error: "Firebase Owner authentication is not configured." }, 503, origin);
  }
  if (request.headers.get("Content-Type")?.split(";")[0].trim().toLowerCase() !== "application/json") {
    return json({ error: "Invalid request." }, 415, origin);
  }
  try {
    const body = await request.json();
    const email = typeof body?.email === "string" ? body.email.trim() : "";
    const password = typeof body?.password === "string" ? body.password : "";
    if (!email || !password || email.length > 320 || password.length > 1024) {
      return json({ error: "Enter a valid Owner email and password." }, 400, origin);
    }
    const signInResponse = await fetch(SIGN_IN_URL + "?key=" + encodeURIComponent(env.FIREBASE_API_KEY), {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ email, password, returnSecureToken: true }),
    });
    const signIn = await signInResponse.json().catch(() => null);
    if (!signInResponse.ok || typeof signIn?.idToken !== "string") {
      return json({ error: "Firebase email/password could not be verified." }, 401, origin);
    }
    const idToken = signIn.idToken;
    const claims = await verifyFirebaseToken(idToken, env.FIREBASE_PROJECT_ID);
    const ownerEmail = String(env.OWNER_EMAIL).trim().toLowerCase();
    if (claims.email.trim().toLowerCase() !== ownerEmail ||
        (env.FIREBASE_OWNER_UID && claims.sub !== String(env.FIREBASE_OWNER_UID))) {
      return json({ error: "Firebase Owner access denied." }, 403, origin);
    }
    const documentUrl = "https://firestore.googleapis.com/v1/projects/" +
      encodeURIComponent(env.FIREBASE_PROJECT_ID) + "/databases/(default)/documents/users/" +
      encodeURIComponent(claims.sub);
    const profileResponse = await fetch(documentUrl, {
      headers: { Authorization: "Bearer " + idToken, Accept: "application/json" },
    });
    const profile = await profileResponse.json().catch(() => null);
    const fields = profile?.fields || {};
    const profileEmail = String(fields.email?.stringValue || claims.email).trim().toLowerCase();
    if (!profileResponse.ok || fields.role?.stringValue !== "owner" ||
        fields.active?.booleanValue !== true || profileEmail !== ownerEmail) {
      return json({ error: "Firebase Owner role is not active or could not be verified." }, 403, origin);
    }

    const now = Math.floor(Date.now() / 1000);
    const proof = await signSession({
      purpose: "firebase-owner-proof",
      firebase_uid: claims.sub,
      firebase_email: ownerEmail,
      firebase_role: "owner",
      iat: now,
      exp: now + PROOF_SECONDS,
      nonce: randomToken(24),
    }, env.SESSION_SIGNING_KEY);
    return json({ authenticated: true, proof }, 200, origin);
  } catch {
    return json({ error: "Firebase Owner sign-in could not be verified." }, 401, origin);
  }
}
export function firebasePreflight({ request, env }) {
  const origin = allowedOrigin(request, env);
  if (!origin) return new Response(null, { status: 403 });
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": origin,
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Max-Age": "600",
      "Vary": "Origin",
    },
  });
}
