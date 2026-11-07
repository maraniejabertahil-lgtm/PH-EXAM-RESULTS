// Retired: Owner sessions are issued directly after Firebase Owner verification.
export async function onRequestGet(){return new Response(null,{status:302,headers:{Location:"/", "Cache-Control":"no-store"}});}
