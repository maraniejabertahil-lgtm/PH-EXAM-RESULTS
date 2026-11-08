const OWNER_AUTH_HEALTH_URL = "https://ph-exam-results-owner.pages.dev/auth/firebase";
const HEALTH_TIMEOUT_MS = 8_000;

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

export async function onRequestGet() {
  try {
    const upstream = await fetch(OWNER_AUTH_HEALTH_URL, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(HEALTH_TIMEOUT_MS),
    });
    const mediaTypeCandidate = (upstream.headers.get("Content-Type") || "")
      .split(";")[0].trim().toLowerCase();
    const mediaType = /^[a-z0-9!#$&^_.+-]+\/[a-z0-9!#$&^_.+-]+$/.test(mediaTypeCandidate)
      ? mediaTypeCandidate
      : "missing-or-invalid";
    const payload = await upstream.json().catch(() => null);

    if (upstream.ok && payload?.ready === true) {
      return json({ ready: true });
    }

    const result = {
      ready: false,
      reason: payload?.ready === false ? "private_auth_not_ready" : "private_auth_invalid_response",
      upstream_status: upstream.status,
      upstream_content_type: mediaType,
    };
    if (Array.isArray(payload?.missing)) {
      result.missing_settings = payload.missing.filter((name) =>
        typeof name === "string" && /^[A-Z0-9_]{1,64}$/.test(name)
      );
    }
    return json(result, 503);
  } catch {
    return json({ ready: false, reason: "private_auth_unreachable" }, 503);
  }
}
