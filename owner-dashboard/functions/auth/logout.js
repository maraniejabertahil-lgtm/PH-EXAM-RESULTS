import { COOKIE_NAMES, clearCookie, requireCsrf } from "../lib/access.js";
export async function onRequestPost({request,env}){
 if(!(await requireCsrf(request,env)))return new Response("Forbidden",{status:403,headers:{"Cache-Control":"no-store"}});
 return new Response(null,{status:204,headers:{"Set-Cookie":[clearCookie(COOKIE_NAMES.session),clearCookie(COOKIE_NAMES.firebase)].join(", "),"Cache-Control":"no-store"});
}
