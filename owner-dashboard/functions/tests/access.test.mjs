import test from "node:test";
import assert from "node:assert/strict";
import { readSession, signSession, isOwnerAccessRequest } from "../lib/access.js";
const env={SESSION_SIGNING_KEY:"test-only-session-signing-key-which-is-long-enough",OWNER_GITHUB_ID:"12345",OWNER_EMAIL:"owner@example.com"};
async function token(overrides={}){const now=Math.floor(Date.now()/1000);return signSession({github_id:12345,login:"owner",email:"owner@example.com",email_verified:true,iat:now,exp:now+300,csrf:"x".repeat(48),...overrides},env.SESSION_SIGNING_KEY);}
const req=value=>new Request("https://owner.example.pages.dev/",{headers:{Cookie:"__Host-ph_owner_session="+value}});
test("accepts valid signed session for exact configured Owner",async()=>{const value=await token();assert.equal(Boolean(await readSession(req(value),env)),true);assert.equal(await isOwnerAccessRequest(req(value),env),true);});
test("rejects missing, modified, expired, wrong-ID, wrong-email and unverified sessions",async()=>{const value=await token();assert.equal(await readSession(new Request("https://owner.example.pages.dev/"),env),null);assert.equal(await readSession(req(value+"x"),env),null);assert.equal(await readSession(req(await token({exp:1})),env),null);assert.equal(await readSession(req(await token({github_id:999})),env),null);assert.equal(await readSession(req(await token({email:"other@example.com"})),env),null);assert.equal(await readSession(req(await token({email_verified:false})),env),null);});
