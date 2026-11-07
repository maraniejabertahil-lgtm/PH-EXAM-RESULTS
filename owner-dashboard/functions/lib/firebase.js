import { COOKIE_NAMES, cookieHeader, clearCookie, randomToken, signSession } from "./access.js";

const IDENTITY_API = "https://identitytoolkit.googleapis.com/v1/accounts:lookup";
const FIREBASE_COOKIE = "__Host-ph_owner_firebase";
const PROOF_SECONDS = 10 * 60;

function json(value, status = 200, headers = {}) {
  return new Response(JSON.stringify(value), { status, headers: {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    ...headers,
  }});
}
function configured(env) {
  return Boolean(env.FIREBASE_API_KEY && env.FIREBASE_PROJECT_ID &&
    env.OWNER_EMAIL && env.SESSION_SIGNING_KEY &&
    String(env.SESSION_SIGNING_KEY).length >= 32);
}
function sameOrigin(request) {
  const origin = request.headers.get("Origin");
  return Boolean(origin && origin === new URL(request.url).origin);
}
export async function getFirebaseConfig({ env }) {
  if (!configured(env)) return json({ error: "Firebase Owner sign-in is not configured." }, 503);
  return json({ apiKey: env.FIREBASE_API_KEY, projectId: env.FIREBASE_PROJECT_ID });
}
export async function establishFirebaseProof({ request, env }) {
  if (!configured(env)) return json({ error: "Firebase Owner sign-in is not configured." }, 503);
  if (!sameOrigin(request)) return json({ error: "Invalid request origin." }, 403);
  let body;
  try { body = await request.json(); } catch { return json({ error: "Invalid sign-in request." }, 400); }
  const idToken = typeof body?.idToken === "string" ? body.idToken : "";
  if (!idToken || idToken.length > 12000) return json({ error: "Firebase sign-in token is missing or invalid." }, 400);

  try {
    const identityResponse = await fetch(IDENTITY_API + "?key=" + encodeURIComponent(env.FIREBASE_API_KEY), {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ idToken }),
    });
    const identity = await identityResponse.json().catch(() => null);
    const user = Array.isArray(identity?.users) ? identity.users[0] : null;
    const ownerEmail = String(env.OWNER_EMAIL).trim().toLowerCase();
    if (!identityResponse.ok || !user || user.disabled === true ||
        user.emailVerified !== true ||
        String(user.email || "").trim().toLowerCase() !== ownerEmail ||
        (env.FIREBASE_OWNER_UID && String(user.localId) !== String(env.FIREBASE_OWNER_UID))) {
      return json({ error: "This Firebase account is not authorized as the active Owner." }, 403);
    }

    const documentUrl = "https://firestore.googleapis.com/v1/projects/" +
      encodeURIComponent(env.FIREBASE_PROJECT_ID) +
      "/databases/(default)/documents/users/" + encodeURIComponent(user.localId);
    const profileResponse = await fetch(documentUrl, {
      headers: { Authorization: "Bearer " + idToken, Accept: "application/json" },
    });
    const profile = await profileResponse.json().catch(() => null);
    if (!profileResponse.ok || !profile?.fields) {
      return json({ error: "The Firebase Owner profile could not be verified." }, 403);
    }
    const role = profile.fields.role?.stringValue;
    const active = profile.fields.active?.booleanValue;
    const profileEmail = String(profile.fields.email?.stringValue || user.email || "").trim().toLowerCase();
    if (role !== "owner" || active !== true || profileEmail !== ownerEmail) {
      return json({ error: "This Firebase account is not authorized as the active Owner." }, 403);
    }

    const now = Math.floor(Date.now() / 1000);
    const proof = await signSession({
      firebase_uid: user.localId,
      firebase_email: ownerEmail,
      firebase_role: "owner",
      iat: now,
      exp: now + PROOF_SECONDS,
      nonce: randomToken(24),
    }, env.SESSION_SIGNING_KEY);
    return json({ authenticated: true, next: "/auth/login" }, 200, {
      "Set-Cookie": cookieHeader(FIREBASE_COOKIE, proof, PROOF_SECONDS),
    });
  } catch {
    return json({ error: "Firebase Owner verification is temporarily unavailable." }, 502);
  }
}
export { FIREBASE_COOKIE };
