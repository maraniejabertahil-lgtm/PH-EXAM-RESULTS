const REQUIRED_SETTINGS = [
  "FIREBASE_PROJECT_ID",
  "FIREBASE_API_KEY",
  "OWNER_EMAIL",
  "SESSION_SIGNING_KEY",
  "CF_ACCOUNT_ID",
  "CF_D1_DATABASE_ID",
  "CF_D1_READ_API_TOKEN",
];

export async function onRequestGet({ env }) {
  const missing = REQUIRED_SETTINGS.filter((name) => {
    const value = env[name];
    return typeof value !== "string" || !value.trim()
      || (name === "SESSION_SIGNING_KEY" && value.length < 32);
  });
  const ready = missing.length === 0;
  return new Response(JSON.stringify(ready ? { ready: true } : { ready: false, missing }), {
    status: ready ? 200 : 503,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
