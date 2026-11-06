import test from "node:test";
import assert from "node:assert/strict";
import { onRequestGet } from "../api/activity.js";

test("rejects requests without a Cloudflare Access assertion before querying D1", async () => {
  const response = await onRequestGet({
    request: new Request("https://example.test/api/owner/activity"),
    env: { CF_ACCESS_TEAM_DOMAIN: "https://example.cloudflareaccess.com", CF_ACCESS_AUD: "aud", CF_ACCOUNT_ID: "account", CF_D1_DATABASE_ID: "database", CF_D1_READ_TOKEN: "token" },
  });
  assert.equal(response.status, 401);
  assert.equal(response.headers.get("cache-control"), "no-store, max-age=0");
  assert.deepEqual(await response.json(), { error: "Authentication required." });
});

import { webcrypto } from "node:crypto";

function base64url(value) { return Buffer.from(value).toString("base64url"); }

test("valid Access JWT is verified before the three private D1 reads", async () => {
  const issuer = "https://team.cloudflareaccess.com";
  const audience = "owner-dashboard-audience";
  const pair = await webcrypto.subtle.generateKey(
    { name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
    true, ["sign", "verify"],
  );
  const jwk = await webcrypto.subtle.exportKey("jwk", pair.publicKey);
  jwk.kid = "test-key";
  const header = base64url(JSON.stringify({ alg: "RS256", typ: "JWT", kid: "test-key" }));
  const now = Math.floor(Date.now() / 1000);
  const payload = base64url(JSON.stringify({ iss: issuer, aud: [audience], exp: now + 300, nbf: now - 5 }));
  const signingInput = header + "." + payload;
  const signature = await webcrypto.subtle.sign("RSASSA-PKCS1-v1_5", pair.privateKey, Buffer.from(signingInput));
  const token = signingInput + "." + Buffer.from(signature).toString("base64url");
  const originalFetch = globalThis.fetch;
  let d1Calls = 0;
  globalThis.fetch = async (url) => {
    if (String(url).endsWith("/cdn-cgi/access/certs")) return new Response(JSON.stringify({ keys: [jwk] }));
    d1Calls += 1;
    return new Response(JSON.stringify({ success: true, result: [{ results: [] }] }));
  };
  try {
    const response = await onRequestGet({
      request: new Request("https://example.test/api/owner/activity", { headers: { "cf-access-jwt-assertion": token } }),
      env: { CF_ACCESS_TEAM_DOMAIN: issuer, CF_ACCESS_AUD: audience, CF_ACCOUNT_ID: "account", CF_D1_DATABASE_ID: "database", CF_D1_API_TOKEN: "secret" },
    });
    assert.equal(response.status, 200);
    assert.equal(d1Calls, 3);
    assert.deepEqual(await response.json().then((body) => [body.events, body.batches, body.predictions]), [[], [], []]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
