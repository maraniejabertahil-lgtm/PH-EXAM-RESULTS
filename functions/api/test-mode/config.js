import { isOwnerAccessRequest } from "../../lib/access.js";
import { getTestModeReadiness } from "../../lib/test-mode.js";

function json(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store, private",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
    },
  });
}

export async function onRequestGet({ request, env }) {
  if (!(await isOwnerAccessRequest(request, env))) {
    return json({ error: "Owner authentication required." }, 401);
  }

  try {
    return json(await getTestModeReadiness(env));
  } catch {
    return json({
      available: false,
      status: "BLOCKED",
      mode: "REAL_WORLD",
      reasons: ["TEST_MODE_READINESS_CHECK_FAILED"],
      stages: [],
      publication_gates: {
        merge_requires_owner_approval: true,
        production_deployment_requires_separate_owner_approval: true,
      },
    }, 503);
  }
}
