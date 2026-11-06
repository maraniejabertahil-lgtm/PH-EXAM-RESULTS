import test from "node:test";
import assert from "node:assert/strict";
import { onRequestGet } from "../api/owner/activity.js";

test("rejects requests without a Cloudflare Access assertion before querying D1", async () => {
  const response = await onRequestGet({
    request: new Request("https://example.test/api/owner/activity"),
    env: { CF_ACCESS_TEAM_DOMAIN: "https://example.cloudflareaccess.com", CF_ACCESS_AUD: "aud", CF_ACCOUNT_ID: "account", CF_D1_DATABASE_ID: "database", CF_D1_API_TOKEN: "token" },
  });
  assert.equal(response.status, 401);
  assert.equal(response.headers.get("cache-control"), "no-store, max-age=0");
  assert.deepEqual(await response.json(), { error: "Authentication required." });
});
