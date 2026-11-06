import test from "node:test";
import assert from "node:assert/strict";
import { onRequest } from "../_middleware.js";

test("private owner routes fail closed without a verified Access JWT", async () => {
  let nextCalled = false;
  const response = await onRequest({
    request: new Request("https://example.pages.dev/owner-monitor/"),
    env: {},
    next: async () => { nextCalled = true; return new Response("asset"); },
  });
  assert.equal(response.status, 404);
  assert.equal(nextCalled, false);
});

test("ordinary public routes continue without owner authentication", async () => {
  const response = await onRequest({
    request: new Request("https://example.pages.dev/"),
    env: {},
    next: async () => new Response("public"),
  });
  assert.equal(response.status, 200);
  assert.equal(await response.text(), "public");
});
