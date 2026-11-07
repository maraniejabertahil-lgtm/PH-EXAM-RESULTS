import { login } from "../lib/oauth.js";
export async function onRequestGet(context){return login(context);}
