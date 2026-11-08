import test from "node:test";
import assert from "node:assert/strict";
import { onRequestGet } from "../auth/health.js";

test("reports ready when all same-origin Firebase Owner settings are configured", async () => {
  const env = { FIREBASE_PROJECT_ID: "project", FIREBASE_API_KEY: "test-key", OWNER_EMAIL: "owner@example.com", SESSION_SIGNING_KEY: "x".repeat(40), CF_ACCOUNT_ID: "account", CF_D1_DATABASE_ID: "database", CF_D1_READ_API_TOKEN: "d1-token" };
  const response = await onRequestGet({ env });
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { ready: true });
  assert.equal(response.headers.get("Cache-Control"), "no-store");
});

test("fails closed and reports missing setting names without exposing values", async () => {
  const response = await onRequestGet({ env: { FIREBASE_PROJECT_ID: "project", FIREBASE_API_KEY: "", OWNER_EMAIL: "owner@example.com", SESSION_SIGNING_KEY: "short", CF_ACCOUNT_ID: "account", CF_D1_DATABASE_ID: "database", CF_D1_READ_API_TOKEN: "d1-token" } });
  assert.equal(response.status, 503);
  const payload = await response.json();
  assert.equal(payload.ready, false);
  assert.deepEqual(payload.missing.sort(), ["FIREBASE_API_KEY", "SESSION_SIGNING_KEY"]);
  assert.doesNotMatch(JSON.stringify(payload), /test-key|owner@example/);
});
