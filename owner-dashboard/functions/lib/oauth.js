import { COOKIE_NAMES, cookieHeader, clearCookie, randomToken, signSession, readFirebaseProof } from "./access.js";
const AUTHORIZE="https://github.com/login/oauth/authorize", TOKEN="https://github.com/login/oauth/access_token", API="https://api.github.com";
const SESSION_SECONDS=8*60*60;
function json(value,status=200){return new Response(JSON.stringify(value),{status,headers:{"Content-Type":"application/json; charset=utf-8","Cache-Control":"no-store","X-Content-Type-Options":"nosniff"}});}
function redirect(path,cookies=[]){const headers=new Headers({Location:path,"Cache-Control":"no-store","Referrer-Policy":"no-referrer"});for(const value of cookies)headers.append("Set-Cookie",value);return new Response(null,{status:302,headers});}
function configured(env){return Boolean(env.GITHUB_OAUTH_CLIENT_ID&&env.GITHUB_OAUTH_CLIENT_SECRET&&env.OWNER_GITHUB_ID&&/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(env.OWNER_EMAIL||""))&&typeof env.SESSION_SIGNING_KEY==="string"&&env.SESSION_SIGNING_KEY.length>=32);}
function getCookie(request,name){return(request.headers.get("Cookie")||"").split(";").map(v=>v.trim()).find(v=>v.startsWith(name+"="))?.slice(name.length+1)||"";}
function b64(bytes){return btoa(String.fromCharCode(...bytes)).replace(/=/g,"").replace(/\+/g,"-").replace(/\//g,"_");}
async function challenge(verifier){return b64(new Uint8Array(await crypto.subtle.digest("SHA-256",new TextEncoder().encode(verifier))));}
export async function login({request,env}){
 if(!configured(env))return json({error:"Owner sign-in is not configured."},503);
 const firebaseProof=await readFirebaseProof(request,env);
 if(!firebaseProof)return redirect("/login.html?reason=firebase_required",[clearCookie(COOKIE_NAMES.firebase)]);
 const state=randomToken(32),verifier=randomToken(48),url=new URL(AUTHORIZE);
 url.searchParams.set("client_id",env.GITHUB_OAUTH_CLIENT_ID);url.searchParams.set("redirect_uri",new URL("/auth/callback",request.url).toString());
 url.searchParams.set("scope","read:user user:email");url.searchParams.set("state",state);
 url.searchParams.set("code_challenge",await challenge(verifier));url.searchParams.set("code_challenge_method","S256");
 url.searchParams.set("allow_signup","false");
 return redirect(url.toString(),[cookieHeader(COOKIE_NAMES.state,state,600),cookieHeader(COOKIE_NAMES.verifier,verifier,600)]);
}
export async function callback({request,env}){
 const url=new URL(request.url),state=url.searchParams.get("state")||"",code=url.searchParams.get("code")||"";
 const saved=getCookie(request,COOKIE_NAMES.state),verifier=getCookie(request,COOKIE_NAMES.verifier);
 const firebaseProof=await readFirebaseProof(request,env);
 const clear=[clearCookie(COOKIE_NAMES.state),clearCookie(COOKIE_NAMES.verifier)];
 if(!configured(env))return json({error:"Owner sign-in is not configured."},503);
 if(!firebaseProof)return redirect("/login.html?reason=firebase_required",[...clear,clearCookie(COOKIE_NAMES.firebase)]);
 if(!code||!state||!saved||state!==saved||!verifier)return redirect("/login.html?reason=github_failed",clear);
 try{
  const tokenResponse=await fetch(TOKEN,{method:"POST",headers:{Accept:"application/json","Content-Type":"application/json"},
   body:JSON.stringify({client_id:env.GITHUB_OAUTH_CLIENT_ID,client_secret:env.GITHUB_OAUTH_CLIENT_SECRET,code,
    redirect_uri:new URL("/auth/callback",request.url).toString(),code_verifier:verifier})});
  const token=await tokenResponse.json();
  if(!tokenResponse.ok||token.error||!token.access_token)throw new Error("OAuth token exchange failed");
  const headers={Authorization:"Bearer "+token.access_token,Accept:"application/vnd.github+json",
   "X-GitHub-Api-Version":"2022-11-28","User-Agent":"PH-EXAM-RESULTS-Owner-Dashboard"};
  const [userResponse,emailResponse]=await Promise.all([fetch(API+"/user",{headers}),fetch(API+"/user/emails",{headers})]);
  if(!userResponse.ok||!emailResponse.ok)throw new Error("GitHub identity lookup failed");
  const user=await userResponse.json(),emails=await emailResponse.json(),ownerEmail=String(env.OWNER_EMAIL).trim().toLowerCase();
  const verified=Array.isArray(emails)&&emails.some(item=>item&&item.verified===true&&String(item.email||"").toLowerCase()===ownerEmail);
  if(String(user.id)!==String(env.OWNER_GITHUB_ID)||!verified||firebaseProof.firebase_email!==ownerEmail)
    return redirect("/login.html?reason=github_denied",[...clear,clearCookie(COOKIE_NAMES.firebase)]);
  const now=Math.floor(Date.now()/1000);
  const session=await signSession({github_id:user.id,login:user.login,email:ownerEmail,email_verified:true,
   firebase_uid:firebaseProof.firebase_uid,firebase_email:firebaseProof.firebase_email,firebase_role:firebaseProof.firebase_role,
   iat:now,exp:now+SESSION_SECONDS,csrf:randomToken(32)},env.SESSION_SIGNING_KEY);
  return redirect("/",[...clear,clearCookie(COOKIE_NAMES.firebase),cookieHeader(COOKIE_NAMES.session,session,SESSION_SECONDS)]);
 }catch{return redirect("/login.html?reason=github_failed",clear);}
}
