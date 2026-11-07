import test from "node:test";
import assert from "node:assert/strict";
import { establishFirebaseProof, firebasePreflight } from "../lib/firebase.js";
import { onRequestPost as completeFirebaseProof } from "../auth/firebase/complete.js";
import { readFirebaseProof } from "../lib/access.js";

const env={
  FIREBASE_PROJECT_ID:"ph-exam-results-dd94a",
  FIREBASE_API_KEY:"server-only-test-api-key",
  FIREBASE_OWNER_UID:"firebase-uid",
  PUBLIC_SITE_ORIGIN:"https://ph-exam-results.pages.dev",
  OWNER_EMAIL:"owner@example.com",
  OWNER_GITHUB_ID:"338246827",
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
    jwk.kid="unit-test-kid";jwk.alg="RS256";jwk.use="sig";
  }
  const now=Math.floor(Date.now()/1000);
  const header=b64(JSON.stringify({alg:"RS256",typ:"JWT",kid:"unit-test-kid"}));
  const claims={iss:"https://securetoken.google.com/"+env.FIREBASE_PROJECT_ID,aud:env.FIREBASE_PROJECT_ID,sub:"firebase-uid",exp:now+300,iat:now,auth_time:now,email:"owner@example.com",email_verified:true,...overrides};
  const payload=b64(JSON.stringify(claims));
  const signed=header+"."+payload;
  const signature=await crypto.subtle.sign("RSASSA-PKCS1-v1_5",keyPair.privateKey,encoder.encode(signed));
  return signed+"."+Buffer.from(new Uint8Array(signature)).toString("base64url");
}
function request(body,origin=env.PUBLIC_SITE_ORIGIN) {
  return new Request("https://ph-exam-results-owner.pages.dev/auth/firebase",{
    method:"POST",headers:{Origin:origin,"Content-Type":"application/json"},body:JSON.stringify(body),
  });
}
async function withFetch(handler,callback) {
  const original=globalThis.fetch;globalThis.fetch=handler;
  try{return await callback();}finally{globalThis.fetch=original;}
}
function mockFetch(token,{role="owner",active=true,email="owner@example.com",identityStatus=200}={}) {
  return async (url,init)=>{
    if(String(url).startsWith("https://identitytoolkit.googleapis.com/")){
      assert.match(String(url),/key=server-only-test-api-key/);
      const authRequest=JSON.parse(init.body);
      assert.equal(authRequest.email,"owner@example.com");
      assert.equal(authRequest.returnSecureToken,true);
      return new Response(JSON.stringify({idToken:token}),{status:identityStatus});
    }
    if(String(url).startsWith("https://www.googleapis.com/service_accounts/"))return new Response(JSON.stringify({keys:[jwk]}));
    return new Response(JSON.stringify({fields:{role:{stringValue:role},active:{booleanValue:active},email:{stringValue:email}}}));
  };
}
const ownerCredentials={email:"owner@example.com",password:"correct-test-password"};
test("accepts Firebase password sign-in and active Firestore Owner profile, returning a short-lived signed proof only",async()=>{
  const token=await createToken();
  await withFetch(mockFetch(token),async()=>{
    const response=await establishFirebaseProof({request:request(ownerCredentials),env});
    assert.equal(response.status,200);
    assert.equal(response.headers.get("Access-Control-Allow-Origin"),env.PUBLIC_SITE_ORIGIN);
    assert.equal(response.headers.get("Access-Control-Allow-Credentials"),null);
    const payload=await response.json();
    assert.equal(payload.authenticated,true);
    assert.equal(typeof payload.proof,"string");
    assert.equal(payload.idToken,undefined);
    assert.equal(response.headers.get("Set-Cookie"),null);
    const proofPayload=JSON.parse(Buffer.from(payload.proof.split(".")[0],"base64url").toString("utf8"));
    assert.equal(proofPayload.firebase_uid,"firebase-uid");
    assert.equal(proofPayload.password,undefined);
  });
});
test("completes the proof on the dashboard origin and sets a first-party HttpOnly cookie",async()=>{
  const token=await createToken();let proof="";
  await withFetch(mockFetch(token),async()=>{
    const exchange=await establishFirebaseProof({request:request(ownerCredentials),env});
    proof=(await exchange.json()).proof;
  });
  const requestToComplete=new Request("https://ph-exam-results-owner.pages.dev/auth/firebase/complete",{
    method:"POST",headers:{Origin:"https://ph-exam-results-owner.pages.dev","Content-Type":"application/json"},
    body:JSON.stringify({proof}),
  });
  const response=await completeFirebaseProof({request:requestToComplete,env});
  assert.equal(response.status,200);
  assert.match(response.headers.get("Set-Cookie"),/__Host-ph_owner_firebase=.*HttpOnly; Secure; SameSite=Lax/);
  const cookie=response.headers.get("Set-Cookie").split(";")[0];
  const sessionRequest=new Request("https://ph-exam-results-owner.pages.dev/",{headers:{Cookie:cookie}});
  const firebaseProof=await readFirebaseProof(sessionRequest,env);
  assert.equal(firebaseProof.firebase_uid,"firebase-uid");
  assert.equal(firebaseProof.firebase_role,"owner");
});
test("rejects requests from origins other than the configured public website",async()=>{
  let calls=0;
  await withFetch(async()=>{calls++;throw new Error("must not fetch");},async()=>{
    const response=await establishFirebaseProof({request:request(ownerCredentials,"https://attacker.example"),env});
    assert.equal(response.status,403);assert.equal(calls,0);
  });
});
test("rejects missing email/password before contacting Firebase",async()=>{
  let calls=0;
  await withFetch(async()=>{calls++;throw new Error("must not fetch");},async()=>{
    const response=await establishFirebaseProof({request:request({email:"",password:""}),env});
    assert.equal(response.status,400);assert.equal(calls,0);
  });
});
test("rejects non-owner, inactive, mismatched-email, unverified, wrong-UID and stale-auth identities",async()=>{
  const cases=[
    {claims:{},profile:{role:"student"},status:403},
    {claims:{},profile:{active:false},status:403},
    {claims:{email:"other@example.com"},profile:{},status:403},
    {claims:{email_verified:false},profile:{},status:401},
    {claims:{sub:"other-uid"},profile:{},status:403},
    {claims:{auth_time:Math.floor(Date.now()/1000)-700},profile:{},status:401},
  ];
  for(const item of cases){
    const token=await createToken(item.claims);
    await withFetch(mockFetch(token,item.profile),async()=>{
      const response=await establishFirebaseProof({request:request(ownerCredentials),env});
      assert.equal(response.status,item.status);
    });
  }
});
test("rejects incorrect Firebase password response",async()=>{
  const token=await createToken();
  await withFetch(mockFetch(token,{identityStatus:400}),async()=>{
    const response=await establishFirebaseProof({request:request(ownerCredentials),env});
    assert.equal(response.status,401);
  });
});
test("rejects tampered Firebase token signature before reading Firestore",async()=>{
  const token=await createToken();let firestoreCalls=0;
  await withFetch(async(url,init)=>{
    if(String(url).startsWith("https://identitytoolkit.googleapis.com/"))return new Response(JSON.stringify({idToken:token.split(".").slice(0,2).join(".")+".a"+token.split(".")[2].slice(1)}));
    if(String(url).startsWith("https://www.googleapis.com/service_accounts/"))return new Response(JSON.stringify({keys:[jwk]}));
    firestoreCalls++;return new Response(JSON.stringify({fields:{role:{stringValue:"owner"},active:{booleanValue:true}}}));
  },async()=>{
    const response=await establishFirebaseProof({request:request(ownerCredentials),env});
    assert.equal(response.status,401);assert.equal(firestoreCalls,0);
  });
});
test("answers CORS preflight only for the configured public origin",()=>{
  const allowed=firebasePreflight({request:new Request("https://ph-exam-results-owner.pages.dev/auth/firebase",{method:"OPTIONS",headers:{Origin:env.PUBLIC_SITE_ORIGIN}}),env});
  assert.equal(allowed.status,204);assert.equal(allowed.headers.get("Access-Control-Allow-Origin"),env.PUBLIC_SITE_ORIGIN);
  const denied=firebasePreflight({request:new Request("https://ph-exam-results-owner.pages.dev/auth/firebase",{method:"OPTIONS",headers:{Origin:"https://attacker.example"}}),env});
  assert.equal(denied.status,403);
});
test("rejects a Firebase proof submitted from a different dashboard origin",async()=>{
  const response=await completeFirebaseProof({request:new Request("https://ph-exam-results-owner.pages.dev/auth/firebase/complete",{
    method:"POST",headers:{Origin:"https://attacker.example","Content-Type":"application/json"},body:JSON.stringify({proof:"x"}),
  }),env});
  assert.equal(response.status,403);
});
