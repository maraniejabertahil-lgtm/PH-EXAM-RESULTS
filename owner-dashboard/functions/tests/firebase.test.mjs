import test from "node:test";
import assert from "node:assert/strict";
import { establishFirebaseProof, firebasePreflight } from "../lib/firebase.js";

const env={
  FIREBASE_PROJECT_ID:"ph-exam-results-dd94a",
  FIREBASE_OWNER_UID:"firebase-uid",
  PUBLIC_SITE_ORIGIN:"https://ph-exam-results.pages.dev",
  OWNER_EMAIL:"owner@example.com",
  SESSION_SIGNING_KEY:"test-only-session-signing-key-which-is-long-enough",
};
const encoder=new TextEncoder();
const b64=value=>Buffer.from(value).toString("base64url");
let keyPair;
let jwk;
async function createToken(overrides={}) {
  if(!keyPair){
    keyPair=await crypto.subtle.generateKey({name:"RSASSA-PKCS1-v1_5",modulusLength:2048,publicExponent:new Uint8Array([1,0,1]),hash:"SHA-256"},true,["sign","verify"]);
    jwk=await crypto.subtle.exportKey("jwk",keyPair.publicKey);
    jwk.kid="unit-test-kid";
    jwk.alg="RS256";
    jwk.use="sig";
  }
  const now=Math.floor(Date.now()/1000);
  const header=b64(JSON.stringify({alg:"RS256",typ:"JWT",kid:"unit-test-kid"}));
  const claims={iss:"https://securetoken.google.com/"+env.FIREBASE_PROJECT_ID,aud:env.FIREBASE_PROJECT_ID,sub:"firebase-uid",exp:now+300,iat:now,auth_time:now,email:"owner@example.com",email_verified:true,...overrides};
  const payload=b64(JSON.stringify(claims));
  const signed=header+"."+payload;
  const signature=await crypto.subtle.sign("RSASSA-PKCS1-v1_5",keyPair.privateKey,encoder.encode(signed));
  return signed+"."+Buffer.from(new Uint8Array(signature)).toString("base64url");
}
function request(idToken,origin=env.PUBLIC_SITE_ORIGIN) {
  return new Request("https://ph-exam-results-owner.pages.dev/auth/firebase",{
    method:"POST",
    headers:{Origin:origin,"Content-Type":"application/json"},
    body:JSON.stringify({idToken}),
  });
}
async function withFetch(handler,callback) {
  const original=globalThis.fetch;
  globalThis.fetch=handler;
  try{return await callback();}finally{globalThis.fetch=original;}
}
function mockFetch({role="owner",active=true,email="owner@example.com"}={}) {
  return async url=>{
    if(String(url).startsWith("https://www.googleapis.com/service_accounts/")){
      return new Response(JSON.stringify({keys:[jwk]}));
    }
    return new Response(JSON.stringify({fields:{
      role:{stringValue:role},active:{booleanValue:active},email:{stringValue:email},
    }}));
  };
}
test("accepts a valid Firebase token and active Firestore Owner profile with a cross-site proof cookie",async()=>{
  const token=await createToken();
  await withFetch(mockFetch(),async()=>{
    const response=await establishFirebaseProof({request:request(token),env});
    assert.equal(response.status,200);
    assert.equal((await response.json()).authenticated,true);
    assert.equal(response.headers.get("Access-Control-Allow-Origin"),env.PUBLIC_SITE_ORIGIN);
    assert.equal(response.headers.get("Access-Control-Allow-Credentials"),"true");
    assert.match(response.headers.get("Set-Cookie"),/__Host-ph_owner_firebase=.*HttpOnly; Secure; SameSite=None/);
  });
});
test("rejects requests from every origin except the configured public website",async()=>{
  const token=await createToken();
  let calls=0;
  await withFetch(async()=>{calls++;throw new Error("must not fetch");},async()=>{
    const response=await establishFirebaseProof({request:request(token,"https://attacker.example"),env});
    assert.equal(response.status,403);
    assert.equal(calls,0);
  });
});
test("rejects a non-owner or inactive Firestore profile",async()=>{
  const token=await createToken();
  await withFetch(mockFetch({role:"student"}),async()=>{
    const response=await establishFirebaseProof({request:request(token),env});
    assert.equal(response.status,403);
    assert.equal(response.headers.get("Set-Cookie"),null);
  });
  await withFetch(mockFetch({active:false}),async()=>{
    const response=await establishFirebaseProof({request:request(token),env});
    assert.equal(response.status,403);
  });
});
test("rejects mismatched email, unverified email, wrong UID and stale authentication",async()=>{
  for(const claims of [
    {email:"other@example.com"},
    {email_verified:false},
    {sub:"other-uid"},
    {auth_time:Math.floor(Date.now()/1000)-700},
  ]){
    const token=await createToken(claims);
    await withFetch(mockFetch(),async()=>{
      const response=await establishFirebaseProof({request:request(token),env});
      assert.equal(response.status,403);
    });
  }
});
test("rejects a token with a tampered signature before reading Firestore",async()=>{
  const token=await createToken();
  let firestoreCalls=0;
  await withFetch(async url=>{
    if(String(url).startsWith("https://www.googleapis.com/service_accounts/"))return new Response(JSON.stringify({keys:[jwk]}));
    firestoreCalls++;
    return new Response(JSON.stringify({fields:{role:{stringValue:"owner"},active:{booleanValue:true}}}));
  },async()=>{
    const tampered=token.slice(0,-1)+(token.endsWith("a")?"b":"a");
    const response=await establishFirebaseProof({request:request(tampered),env});
    assert.equal(response.status,401);
    assert.equal(firestoreCalls,0);
  });
});
test("answers CORS preflight only for the configured public origin",()=>{
  const allowed=firebasePreflight({request:new Request("https://ph-exam-results-owner.pages.dev/auth/firebase",{method:"OPTIONS",headers:{Origin:env.PUBLIC_SITE_ORIGIN}}),env});
  assert.equal(allowed.status,204);
  assert.equal(allowed.headers.get("Access-Control-Allow-Origin"),env.PUBLIC_SITE_ORIGIN);
  const denied=firebasePreflight({request:new Request("https://ph-exam-results-owner.pages.dev/auth/firebase",{method:"OPTIONS",headers:{Origin:"https://attacker.example"}}),env});
  assert.equal(denied.status,403);
});
