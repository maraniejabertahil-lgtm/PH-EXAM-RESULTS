import test from "node:test";
import assert from "node:assert/strict";
import { recordActivity, recordActivities } from "../src/activity-log.js";

test("Watcher activity logging reports missing D1 credentials without exposing values", async () => {
  const original = console.warn;
  const warnings = [];
  console.warn = (message) => warnings.push(String(message));
  try {
    assert.equal(await recordActivity({}, {
      event_id: "event-1", execution_id: "execution-1", status: "success",
    }), false);
  } finally { console.warn = original; }
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /CF_D1_API_TOKEN/);
  assert.match(warnings[0], /CF_ACCOUNT_ID/);
  assert.match(warnings[0], /CF_D1_DATABASE_ID/);
  assert.doesNotMatch(warnings[0], /test-token|account|database/);
});

test("Watcher activity logging sends an idempotent parameterized D1 insert", async () => {
  let request;
  const result = await recordActivity({
    CF_D1_API_TOKEN: "test-token", CF_ACCOUNT_ID: "account", CF_D1_DATABASE_ID: "database",
  }, {
    event_id: "event-1", execution_id: "execution-1", status: "success",
    operation: "scheduled_scan", message: "Completed",
    metadata: { mode: "standard", search_query: "must-not-be-stored" },
  }, async (url, init) => {
    request = { url, init };
    return new Response(JSON.stringify({ success: true, result: [{ results: [] }] }), { status: 200 });
  });
  assert.equal(result, true);
  assert.match(request.url, /d1\/database\/database\/query$/);
  const body = JSON.parse(request.init.body);
  assert.equal(body.batch.length, 1);
  assert.match(body.batch[0].sql, /INSERT OR IGNORE/);
  assert.match(body.batch[0].sql, /NULLIF/);
  assert.ok(body.batch[0].params.every((value) => typeof value === "string"));
  assert.equal(body.batch[0].params[0], "event-1");
  assert.equal(body.batch[0].params.at(-1), JSON.stringify({ mode: "standard" }));
});

test("multiple Watcher events use one D1 REST request", async () => {
  let calls = 0;
  let body;
  const result = await recordActivities({
    CF_D1_API_TOKEN: "test-token", CF_ACCOUNT_ID: "account", CF_D1_DATABASE_ID: "database",
  }, [
    { event_id: "event-a", execution_id: "exec-a", status: "running" },
    { event_id: "event-b", execution_id: "exec-a", status: "failed", error_message: "diagnostic" },
  ], async (_url, init) => {
    calls += 1;
    body = JSON.parse(init.body);
    return new Response(JSON.stringify({
      success: true,
      result: [{ success: true }, { success: true }],
    }), { status: 200 });
  });
  assert.equal(result, true);
  assert.equal(calls, 1);
  assert.equal(body.batch.length, 2);
});
