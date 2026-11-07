export async function onRequestGet({env}){
  const ready=Boolean(
    env.FIREBASE_PROJECT_ID&&
    env.FIREBASE_API_KEY&&
    env.PUBLIC_SITE_ORIGIN&&
    env.OWNER_EMAIL&&
    env.OWNER_GITHUB_ID&&
    env.GITHUB_OAUTH_CLIENT_ID&&
    env.GITHUB_OAUTH_CLIENT_SECRET&&
    typeof env.SESSION_SIGNING_KEY==="string"&&env.SESSION_SIGNING_KEY.length>=32&&
    env.CF_ACCOUNT_ID&&
    env.CF_D1_DATABASE_ID&&
    env.CF_D1_READ_API_TOKEN
  );
  return new Response(JSON.stringify({ready}),{
    status:ready?200:503,
    headers:{
      "Content-Type":"application/json; charset=utf-8",
      "Cache-Control":"no-store",
      "X-Content-Type-Options":"nosniff",
    },
  });
}
