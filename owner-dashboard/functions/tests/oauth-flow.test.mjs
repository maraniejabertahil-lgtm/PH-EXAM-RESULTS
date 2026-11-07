import test from "node:test";
import assert from "node:assert/strict";
import { login, callback } from "../lib/oauth.js";
import { COOKIE_NAMES, signSession, readSession } from "../lib/access.js";

const env={
  GITHUB_OAUTH_CLIENT_ID:"github-client-id",
  GITHUB_OAUTH_CLIENT_SECRET:"github-client-secret",
  OWNER_GITHUB_ID:"338246827",
  OWNER_EMAIL:"owner@example.com",
  PUBLIC_SITE_ORIGIN:"https://ph-exam-results.pages.dev",
  SESSION_SIGNING_KEY:"test-only-session-signing-key-which-is-long-enough",
};
async function firebaseCookie(){
  const now=Math.floor(Date.now()/1000);
  return signSession({purpose:"firebase-owner-proof",firebase_uid:"firebase-uid",firebase_email:"owner@example.com",firebase_role:"owner",iat:now,exp:now+600,nonce:"n".repeat(32)},env.SESSION_SIGNING_KEY);
}
test("GitHub OAuth cannot start without a verified Firebase Owner proof",async()=>{
  const response=await login({request:new Request("https://ph-exam-results-owner.pages.dev/auth/login"),env});
  assert.equal(response.status,302);
  assert.equal(response.headers.get("Location"),"https://ph-exam-results.pages.dev/?owner=login&owner_reason=firebase_required");
});
test("valid Firebase Owner proof starts the existing GitHub OAuth PKCE flow",async()=>{
  const proof=await firebaseCookie();
  const request=new Request("https://ph-exam-results-owner.pages.dev/auth/login",{headers:{Cookie:COOKIE_NAMES.firebase+"="+proof}});
  const response=await login({request,env});
  assert.equal(response.status,302);
  const location=new URL(response.headers.get("Location"));
  assert.equal(location.origin,"https://github.com");
  assert.equal(location.pathname,"/login/oauth/authorize");
  assert.equal(location.searchParams.get("client_id"),env.GITHUB_OAUTH_CLIENT_ID);
  assert.equal(location.searchParams.get("code_challenge_method"),"S256");
  assert.ok(location.searchParams.get("code_challenge"));
  assert.ok(response.headers.get("Set-Cookie").includes(COOKIE_NAMES.state));
  assert.ok(response.headers.get("Set-Cookie").includes(COOKIE_NAMES.verifier));
});
test("GitHub callback issues a dashboard session only when ID and verified email match",async()=>{
  const proof=await firebaseCookie();
  const state="oauth-state-value";
  const verifier="pkce-verifier-value-with-sufficient-entropy-for-this-test";
  const request=new Request("https://ph-exam-results-owner.pages.dev/auth/callback?code=auth-code&state="+state,{
    headers:{Cookie:[
      COOKIE_NAMES.firebase+"="+proof,
      COOKIE_NAMES.state+"="+state,
      COOKIE_NAMES.verifier+"="+verifier,
    ].join("; ")},
  });
  const original=globalThis.fetch;
  globalThis.fetch=async(url)=>{
    if(String(url).includes("/login/oauth/access_token"))return new Response(JSON.stringify({access_token:"test-access-token"}));
    if(String(url).endsWith("/user"))return new Response(JSON.stringify({id:338246827,login:"owner-account"}));
    if(String(url).endsWith("/user/emails"))return new Response(JSON.stringify([{email:"owner@example.com",verified:true,primary:true}]));
    throw new Error("Unexpected mocked GitHub URL");
  };
  try{
    const response=await callback({request,env});
    assert.equal(response.status,302);
    assert.equal(response.headers.get("Location"),"/");
    const setCookie=response.headers.get("Set-Cookie")||"";
    const match=setCookie.match(/__Host-ph_owner_session=([^;,\s]+)/);
    assert.ok(match,"signed session cookie must be issued");
    const sessionRequest=new Request("https://ph-exam-results-owner.pages.dev/",{headers:{Cookie:COOKIE_NAMES.session+"="+match[1]}});
    const session=await readSession(sessionRequest,env);
    assert.equal(session.firebase_uid,"firebase-uid");
    assert.equal(session.github_id,338246827);
    assert.equal(session.firebase_role,"owner");
  }finally{globalThis.fetch=original;}
});
test("GitHub callback denies another account even after Firebase Owner verification",async()=>{
  const proof=await firebaseCookie(),state="oauth-state-value",verifier="pkce-verifier-value-with-sufficient-entropy-for-this-test";
  const request=new Request("https://ph-exam-results-owner.pages.dev/auth/callback?code=auth-code&state="+state,{
    headers:{Cookie:[COOKIE_NAMES.firebase+"="+proof,COOKIE_NAMES.state+"="+state,COOKIE_NAMES.verifier+"="+verifier].join("; ")},
  });
  const original=globalThis.fetch;
  globalThis.fetch=async(url)=>{
    if(String(url).includes("/login/oauth/access_token"))return new Response(JSON.stringify({access_token:"test-access-token"}));
    if(String(url).endsWith("/user"))return new Response(JSON.stringify({id:999,login:"not-owner"}));
    if(String(url).endsWith("/user/emails"))return new Response(JSON.stringify([{email:"owner@example.com",verified:true}]));
    throw new Error("Unexpected mocked GitHub URL");
  };
  try{
    const response=await callback({request,env});
    assert.equal(response.status,302);
    assert.match(response.headers.get("Location"),/owner_reason=github_denied/);
    assert.doesNotMatch(response.headers.get("Set-Cookie")||"",/__Host-ph_owner_session=/);
  }finally{globalThis.fetch=original;}
});
