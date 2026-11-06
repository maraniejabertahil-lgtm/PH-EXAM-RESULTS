import { isOwnerAccessRequest } from "./lib/access.js";

const PRIVATE_PREFIXES = ["/owner-monitor", "/api/owner"];

export async function onRequest(context) {
  const pathname = new URL(context.request.url).pathname;
  if (!PRIVATE_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(prefix + "/"))) {
    return context.next();
  }
  if (!(await isOwnerAccessRequest(context.request, context.env))) {
    return new Response("Not found", {
      status: 404,
      headers: { "Cache-Control": "no-store", "Content-Type": "text/plain; charset=utf-8" },
    });
  }
  return context.next();
}
