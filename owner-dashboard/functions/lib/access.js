const SESSION_COOKIE = "__Host-ph_owner_session";
const STATE_COOKIE = "__Host-ph_owner_oauth_state";
const VERIFIER_COOKIE = "__Host-ph_owner_pkce";
function b64url(bytes) { return btoa(String.fromCharCode(...bytes)).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_"); }
function fromB64url(value) { const raw=value.replace(/-/g,"+").replace(/_/g,"/"); return Uint8Array.from(atob(raw+"=".repeat((4-raw.length%4)%4)),c=>c.charCodeAt(0)); }
function cookie(request,name) { return (request.headers.get("Cookie")||"").split(";").map(v=>v.trim()).find(v=>v.startsWith(name+"="))?.slice(name.length+1)||""; }
function equal(a,b) { if(typeof a!=="string"||typeof b!=="string"||a.length!==b.length)return false; let out=0; for(let i=0;i<a.length;i++)out|=a.charCodeAt(i)^b.charCodeAt(i); return out===0; }
async function hmac(secret,value) { const key=await crypto.subtle.importKey("raw",new TextEncoder().encode(secret),{name:"HMAC",hash:"SHA-256"},false,["sign"]); return b64url(new Uint8Array(await crypto.subtle.sign("HMAC",key,new TextEncoder().encode(value)))); }
export function randomToken(bytes=32) { const value=new Uint8Array(bytes); crypto.getRandomValues(value); return b64url(value); }
export function cookieHeader(name,value,maxAge) { return name+"="+value+"; Path=/; Max-Age="+maxAge+"; HttpOnly; Secure; SameSite=Lax"; }
export function clearCookie(name) { return name+"=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax"; }
export const COOKIE_NAMES={session:SESSION_COOKIE,state:STATE_COOKIE,verifier:VERIFIER_COOKIE};
export async function signSession(payload,secret) { const body=b64url(new TextEncoder().encode(JSON.stringify(payload))); return body+"."+await hmac(secret,body); }
export async function readSession(request,env) {
 const secret=env.SESSION_SIGNING_KEY;
 if(!secret||secret.length<32||!env.OWNER_EMAIL)return null;
 try {
  const parts=cookie(request,SESSION_COOKIE).split(".");
  if(parts.length!==2||!equal(await hmac(secret,parts[0]),parts[1]))return null;
  const data=JSON.parse(new TextDecoder().decode(fromB64url(parts[0])));
  const now=Math.floor(Date.now()/1000);
  if(!Number.isInteger(data.exp)||data.exp<=now||!Number.isInteger(data.iat)||data.iat>now+60||
    typeof data.csrf!=="string"||data.csrf.length<32)return null;
  const ownerEmail=String(env.OWNER_EMAIL).trim().toLowerCase();
  if(data.provider==="firebase") {
   if(!env.FIREBASE_PROJECT_ID||data.project_id!==env.FIREBASE_PROJECT_ID||
     data.role!=="owner"||typeof data.uid!=="string"||!data.uid||
     data.email!==ownerEmail||data.email_verified!==true)return null;
  } else if(String(data.github_id)!==String(env.OWNER_GITHUB_ID)||
    data.email!==ownerEmail||data.email_verified!==true)return null;
  return data;
 } catch{return null;}
}
export async function isOwnerAccessRequest(request,env){return Boolean(await readSession(request,env));}
export async function requireCsrf(request,env){
 const session=await readSession(request,env); if(!session)return false;
 if(request.headers.get("Origin")!==new URL(request.url).origin)return false;
 return equal(request.headers.get("X-CSRF-Token")||"",session.csrf);
}