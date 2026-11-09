import { readSession } from "./lib/access.js";

const OWNER_PROTECTED_PATHS = new Set([
  "/owner",
  "/api/activity",
  "/api/analytics",
  "/api/test-runs",
]);

export async function onRequest({ request, env, next }) {
  const { pathname } = new URL(request.url);
  const protectedPath = OWNER_PROTECTED_PATHS.has(pathname) ||
    pathname.startsWith("/owner/") || pathname.startsWith("/api/test-runs/");
  if (!protectedPath) return next();

  const session = await readSession(request, env);
  if (!session) {
    const login = new URL("/", request.url);
    login.searchParams.set("owner", "login");
    return new Response(null, {
      status: 302,
      headers: {
        Location: login.toString(),
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
      },
    });
  }
  return next();
}
