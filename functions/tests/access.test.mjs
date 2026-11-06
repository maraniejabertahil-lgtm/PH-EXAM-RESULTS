import test from "node:test";
import assert from "node:assert/strict";
import { isOwnerAccessRequest } from "../lib/access.js";

test("owner access fails closed when Access configuration is absent", async () => {
  const request = new Request("https://example.pages.dev/owner-monitor/");
  assert.equal(await isOwnerAccessRequest(request, {}), false);
});

test("owner access fails closed when Access assertion is missing", async () => {
  const request = new Request("https://example.pages.dev/owner-monitor/");
  assert.equal(await isOwnerAccessRequest(request, {
    CF_ACCESS_TEAM_DOMAIN: "example.cloudflareaccess.com", CF_ACCESS_AUD: "expected-audience", OWNER_EMAIL: "owner@example.com",
  }), false);
});
