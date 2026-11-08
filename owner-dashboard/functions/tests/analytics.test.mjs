import test from "node:test";
import assert from "node:assert/strict";
import { onRequestGet } from "../api/analytics.js";
import { signSession } from "../lib/access.js";

const env = {
  SESSION_SIGNING_KEY: "test-only-session-signing-key-which-is-long-enough",
  OWNER_EMAIL: "owner@example.com",
  CF_D1_READ_API_TOKEN: "read-token",
  CF_ACCOUNT_ID: "account",
  CF_D1_DATABASE_ID: "database",
};
async function ownerRequest(url) {
  const now = Math.floor(Date.now() / 1000);
  const session = await signSession({
    github_id: 12345, login: "owner", email: "owner@example.com", email_verified: true,
    firebase_uid: "firebase-uid", firebase_email: "owner@example.com", firebase_role: "owner",
    iat: now, exp: now + 300, csrf: "x".repeat(48),
  }, env.SESSION_SIGNING_KEY);
  return new Request(url, { headers: { Cookie: "__Host-ph_owner_session=" + session } });
}

test("rejects signed-out analytics requests before querying D1", async () => {
  const original = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => { calls++; throw new Error("must not query"); };
  try {
    const response = await onRequestGet({ request: new Request("https://owner.example.pages.dev/api/analytics"), env });
    assert.equal(response.status, 401);
    assert.equal(calls, 0);
  } finally { globalThis.fetch = original; }
});

test("returns bounded analytics from private operational tables", async () => {
  const original = globalThis.fetch;
  const requests = [];
  const results = [
    [{ day: "2026-11-01", watcher_scans: 5, releases: 1, events: 6, extraction_events: 2, publication_events: 1 }],
    [{ day: "2026-11-01", batches: 1, published: 1, validated_records: 50 }],
    [{ active: 2, next_release: "2026-11-10" }],
    [{ occurred_at: new Date().toISOString() }],
    [{ status: "updated", upcoming_count: 22, exam: "Veterinarians (CBLE)", target_release_date: "2026-11-10", checked_at: new Date().toISOString() }],
  ];
  globalThis.fetch = async (_url, init) => {
    requests.push(JSON.parse(init.body));
    return new Response(JSON.stringify({ success: true, result: [{ success: true, results: results[requests.length - 1] }] }));
  };
  try {
    const response = await onRequestGet({ request: await ownerRequest("https://owner.example.pages.dev/api/analytics?days=30"), env });
    const payload = await response.json();
    assert.equal(response.status, 200);
    assert.equal(payload.days, 30);
    assert.equal(payload.daily[0].watcher_scans, 5);
    assert.equal(payload.batches[0].validated_records, 50);
    assert.equal(payload.predictions.active, 2);
    assert.equal(payload.monitor.status, "active");
    assert.equal(payload.schedule.exam, "Veterinarians (CBLE)");
    assert.equal(payload.schedule.target_release_date, "2026-11-10");
    assert.deepEqual(payload.integrations, { visitors: "not_connected", adsense: "not_connected" });
    assert.equal(requests.length, 5);
    assert.ok(requests.every((item) => typeof item.sql === "string" && item.sql.includes("FROM ")));
    assert.ok(!JSON.stringify(payload).includes("examinee"));
  } finally { globalThis.fetch = original; }
});

test("falls back to the default 30-day window for unsupported ranges", async () => {
  const original = globalThis.fetch;
  const paramsHistory = [];
  globalThis.fetch = async (_url, init) => {
    paramsHistory.push(JSON.parse(init.body).params);
    return new Response(JSON.stringify({ success: true, result: [{ success: true, results: [] }] }));
  };
  try {
    const response = await onRequestGet({ request: await ownerRequest("https://owner.example.pages.dev/api/analytics?days=365"), env });
    const payload = await response.json();
    assert.equal(response.status, 200);
    assert.equal(payload.days, 30);
    assert.equal(paramsHistory[0][0], "-30 days");
  } finally { globalThis.fetch = original; }
});
