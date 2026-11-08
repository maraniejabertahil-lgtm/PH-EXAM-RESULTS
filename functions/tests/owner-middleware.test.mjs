import test from "node:test";
import assert from "node:assert/strict";
import { onRequest } from "../_middleware.js";
import { signSession } from "../lib/access.js";

const env = {
  SESSION_SIGNING_KEY: "test-only-session-signing-key-which-is-long-enough",
  OWNER_EMAIL: "owner@example.com",
  FIREBASE_OWNER_UID: "firebase-uid",
};
const next = async () => new Response("next", { status: 200 });

test("public search and Firebase handoff routes remain public", async () => {
  for (const path of ["/", "/auth/firebase", "/auth/firebase/complete", "/auth/session", "/auth/health"]) {
    const response = await onRequest({ request: new Request("https://ph-exam-results.pages.dev" + path), env, next });
    assert.equal(response.status, 200, path);
  }
});

test("Owner dashboard and private APIs redirect without a valid Owner session", async () => {
  for (const path of ["/owner", "/owner/", "/owner/activity.js", "/owner/owner.css", "/api/activity", "/api/analytics"]) {
    const response = await onRequest({ request: new Request("https://ph-exam-results.pages.dev" + path), env, next });
    assert.equal(response.status, 302, path);
    assert.match(response.headers.get("Location"), /\?owner=login/);
    assert.equal(response.headers.get("Cache-Control"), "no-store");
  }
});

test("signed Firebase Owner session unlocks protected same-origin routes", async () => {
  const now = Math.floor(Date.now() / 1000);
  const token = await signSession({
    firebase_uid: "firebase-uid", firebase_email: "owner@example.com", firebase_role: "owner",
    iat: now, exp: now + 300, csrf: "x".repeat(48),
  }, env.SESSION_SIGNING_KEY);
  const request = new Request("https://ph-exam-results.pages.dev/owner/", {
    headers: { Cookie: "__Host-ph_owner_session=" + token },
  });
  const response = await onRequest({ request, env, next });
  assert.equal(response.status, 200);
  assert.equal(await response.text(), "next");
});
