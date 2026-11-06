import test from "node:test";
import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { onRequestGet } from "../api/activity.js";

function base64url(value) { return Buffer.from(value).toString("base64url"); }

async function makeToken() {
  const issuer = "https://team.cloudflareaccess.com";
  const audience = "owner-dashboard-audience";
  const pair = await webcrypto.subtle.generateKey(
    { name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
    true, ["sign", "verify"],
  );
  const jwk = await webcrypto.subtle.exportKey("jwk", pair.publicKey);
  jwk.kid = "api-test-key";
  const header = base64url(JSON.stringify({ alg: "RS256", typ: "JWT", kid: jwk.kid }));
  const now = Math.floor(Date.now() / 1000);
  const payload = base64url(JSON.stringify({ iss: issuer, aud: [audience], exp: now + 300, nbf: now - 5, email: "owner@example.com" }));
  const input = header + "." + payload;
  const signature = await webcrypto.subtle.sign("RSASSA-PKCS1-v1_5", pair.privateKey, Buffer.from(input));
  return { token: input + "." + Buffer.from(signature).toString("base64url"), jwk, issuer, audience };
}

test("rejects unauthenticated activity requests before querying D1", async () => {
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; throw new Error("must not query"); };
  try {
    const response = await onRequestGet({
      request: new Request("https://private.example.pages.dev/api/activity"),
      env: { CF_D1_READ_API_TOKEN: "read-token", CF_ACCOUNT_ID: "account", CF_D1_DATABASE_ID: "database" },
    });
    assert.equal(response.status, 401);
    assert.equal(calls, 0);
    assert.equal(response.headers.get("cache-control"), "no-store, private");
  } finally { globalThis.fetch = originalFetch; }
});

test("valid owner Access JWT reads a private, bounded D1 activity timeline", async () => {
  const auth = await makeToken();
  const originalFetch = globalThis.fetch;
  let d1Body;
  let d1Calls = 0;
  globalThis.fetch = async (url, init) => {
    if (String(url).endsWith("/cdn-cgi/access/certs")) return new Response(JSON.stringify({ keys: [auth.jwk] }));
    d1Calls += 1;
    d1Body = JSON.parse(init.body);
    return new Response(JSON.stringify({ success: true, result: [{ success: true, results: [] }] }));
  };
  try {
    const response = await onRequestGet({
      request: new Request("https://private.example.pages.dev/api/activity?status=failed&limit=500", {
        headers: { "cf-access-jwt-assertion": auth.token },
      }),
      env: {
        CF_ACCESS_TEAM_DOMAIN: auth.issuer,
        CF_ACCESS_AUD: auth.audience,
        OWNER_EMAIL: "owner@example.com",
        CF_D1_READ_API_TOKEN: "read-token",
        CF_ACCOUNT_ID: "account",
        CF_D1_DATABASE_ID: "database",
      },
    });
    assert.equal(response.status, 200);
    assert.equal(d1Calls, 1);
    assert.ok(d1Body.params.every((value) => typeof value === "string"));
    assert.deepEqual(d1Body.params, ["failed", "100"]);
    assert.match(d1Body.sql, /COALESCE\(event_id, id\)/);
    assert.deepEqual(await response.json().then((body) => body.events), []);
  } finally { globalThis.fetch = originalFetch; }
});
