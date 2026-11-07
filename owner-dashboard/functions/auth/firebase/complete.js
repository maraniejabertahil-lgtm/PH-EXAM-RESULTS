import { COOKIE_NAMES, cookieHeader, readSignedValue, signSession, randomToken } from "../../lib/access.js";

const SESSION_SECONDS = 8 * 60 * 60;

function json(value,status=200,extra={}){return new Response(JSON.stringify(value),{status,headers:{
  "Content-Type":"application/json; charset=utf-8",
  "Cache-Control":"no-store",
  "X-Content-Type-Options":"nosniff",
  ...extra,
}});}
export async function onRequestPost({request,env}){
  if(request.headers.get("Origin")!==new URL(request.url).origin)return json({error:"Invalid proof handoff origin."},403);
  if(request.headers.get("Content-Type")?.split(";")[0].trim().toLowerCase()!=="application/json")return json({error:"Invalid request."},415);
  let body;
  try{body=await request.json();}catch{return json({error:"Invalid proof handoff."},400);}
  const proof=await readSignedValue(body?.proof,env);
  const ownerEmail=String(env.OWNER_EMAIL||"").trim().toLowerCase();
  const now=Math.floor(Date.now()/1000);
  if(!proof||proof.purpose!=="firebase-owner-proof"||proof.firebase_role!=="owner"||
    typeof proof.firebase_uid!=="string"||!proof.firebase_uid||
    proof.firebase_email!==ownerEmail||
    (env.FIREBASE_OWNER_UID&&proof.firebase_uid!==String(env.FIREBASE_OWNER_UID))||
    proof.exp-now>600||now-proof.iat>600){
    return json({error:"Firebase Owner proof is invalid or expired."},403);
  }
  // Firebase password + verified Owner profile is the sole login proof.
  // The short-lived handoff proof is exchanged for an eight-hour first-party session.
  const session=await signSession({
    firebase_uid:proof.firebase_uid,
    firebase_email:ownerEmail,
    firebase_role:"owner",
    iat:now,
    exp:now+SESSION_SECONDS,
    csrf:randomToken(32),
  },env.SESSION_SIGNING_KEY);
  return json({authenticated:true},200,{
    "Set-Cookie":cookieHeader(COOKIE_NAMES.session,session,SESSION_SECONDS),
  });
}
