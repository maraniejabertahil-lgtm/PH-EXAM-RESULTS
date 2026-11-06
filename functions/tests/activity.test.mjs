import test from "node:test";
import assert from "node:assert/strict";
import { onRequestGet } from "../api/owner/activity.js";

test("activity endpoint fails closed when D1 credentials are absent", async () => {
  const response = await onRequestGet({ request: new Request("https://example.pages.dev/api/owner/activity"), env: {} });
  assert.equal(response.status, 503);
  assert.match((await response.json()).error, /not configured/i);
});

test("activity endpoint uses bounded, string-only D1 read parameters", async () => {
  const originalFetch = globalThis.fetch;
  let body;
  globalThis.fetch = async (_url, init) => {
    body = JSON.parse(init.body);
    return new Response(JSON.stringify({ success: true, result: [{ success: true, results: [] }] }), { status: 200 });
  };
  try {
    const response = await onRequestGet({
      request: new Request("https://example.pages.dev/api/owner/activity?status=failed&limit=500"),
      env: { CF_D1_READ_API_TOKEN: "read-token", CF_ACCOUNT_ID: "account", CF_D1_DATABASE_ID: "database" },
    });
    assert.equal(response.status, 200);
    assert.ok(body.params.every((value) => typeof value === "string"));
    assert.deepEqual(body.params, ["failed", "100"]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
