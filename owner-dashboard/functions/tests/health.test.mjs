import test from "node:test";
import assert from "node:assert/strict";
import { onRequestGet } from "../auth/health.js";

const readyEnv = {
  FIREBASE_PROJECT_ID: "ph-exam-results-dd94a",
  FIREBASE_API_KEY: "public-web-api-key-kept-server-side",
  PUBLIC_SITE_ORIGIN: "https://ph-exam-results.pages.dev",
  OWNER_EMAIL: "owner@example.com",
  OWNER_GITHUB_ID: "338246827",
  GITHUB_OAUTH_CLIENT_ID: "client-id",
  GITHUB_OAUTH_CLIENT_SECRET: "client-secret",
  SESSION_SIGNING_KEY: "test-only-session-signing-key-which-is-long-enough",
  CF_ACCOUNT_ID: "account",
  CF_D1_DATABASE_ID: "database",
  CF_D1_READ_API_TOKEN: "read-token",
};

async function withFetch(handler, callback) {
  const original = globalThis.fetch;
  globalThis.fetch = handler;
  try { return await callback(); } finally { globalThis.fetch = original; }
}

test("readiness requires a successful live D1 query against the activity schema", async () => {
  await withFetch(async (url, init) => {
    assert.match(String(url), /\/accounts\/account\/d1\/database\/database\/query$/);
    assert.equal(init.method, "POST");
    assert.equal(init.headers.Authorization, "Bearer read-token");
    const body = JSON.parse(init.body);
    assert.match(body.sql, /FROM monitoring_logs LIMIT 0/);
    return new Response(JSON.stringify({ success: true, result: [{ success: true, results: [] }] }));
  }, async () => {
    const response = await onRequestGet({ env: readyEnv });
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { ready: true });
  });
});

test("readiness identifies invalid configuration without contacting D1", async () => {
  let calls = 0;
  await withFetch(async () => { calls++; throw new Error("must not query"); }, async () => {
    const response = await onRequestGet({ env: { ...readyEnv, SESSION_SIGNING_KEY: "short" } });
    assert.equal(response.status, 503);
    assert.deepEqual(await response.json(), { ready: false, reason: "configuration" });
    assert.equal(calls, 0);
  });
});

test("readiness rejects malformed Owner identity and public-origin configuration before querying D1", async () => {
  const invalidEnvironments = [
    { ...readyEnv, PUBLIC_SITE_ORIGIN: "http://ph-exam-results.pages.dev" },
    { ...readyEnv, PUBLIC_SITE_ORIGIN: "https://ph-exam-results.pages.dev/" },
    { ...readyEnv, OWNER_EMAIL: "not-an-email" },
    { ...readyEnv, OWNER_GITHUB_ID: "owner-account" },
  ];
  for (const env of invalidEnvironments) {
    let calls = 0;
    await withFetch(async () => { calls++; throw new Error("must not query"); }, async () => {
      const response = await onRequestGet({ env });
      assert.equal(response.status, 503);
      assert.deepEqual(await response.json(), { ready: false, reason: "configuration" });
      assert.equal(calls, 0);
    });
  }
});

test("readiness distinguishes D1 transport, HTTP authorization, and response failures without exposing secrets", async () => {
  const failures = [
    {
      handler: async () => { throw new Error("network unavailable"); },
      expected: { ready: false, reason: "d1_network" },
    },
    {
      handler: async () => new Response(JSON.stringify({ success: false }), { status: 403 }),
      expected: { ready: false, reason: "d1_http", upstream_status: 403 },
    },
    {
      handler: async () => new Response(JSON.stringify({ success: true, result: [{ success: false, results: [] }] })),
      expected: { ready: false, reason: "d1_response", upstream_status: 200 },
    },
    {
      handler: async () => new Response(JSON.stringify({ success: true, result: [] })),
      expected: { ready: false, reason: "d1_response", upstream_status: 200 },
    },
  ];
  for (const item of failures) {
    await withFetch(item.handler, async () => {
      const response = await onRequestGet({ env: readyEnv });
      assert.equal(response.status, 503);
      assert.deepEqual(await response.json(), item.expected);
    });
  }
});
