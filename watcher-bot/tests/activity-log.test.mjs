import test from "node:test";
import assert from "node:assert/strict";
import { recordActivity } from "../src/activity-log.js";

test("Watcher activity logging is a no-op until D1 credentials are configured", async () => {
  assert.equal(await recordActivity({}, {
    event_id: "event-1", execution_id: "execution-1", status: "success",
  }), false);
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
  assert.match(body.sql, /INSERT OR IGNORE/);
  assert.equal(body.params[0], "event-1");
  assert.equal(body.params.at(-1), JSON.stringify({ mode: "standard" }));
});
