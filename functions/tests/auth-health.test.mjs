import test from "node:test";
import assert from "node:assert/strict";
import { onRequestGet } from "../auth/health.js";

async function withFetch(handler, callback) {
  const original = globalThis.fetch;
  globalThis.fetch = handler;
  try {
    return await callback();
  } finally {
    globalThis.fetch = original;
  }
}

test("reports ready only when the private Owner Firebase route returns its readiness contract", async () => {
  await withFetch(async (url, init) => {
    assert.equal(String(url), "https://ph-exam-results-owner.pages.dev/auth/firebase");
    assert.equal(init.method, "GET");
    assert.equal(init.headers.Accept, "application/json");
    return Response.json({ ready: true });
  }, async () => {
    const response = await onRequestGet();
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { ready: true });
    assert.equal(response.headers.get("Cache-Control"), "no-store");
  });
});

test("reports safe diagnostics for a missing or non-JSON private route without reflecting its body", async () => {
  await withFetch(async () => new Response("<html>cloudflare not found</html>", {
    status: 404,
    headers: { "Content-Type": "text/html; charset=utf-8" },
  }), async () => {
    const response = await onRequestGet();
    const payload = await response.json();
    assert.equal(response.status, 503);
    assert.equal(payload.ready, false);
    assert.equal(payload.reason, "private_auth_invalid_response");
    assert.equal(payload.upstream_status, 404);
    assert.equal(payload.upstream_content_type, "text/html");
    assert.doesNotMatch(JSON.stringify(payload), /cloudflare|<html>/i);
  });
});

test("does not expose network exception details from the private service", async () => {
  await withFetch(async () => { throw new Error("private endpoint internals"); }, async () => {
    const response = await onRequestGet();
    assert.equal(response.status, 503);
    assert.deepEqual(await response.json(), {
      ready: false,
      reason: "private_auth_unreachable",
    });
  });
});
