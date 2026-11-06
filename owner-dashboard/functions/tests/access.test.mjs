import test from "node:test";
import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { isOwnerAccessRequest } from "../lib/access.js";

function base64url(value) { return Buffer.from(value).toString("base64url"); }

async function makeOwnerToken(email = "owner@example.com") {
  const issuer = "https://team.cloudflareaccess.com";
  const audience = "owner-dashboard-audience";
  const pair = await webcrypto.subtle.generateKey(
    { name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
    true, ["sign", "verify"],
  );
  const jwk = await webcrypto.subtle.exportKey("jwk", pair.publicKey);
  jwk.kid = "owner-test-key";
  const header = base64url(JSON.stringify({ alg: "RS256", typ: "JWT", kid: jwk.kid }));
  const now = Math.floor(Date.now() / 1000);
  const payload = base64url(JSON.stringify({ iss: issuer, aud: [audience], exp: now + 300, nbf: now - 5, email }));
  const input = header + "." + payload;
  const signature = await webcrypto.subtle.sign("RSASSA-PKCS1-v1_5", pair.privateKey, Buffer.from(input));
  return {
    token: input + "." + Buffer.from(signature).toString("base64url"),
    jwk, issuer, audience,
    env: { CF_ACCESS_TEAM_DOMAIN: "team.cloudflareaccess.com", CF_ACCESS_AUD: audience, OWNER_EMAIL: "owner@example.com" },
  };
}

test("owner access fails closed without a Cloudflare Access assertion", async () => {
  const request = new Request("https://private.example.pages.dev/");
  assert.equal(await isOwnerAccessRequest(request, {
    CF_ACCESS_TEAM_DOMAIN: "team.cloudflareaccess.com",
    CF_ACCESS_AUD: "owner-dashboard-audience",
    OWNER_EMAIL: "owner@example.com",
  }), false);
});

test("only the exact owner email with a valid signed Access JWT is accepted", async () => {
  const auth = await makeOwnerToken();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ keys: [auth.jwk] }));
  try {
    const valid = new Request("https://private.example.pages.dev/", {
      headers: { "cf-access-jwt-assertion": auth.token },
    });
    assert.equal(await isOwnerAccessRequest(valid, auth.env), true);
    const wrong = await makeOwnerToken("someone-else@example.com");
    const invalidOwner = new Request("https://private.example.pages.dev/", {
      headers: { "cf-access-jwt-assertion": wrong.token },
    });
    assert.equal(await isOwnerAccessRequest(invalidOwner, auth.env), false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
