import { COOKIE_NAMES, cookieHeader, randomToken, signSession } from "../lib/access.js";

const SESSION_SECONDS = 8 * 60 * 60;
const JWKS_URL = "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com";

function json(value, status, origin) {
  const headers = {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Vary": "Origin",
  };
  if (origin) {
    headers["Access-Control-Allow-Origin"] = origin;
    headers["Access-Control-Allow-Credentials"] = "true";
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
  return JSON.parse(new TextDecoder().decode(Uint8Array.from(
    atob(normalized + "=".repeat((4 - normalized.length % 4) % 4)), c => c.charCodeAt(0)
  )));
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
  if (!response.ok) throw new Error("Signing keys unavailable");
  const keys = await response.json();
  const jwk = Array.isArray(keys.keys)
    ? keys.keys.find(key => key.kid === header.kid && key.kty === "RSA")
    : null;
  if (!jwk) throw new Error("Unknown signing key");

  const publicKey = await crypto.subtle.importKey(
    "jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]
  );
  const signature = Uint8Array.from(
    atob(parts[2].replace(/-/g, "+").replace(/_/g, "/") +
      "=".repeat((4 - parts[2].length % 4) % 4)),
    c => c.charCodeAt(0)
  );
  const signed = new TextEncoder().encode(parts[0] + "." + parts[1]);
  if (!await crypto.subtle.verify("RSASSA-PKCS1-v1_5", publicKey, signature, signed)) {
    throw new Error("Invalid signature");
  }

  const now = Math.floor(Date.now() / 1000);
  if (claims.iss !== "https://securetoken.google.com/" + projectId ||
      claims.aud !== projectId || typeof claims.sub !== "string" || !claims.sub ||
      claims.sub.length > 128 || !Number.isInteger(claims.exp) || claims.exp <= now ||
      !Number.isInteger(claims.iat) || claims.iat > now + 60 ||
      !Number.isInteger(claims.auth_time) || claims.auth_time > now + 60 ||
      now - claims.auth_time > 10 * 60 || claims.email_verified !== true ||
      typeof claims.email !== "string") {
    throw new Error("Invalid identity claims");
  }
  return claims;
}

async function exchange({ request, env }) {
  const origin = allowedOrigin(request, env);
  if (!origin) return json({ error: "Origin not allowed." }, 403);
  if (!env.FIREBASE_PROJECT_ID || !env.OWNER_EMAIL ||
      !env.SESSION_SIGNING_KEY || env.SESSION_SIGNING_KEY.length < 32) {
    return json({ error: "Owner authentication is not configured." }, 503, origin);
  }
  if (request.headers.get("Content-Type")?.split(";")[0].trim().toLowerCase() !== "application/json") {
    return json({ error: "Invalid request." }, 415, origin);
  }

  try {
    const body = await request.json();
    const claims = await verifyFirebaseToken(body?.idToken, env.FIREBASE_PROJECT_ID);
    const ownerEmail = String(env.OWNER_EMAIL).trim().toLowerCase();
    if (claims.email.toLowerCase() !== ownerEmail) {
      return json({ error: "Owner access denied." }, 403, origin);
    }

    const documentUrl = "https://firestore.googleapis.com/v1/projects/" +
      encodeURIComponent(env.FIREBASE_PROJECT_ID) + "/databases/(default)/documents/users/" +
      encodeURIComponent(claims.sub);
    const userResponse = await fetch(documentUrl, {
      headers: { Authorization: "Bearer " + body.idToken, Accept: "application/json" },
    });
    if (!userResponse.ok) return json({ error: "Owner access denied." }, 403, origin);

    const userDocument = await userResponse.json();
    const fields = userDocument.fields || {};
    if (fields.role?.stringValue !== "owner" || fields.active?.booleanValue !== true ||
        fields.email?.stringValue?.trim().toLowerCase() !== ownerEmail) {
      return json({ error: "Owner access denied." }, 403, origin);
    }

    const now = Math.floor(Date.now() / 1000);
    const session = await signSession({
      provider: "firebase",
      project_id: env.FIREBASE_PROJECT_ID,
      uid: claims.sub,
      role: "owner",
      login: ownerEmail,
      email: ownerEmail,
      email_verified: true,
      iat: now,
      exp: now + SESSION_SECONDS,
      csrf: randomToken(32),
    }, env.SESSION_SIGNING_KEY);

    return new Response(JSON.stringify({ authenticated: true }), {
      status: 200,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Vary": "Origin",
        "Set-Cookie": cookieHeader(COOKIE_NAMES.session, session, SESSION_SECONDS),
      },
    });
  } catch {
    return json({ error: "Owner sign-in could not be verified." }, 401, origin);
  }
}

export async function onRequestOptions({ request, env }) {
  const origin = allowedOrigin(request, env);
  if (!origin) return new Response(null, { status: 403 });
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": origin,
      "Access-Control-Allow-Credentials": "true",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Max-Age": "600",
      "Vary": "Origin",
    },
  });
}

export async function onRequestPost(context) {
  return exchange(context);
}
