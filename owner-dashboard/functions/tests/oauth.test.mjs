import test from "node:test";
import assert from "node:assert/strict";
import { readSession, signSession, requireCsrf } from "../lib/access.js";
const env={SESSION_SIGNING_KEY:"test-only-session-signing-key-which-is-long-enough",OWNER_GITHUB_ID:"12345",OWNER_EMAIL:"owner@example.com"};
async function token(){const now=Math.floor(Date.now()/1000);return signSession({github_id:12345,login:"owner",email:"owner@example.com",email_verified:true,firebase_uid:"firebase-uid",firebase_email:"owner@example.com",firebase_role:"owner",iat:now,exp:now+300,csrf:"c".repeat(48)},env.SESSION_SIGNING_KEY);}
function request(value,headers={}){return new Request("https://owner.example.pages.dev/logout",{headers:{Cookie:"__Host-ph_owner_session="+value,...headers}});}
test("requires same-origin and matching CSRF token for logout",async()=>{const value=await token();assert.equal(await requireCsrf(request(value,{Origin:"https://attacker.example","X-CSRF-Token":"c".repeat(48)}),env),false);assert.equal(await requireCsrf(request(value,{Origin:"https://owner.example.pages.dev","X-CSRF-Token":"wrong"}),env),false);assert.equal(await requireCsrf(request(value,{Origin:"https://owner.example.pages.dev","X-CSRF-Token":"c".repeat(48)}),env),true);});
test("session cannot be validated if signing secret is missing or too short",async()=>{const value=await token();assert.equal(await readSession(request(value),{...env,SESSION_SIGNING_KEY:"short"}),null);assert.equal(await readSession(request(value),{...env,SESSION_SIGNING_KEY:""}),null);});
