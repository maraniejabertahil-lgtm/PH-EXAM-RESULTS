import { COOKIE_NAMES, clearCookie, requireCsrf } from "../lib/access.js";
export async function onRequestPost({request,env}){
 if(!(await requireCsrf(request,env)))return new Response("Forbidden",{status:403,headers:{"Cache-Control":"no-store"}});
 const headers=new Headers({"Cache-Control":"no-store"});
 headers.append("Set-Cookie",clearCookie(COOKIE_NAMES.session));
 headers.append("Set-Cookie",clearCookie(COOKIE_NAMES.firebase));
 return new Response(null,{status:204,headers});
}
