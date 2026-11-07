import test from "node:test";
import assert from "node:assert/strict";
import { onRequest } from "../_middleware.js";
import { signSession } from "../lib/access.js";
const env={SESSION_SIGNING_KEY:"test-only-session-signing-key-which-is-long-enough",OWNER_EMAIL:"owner@example.com",FIREBASE_OWNER_UID:"firebase-uid",PUBLIC_SITE_ORIGIN:"https://ph-exam-results.pages.dev"};
const next=async()=>new Response("next",{status:200});
test("direct dashboard URL redirects to the public Owner login dialog without a Firebase Owner session",async()=>{
  const response=await onRequest({request:new Request("https://owner.example.pages.dev/"),env,next});
  assert.equal(response.status,302);
  assert.equal(response.headers.get("Location"),"https://ph-exam-results.pages.dev/?owner=login");
});
test("only the Firebase handoff and authentication routes are reachable before login",async()=>{
  for(const path of ["/continue.html","/continue","/continue.js","/continue.css","/auth/firebase","/auth/firebase/complete","/auth/login","/auth/callback","/auth/session"]){
    const response=await onRequest({request:new Request("https://owner.example.pages.dev"+path),env,next});
    assert.equal(response.status,200,path);
  }
  for(const path of ["/","/activity.js","/owner.css","/api/activity"]){
    const blocked=await onRequest({request:new Request("https://owner.example.pages.dev"+path),env,next});
    assert.equal(blocked.status,302,path);
  }
});
test("dashboard route accepts a signed Firebase Owner session with no GitHub fields",async()=>{
  const now=Math.floor(Date.now()/1000);
  const token=await signSession({firebase_uid:"firebase-uid",firebase_email:"owner@example.com",firebase_role:"owner",iat:now,exp:now+300,csrf:"x".repeat(48)},env.SESSION_SIGNING_KEY);
  const request=new Request("https://owner.example.pages.dev/",{headers:{Cookie:"__Host-ph_owner_session="+token}});
  const response=await onRequest({request,env,next});
  assert.equal(response.status,200);assert.equal(await response.text(),"next");
});
