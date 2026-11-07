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

test("readiness reports safe configuration and successful live D1 schema checks", async () => {
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
    const body = await response.json();
    assert.equal(body.ready, true);
    assert.ok(Object.values(body.checks).every(Boolean));
    assert.deepEqual(body.d1, {
      attempted: true, http_status: 200, api_success: true,
      statement_success: true, results_array: true, error_codes: [],
      transport_error: false, ready: true,
    });
  });
});

test("readiness identifies a missing configuration item without exposing values", async () => {
  let calls = 0;
  await withFetch(async () => { calls++; throw new Error("must not query"); }, async () => {
    const response = await onRequestGet({ env: { ...readyEnv, SESSION_SIGNING_KEY: "short" } });
    assert.equal(response.status, 503);
    const body = await response.json();
    assert.equal(body.ready, false);
    assert.equal(body.checks.session_signing_key, false);
    assert.equal(body.d1.attempted, false);
    assert.equal(calls, 0);
  });
});

test("readiness identifies D1 authorization, schema, and transport failures safely", async () => {
  const failures = [
    {
      handler: async () => { throw new Error("network unavailable"); },
      check: (d1) => { assert.equal(d1.transport_error, true); },
    },
    {
      handler: async () => new Response(JSON.stringify({ success: false, errors: [{ code: 10000 }] }), { status: 403 }),
      check: (d1) => { assert.equal(d1.http_status, 403); assert.deepEqual(d1.error_codes, ["10000"]); },
    },
    {
      handler: async () => new Response(JSON.stringify({ success: true, result: [{ success: false, errors: [{ code: 7500 }] }] })),
      check: (d1) => { assert.equal(d1.statement_success, false); assert.deepEqual(d1.error_codes, ["7500"]); },
    },
    {
      handler: async () => new Response(JSON.stringify({ success: true, result: [] })),
      check: (d1) => { assert.equal(d1.results_array, false); },
    },
  ];
  for (const item of failures) {
    await withFetch(item.handler, async () => {
      const response = await onRequestGet({ env: readyEnv });
      assert.equal(response.status, 503);
      const body = await response.json();
      assert.equal(body.ready, false);
      item.check(body.d1);
    });
  }
});
