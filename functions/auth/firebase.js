const PUBLIC_SITE_ORIGIN = "https://ph-exam-results.pages.dev";
const OWNER_DASHBOARD_AUTH_URL = "https://ph-exam-results-owner.pages.dev/auth/firebase";
const UPSTREAM_TIMEOUT_MS = 15_000;

function json(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

/**
 * Same-origin browser entry point for Firebase Owner sign-in.
 *
 * The public browser sends credentials only to its own Pages origin. This
 * Function forwards them over HTTPS to the isolated private dashboard. The
 * private endpoint still performs Firebase password verification, token
 * signature validation, and Firestore Owner-role authorization.
 */
export async function onRequestPost({ request }) {
  if (request.headers.get("Origin") !== PUBLIC_SITE_ORIGIN) {
    return json({ error: "Open the official PH Exam Results website to sign in." }, 403);
  }

  if (request.headers.get("Content-Type")?.split(";")[0].trim().toLowerCase() !== "application/json") {
    return json({ error: "Invalid Owner sign-in request." }, 415);
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Invalid Owner sign-in request." }, 400);
  }

  const email = typeof body?.email === "string" ? body.email.trim() : "";
  const password = typeof body?.password === "string" ? body.password : "";
  if (!email || !password || email.length > 320 || password.length > 1024) {
    return json({ error: "Enter a valid Owner email and password." }, 400);
  }

  try {
    const upstream = await fetch(OWNER_DASHBOARD_AUTH_URL, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        // The private dashboard deliberately authorizes only this exact origin.
        Origin: PUBLIC_SITE_ORIGIN,
      },
      body: JSON.stringify({ email, password }),
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });

    const rawPayload = await upstream.text();
    const upstreamContentType = upstream.headers.get("Content-Type") || "";
    const mediaTypeCandidate = upstreamContentType.split(";")[0].trim().toLowerCase();
    const mediaType = /^[a-z0-9!#    const payload = await upstream.json().catch(() => null);
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return json({ error: "The Owner sign-in service returned an invalid response." }, 502);
    }
^_.+-]+\/[a-z0-9!#    const payload = await upstream.json().catch(() => null);
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return json({ error: "The Owner sign-in service returned an invalid response." }, 502);
    }
^_.+-]+$/.test(mediaTypeCandidate)
      ? mediaTypeCandidate
      : "missing-or-invalid";
    let payload = null;
    try {
      payload = rawPayload ? JSON.parse(rawPayload) : null;
    } catch {
      // Upstream HTML/error bodies are intentionally never reflected to the browser.
    }
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      const routeHint = upstream.status === 404
        ? "Verify that CF_OWNER_PAGES_PROJECT_NAME is ph-exam-results-owner and that /auth/firebase is deployed."
        : "Check the private Owner Pages deployment and its /auth/firebase route.";
      return json({
        error: `The Owner sign-in service returned a non-JSON response (HTTP ${upstream.status}; content-type ${mediaType}). ${routeHint}`,
      }, 502);
    }

    // Return only the two response shapes the browser needs. Never forward
    // upstream cookies, identity tokens, or incidental response headers.
    if (payload.authenticated === true && typeof payload.proof === "string") {
      return json({ authenticated: true, proof: payload.proof }, upstream.status);
    }

    return json({
      error: typeof payload.error === "string"
        ? payload.error
        : "Firebase Owner access could not be verified.",
    }, upstream.status);
  } catch {
    // Do not log or reflect the request body: it contains the Owner password.
    return json({
      error: "The Owner sign-in service is temporarily unreachable. Check your connection and try again.",
    }, 503);
  }
}
