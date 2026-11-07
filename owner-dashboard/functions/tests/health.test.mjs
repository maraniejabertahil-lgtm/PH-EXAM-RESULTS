import test from "node:test";
import assert from "node:assert/strict";
import { onRequestGet } from "../auth/health.js";
const readyEnv={
  FIREBASE_PROJECT_ID:"ph-exam-results-dd94a",
  FIREBASE_API_KEY:"public-web-api-key-kept-server-side",
  PUBLIC_SITE_ORIGIN:"https://ph-exam-results.pages.dev",
  OWNER_EMAIL:"owner@example.com",
  OWNER_GITHUB_ID:"338246827",
  GITHUB_OAUTH_CLIENT_ID:"client-id",
  GITHUB_OAUTH_CLIENT_SECRET:"client-secret",
  SESSION_SIGNING_KEY:"test-only-session-signing-key-which-is-long-enough",
  CF_ACCOUNT_ID:"account",
  CF_D1_DATABASE_ID:"database",
  CF_D1_READ_API_TOKEN:"read-token",
};
test("readiness endpoint returns only ready status when required production configuration exists",async()=>{
  const response=await onRequestGet({env:readyEnv});
  assert.equal(response.status,200);
  assert.deepEqual(await response.json(),{ready:true});
});
test("readiness endpoint fails closed when any required configuration is missing",async()=>{
  const response=await onRequestGet({env:{...readyEnv,SESSION_SIGNING_KEY:"short"}});
  assert.equal(response.status,503);
  assert.deepEqual(await response.json(),{ready:false});
});
