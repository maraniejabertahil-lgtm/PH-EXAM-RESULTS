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

test("readiness fails closed when a required configuration value is missing", async () => {
  let calls = 0;
  await withFetch(async () => { calls++; throw new Error("must not query"); }, async () => {
    const response = await onRequestGet({ env: { ...readyEnv, SESSION_SIGNING_KEY: "short" } });
    assert.equal(response.status, 503);
    assert.deepEqual(await response.json(), { ready: false });
    assert.equal(calls, 0);
  });
});

test("readiness fails closed when D1 is unreachable, unauthorized, or missing its activity schema", async () => {
  const failures = [
    async () => { throw new Error("network unavailable"); },
    async () => new Response(JSON.stringify({ success: false }), { status: 403 }),
    async () => new Response(JSON.stringify({ success: true, result: [{ success: false, results: [] }] })),
    async () => new Response(JSON.stringify({ success: true, result: [] })),
  ];
  for (const handler of failures) {
    await withFetch(handler, async () => {
      const response = await onRequestGet({ env: readyEnv });
      assert.equal(response.status, 503);
      assert.deepEqual(await response.json(), { ready: false });
    });
  }
});
