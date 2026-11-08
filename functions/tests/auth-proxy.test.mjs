import test from "node:test";
import assert from "node:assert/strict";
import { onRequestPost } from "../auth/firebase.js";

const PUBLIC_ORIGIN = "https://ph-exam-results.pages.dev";
const UPSTREAM_URL = "https://ph-exam-results-owner.pages.dev/auth/firebase";
const credentials = { email: "owner@example.com", password: "test-password" };

function request(body = credentials, origin = PUBLIC_ORIGIN, contentType = "application/json") {
  return new Request(PUBLIC_ORIGIN + "/auth/firebase", {
    method: "POST",
    headers: { Origin: origin, "Content-Type": contentType },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

async function withFetch(handler, callback) {
  const original = globalThis.fetch;
  globalThis.fetch = handler;
  try {
    return await callback();
  } finally {
    globalThis.fetch = original;
  }
}

test("forwards valid credentials server-to-server and returns only the short-lived proof", async () => {
  let calls = 0;
  await withFetch(async (url, init) => {
    calls += 1;
    assert.equal(String(url), UPSTREAM_URL);
    assert.equal(init.method, "POST");
    assert.equal(init.headers.Origin, PUBLIC_ORIGIN);
    assert.equal(init.headers["Content-Type"], "application/json");
    assert.deepEqual(JSON.parse(init.body), credentials);
    assert.ok(init.signal instanceof AbortSignal);
    return new Response(JSON.stringify({
      authenticated: true,
      proof: "signed-owner-proof",
      idToken: "must-not-be-forwarded",
    }), {
      status: 200,
      headers: { "Set-Cookie": "must-not-be-forwarded=1" },
    });
  }, async () => {
    const response = await onRequestPost({ request: request() });
    assert.equal(calls, 1);
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("Cache-Control"), "no-store");
    assert.equal(response.headers.get("Set-Cookie"), null);
    assert.equal(response.headers.get("Access-Control-Allow-Origin"), null);
    assert.deepEqual(await response.json(), {
      authenticated: true,
      proof: "signed-owner-proof",
    });
  });
});

test("rejects non-canonical origins without contacting the private dashboard", async () => {
  let calls = 0;
  await withFetch(async () => {
    calls += 1;
    throw new Error("upstream must not be called");
  }, async () => {
    const response = await onRequestPost({
      request: request(credentials, "https://preview.ph-exam-results.pages.dev"),
    });
    assert.equal(response.status, 403);
    assert.equal(calls, 0);
  });
});

test("rejects malformed JSON, invalid content types, and missing credentials", async () => {
  let calls = 0;
  await withFetch(async () => {
    calls += 1;
    throw new Error("upstream must not be called");
  }, async () => {
    const malformed = await onRequestPost({ request: request("{") });
    const wrongType = await onRequestPost({ request: request(credentials, PUBLIC_ORIGIN, "text/plain") });
    const empty = await onRequestPost({ request: request({ email: "", password: "" }) });
    assert.equal(malformed.status, 400);
    assert.equal(wrongType.status, 415);
    assert.equal(empty.status, 400);
    assert.equal(calls, 0);
  });
});

test("passes Firebase authorization failures through as safe JSON errors", async () => {
  await withFetch(async () => new Response(JSON.stringify({
    error: "Firebase email/password could not be verified.",
    idToken: "must-not-be-forwarded",
  }), { status: 401 }), async () => {
    const response = await onRequestPost({ request: request() });
    assert.equal(response.status, 401);
    assert.deepEqual(await response.json(), {
      error: "Firebase email/password could not be verified.",
    });
    assert.equal(response.headers.get("Set-Cookie"), null);
  });
});

test("converts upstream outages and non-JSON replies into readable no-store errors", async () => {
  await withFetch(async () => { throw new Error("private service offline"); }, async () => {
    const response = await onRequestPost({ request: request() });
    assert.equal(response.status, 503);
    assert.match((await response.json()).error, /temporarily unreachable/);
    assert.equal(response.headers.get("Cache-Control"), "no-store");
  });

  await withFetch(async () => new Response("upstream unavailable", { status: 502 }), async () => {
    const response = await onRequestPost({ request: request() });
    assert.equal(response.status, 502);
    assert.match((await response.json()).error, /invalid response/);
  });
});
