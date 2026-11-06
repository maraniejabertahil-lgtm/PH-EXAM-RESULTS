import test from "node:test";
import assert from "node:assert/strict";
import { onRequestGet } from "../api/owner/activity.js";

test("activity endpoint fails closed when D1 credentials are absent", async () => {
  const response = await onRequestGet({ request: new Request("https://example.pages.dev/api/owner/activity"), env: {} });
  assert.equal(response.status, 503);
  assert.match((await response.json()).error, /not configured/i);
});
