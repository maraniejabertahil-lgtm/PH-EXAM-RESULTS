import { readSession } from "../lib/access.js";
export async function onRequestGet({request,env}){
 const session=await readSession(request,env);
 return new Response(JSON.stringify(session?{authenticated:true,login:session.login,csrf:session.csrf}:{authenticated:false}),{
  status:200,headers:{"Content-Type":"application/json; charset=utf-8","Cache-Control":"no-store","X-Content-Type-Options":"nosniff"}});
}
