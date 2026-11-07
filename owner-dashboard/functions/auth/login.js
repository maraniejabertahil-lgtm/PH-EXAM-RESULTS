// GitHub OAuth is no longer part of Owner login. Firebase password + Firestore role is sufficient.
export async function onRequestGet(){return new Response(null,{status:302,headers:{Location:"/", "Cache-Control":"no-store"}});}
