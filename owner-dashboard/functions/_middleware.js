import { readSession } from "./lib/access.js";

export async function onRequest(context) {
  const url = new URL(context.request.url);
  if (url.pathname === "/" || url.pathname === "/index.html") {
    const session = await readSession(context.request, context.env);
    if (!session) {
      return Response.redirect("https://ph-exam-results.pages.dev/?owner=login", 302);
    }
  }
  return context.next();
}