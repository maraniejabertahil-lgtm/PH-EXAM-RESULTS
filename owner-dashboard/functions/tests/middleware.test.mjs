import test from "node:test";
import assert from "node:assert/strict";
import { onRequest } from "../_middleware.js";
import { signSession } from "../lib/access.js";
const env={SESSION_SIGNING_KEY:"test-only-session-signing-key-which-is-long-enough",OWNER_GITHUB_ID:"12345",OWNER_EMAIL:"owner@example.com",PUBLIC_SITE_ORIGIN:"https://ph-exam-results.pages.dev"};
const next=async()=>new Response("next",{status:200});
test("direct dashboard URL redirects to the public Owner login dialog without a dual-proof session",async()=>{
  const response=await onRequest({request:new Request("https://owner.example.pages.dev/"),env,next});
  assert.equal(response.status,302);
  assert.equal(response.headers.get("Location"),"https://ph-exam-results.pages.dev/?owner=login");
});
test("only the Firebase handoff and authentication routes are reachable before login",async()=>{
  for(const path of ["/continue.html","/continue.js","/owner.css","/auth/firebase","/auth/firebase/complete","/auth/login","/auth/callback","/auth/session"]){
    const response=await onRequest({request:new Request("https://owner.example.pages.dev"+path),env,next});
    assert.equal(response.status,200,path);
  }
  const blocked=await onRequest({request:new Request("https://owner.example.pages.dev/activity.js"),env,next});
  assert.equal(blocked.status,302);
});
test("dashboard route continues only with both signed identity proofs",async()=>{
  const now=Math.floor(Date.now()/1000);
  const token=await signSession({github_id:12345,login:"owner",email:"owner@example.com",email_verified:true,firebase_uid:"firebase-uid",firebase_email:"owner@example.com",firebase_role:"owner",iat:now,exp:now+300,csrf:"x".repeat(48)},env.SESSION_SIGNING_KEY);
  const request=new Request("https://owner.example.pages.dev/",{headers:{Cookie:"__Host-ph_owner_session="+token}});
  const response=await onRequest({request,env,next});
  assert.equal(response.status,200);assert.equal(await response.text(),"next");
});
