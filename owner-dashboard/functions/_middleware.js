import { readSession } from "./lib/access.js";

const PUBLIC_PATHS = new Set([
  "/auth/firebase",
  "/auth/login",
  "/auth/callback",
  "/auth/session",
]);

export async function onRequest({ request, env, next }) {
  const url = new URL(request.url);
  if (PUBLIC_PATHS.has(url.pathname)) return next();
  const session = await readSession(request, env);
  if (!session) {
    const login = new URL("/", env.PUBLIC_SITE_ORIGIN || "https://ph-exam-results.pages.dev");
    login.searchParams.set("owner", "login");
    return new Response(null, {
      status: 302,
      headers: { Location: login.toString(), "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" },
    });
  }
  return next();
}
