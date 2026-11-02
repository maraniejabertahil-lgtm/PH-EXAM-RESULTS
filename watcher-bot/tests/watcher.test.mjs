import test from "node:test";
import assert from "node:assert/strict";
import worker, { runScheduled, expandPreemptiveTemplates } from "../src/index.js";

const repository = "owner/repository";
class MemoryKV {
  constructor(initial = {}) { this.values = new Map(Object.entries(initial)); }
  async get(key) { return this.values.has(key) ? this.values.get(key) : null; }
  async put(key, value) { this.values.set(key, value); }
}
function registryResponse(sources) {
  const content = btoa(JSON.stringify({ schema_version: 1, sources }));
  return new Response(JSON.stringify({ encoding: "base64", content }), { status: 200 });
}
function envFor(peak = false) {
  return {
    GITHUB_REPOSITORY: repository,
    GITHUB_TOKEN: "test-token",
    GITHUB_SOURCE_REF: "main",
    PEAK_WEEK: new MemoryKV(peak ? { PEAK_WEEK: "true" } : {})
  };
}
function approvedSource(overrides = {}) {
  return {
    id: "csc-cse", authority: "CSC", exam: "CSE", source_type: "official",
    authorized: true, enabled: true, url: "https://csc.example.gov.ph/exam-results",
    preemptive_url_templates: [], ...overrides
  };
}
function githubFetch(sources, handler) {
  const dispatches = [];
  const fetchImpl = async (input, init = {}) => {
    const url = String(input);
    if (url.includes("api.github.com/repos/owner/repository/contents/")) return registryResponse(sources);
    if (url === "https://api.github.com/repos/owner/repository/dispatches") {
      dispatches.push(JSON.parse(init.body));
      return new Response(null, { status: 204 });
    }
    return handler(url, init);
  };
  return { fetchImpl, dispatches };
}

test("standard mode checks configured source once and creates a baseline", async () => {
  const source = approvedSource();
  const { fetchImpl } = githubFetch([source], async (_url, init) => {
    assert.equal(init.method, "HEAD");
    return new Response(null, { status: 200, headers: { etag: '"v1"', "content-type": "text/html" } });
  });
  const report = await runScheduled({ env: envFor(), fetchImpl, scheduledTime: Date.UTC(2026, 10, 2) });
  assert.equal(report.mode, "standard");
  assert.equal(report.first_check.checked_targets, 1);
  assert.equal(report.second_check, null);
  assert.equal(report.first_check.results[0].status, "baseline_created");
});

test("preemptive PDF returning HTTP 200 dispatches once and is deduplicated", async () => {
  const source = approvedSource({ preemptive_url_templates: ["https://csc.example.gov.ph/CSE_{MM}{YYYY}_passers.pdf"] });
  const { fetchImpl, dispatches } = githubFetch([source], async (url, init) => {
    if (url.endsWith("CSE_112026_passers.pdf")) {
      return init.method === "HEAD"
        ? new Response(null, { status: 200, headers: { "content-type": "application/pdf" } })
        : new Response("%PDF-1.7\\nverified", { status: 206 });
    }
    return new Response(null, { status: 404 });
  });
  const env = envFor(true);
  const report = await runScheduled({ env, fetchImpl, sleepImpl: async () => {}, scheduledTime: Date.UTC(2026, 10, 2) });
  assert.equal(report.mode, "peak_week");
  assert.equal(report.second_check.checked_targets, 3);
  assert.equal(dispatches.length, 1);
  assert.ok(dispatches.every((item) => item.event_type === "source-detected"));
});

test("staging configuration dispatches only the staging-specific event type", async () => {
  const source = approvedSource({ url: "https://csc.example.gov.ph/current-list.pdf" });
  const env = envFor();
  env.GITHUB_EVENT_TYPE = "staging-source-detected";
  const { fetchImpl, dispatches } = githubFetch([source], async (_url, init) => init.method === "HEAD"
    ? new Response(null, { status: 200, headers: { "content-type": "application/pdf" } })
    : new Response("%PDF-1.7\\nverified", { status: 206 }));
  const report = await runScheduled({ env, fetchImpl, scheduledTime: Date.UTC(2026, 10, 2) });
  assert.equal(report.first_check.results[0].status, "dispatched");
  assert.equal(dispatches.length, 1);
  assert.equal(dispatches[0].event_type, "staging-source-detected");
});

test("peak week waits 30 seconds and runs two scans", async () => {
  const source = approvedSource({ preemptive_url_templates: ["https://csc.example.gov.ph/CSE_{MM}{YYYY}_passers.pdf"] });
  const { fetchImpl } = githubFetch([source], async () => new Response(null, { status: 404 }));
  const waits = [];
  const report = await runScheduled({
    env: envFor(true), fetchImpl, sleepImpl: async (ms) => waits.push(ms),
    scheduledTime: Date.UTC(2026, 10, 2)
  });
  assert.deepEqual(waits, [30_000]);
  assert.equal(report.first_check.checked_targets, 3);
  assert.equal(report.second_check.checked_targets, 3);
});

test("unapproved and disabled sources are never checked", async () => {
  const sources = [approvedSource({ authorized: false }), approvedSource({ id: "disabled", enabled: false })];
  let externalCalls = 0;
  const { fetchImpl } = githubFetch(sources, async () => {
    externalCalls += 1;
    return new Response(null, { status: 200 });
  });
  const report = await runScheduled({ env: envFor(), fetchImpl });
  assert.equal(report.approved_enabled_sources, 0);
  assert.equal(report.first_check.checked_targets, 0);
  assert.equal(externalCalls, 0);
});

test("preemptive templates only expand to the approved source origin", () => {
  const source = approvedSource({
    preemptive_url_templates: [
      "https://csc.example.gov.ph/CSE_{MM}{YYYY}_passers.pdf",
      "https://other.example.net/{YYYYMM}.pdf"
    ]
  });
  const targets = expandPreemptiveTemplates([source], Date.UTC(2026, 7, 1));
  assert.deepEqual(targets.map((item) => item.url), [
    "https://csc.example.gov.ph/CSE_082026_passers.pdf",
    "https://csc.example.gov.ph/CSE_092026_passers.pdf"
  ]);
});

test("cross-origin redirects are rejected", async () => {
  const source = approvedSource();
  const { fetchImpl } = githubFetch([source], async () => new Response(null, {
    status: 302, headers: { location: "https://malicious.example/file.pdf" }
  }));
  const report = await runScheduled({ env: envFor(), fetchImpl });
  assert.equal(report.first_check.results[0].status, "check_error");
  assert.match(report.first_check.results[0].error, /Cross-origin/);
});

test("page metadata changes discover and dispatch same-origin PDF links", async () => {
  const source = approvedSource();
  const env = envFor();
  const { createHash } = await import("node:crypto");
  const hex = createHash("sha256").update(`${source.id}\n${source.url}`).digest("hex");
  await env.PEAK_WEEK.put(
    `baseline:${hex}`,
    JSON.stringify({ status: 200, contentType: "text/html", etag: '"v1"', lastModified: "", contentLength: "" })
  );
  const { fetchImpl, dispatches } = githubFetch([source], async (url, init) => {
    if (url === source.url && init.method === "HEAD") {
      return new Response(null, { status: 200, headers: { etag: '"v2"', "content-type": "text/html" } });
    }
    if (url === source.url && init.method === "GET") {
      return new Response('<a href="/downloads/CSE-list.pdf">Download</a><a href="https://external.example/x.pdf">external</a>', {
        status: 200, headers: { "content-type": "text/html" }
      });
    }
    if (url === "https://csc.example.gov.ph/downloads/CSE-list.pdf") {
      return init.method === "HEAD"
        ? new Response(null, { status: 200, headers: { "content-type": "application/pdf" } })
        : new Response("%PDF-1.7\\nverified", { status: 206 });
    }
    return new Response(null, { status: 404 });
  });
  const report = await runScheduled({ env, fetchImpl, scheduledTime: Date.UTC(2026, 10, 2) });
  assert.equal(report.first_check.results[0].status, "changed");
  assert.equal(dispatches.length, 1);
  assert.equal(dispatches[0].client_payload.detected_url, "https://csc.example.gov.ph/downloads/CSE-list.pdf");
});

test("baseline scan dispatches only the two exact owner-approved Google Drive IDs", async () => {
  const ids = [
    "1jQmBLSU2azhFvCgU6l8m6ljXGDmIRa1l",
    "1qYaCbxIZ_6DHyMD9FhgZdj-YtbIJh5Wf"
  ];
  const source = approvedSource({
    drive_file_ids: ids,
    scan_page_on_baseline: true,
    url: "https://www.csc.gov.ph/regional-offices/region-v/examination/results-10072026"
  });
  const { fetchImpl, dispatches } = githubFetch([source], async (url, init) => {
    if (url === source.url && init.method === "HEAD") {
      return new Response(null, { status: 200, headers: { etag: '"stable"', "content-type": "text/html" } });
    }
    if (url === source.url && init.method === "GET") {
      return new Response(
        ids.map((id) => '<a href="https://drive.google.com/file/d/' + id + '/view?usp=drive_link">PDF</a>').join("") +
        '<a href="https://drive.google.com/file/d/not-approved-000000/view">Ignore</a>',
        { status: 200, headers: { "content-type": "text/html" } }
      );
    }
    if (url.startsWith("https://drive.google.com/uc?export=download&id=")) {
      const id = new URL(url).searchParams.get("id");
      return new Response(null, {
        status: 302,
        headers: { location: "https://drive.usercontent.google.com/download?id=" + id + "&export=download" }
      });
    }
    if (url.startsWith("https://drive.usercontent.google.com/download?id=")) {
      return new Response("%PDF-1.7\\nverified test PDF", {
        status: 206, headers: { "content-type": "application/pdf" }
      });
    }
    throw new Error("Unexpected external request: " + url);
  });
  const report = await runScheduled({ env: envFor(), fetchImpl, scheduledTime: Date.UTC(2026, 10, 2) });
  assert.equal(report.first_check.results[0].status, "baseline_created");
  assert.equal(dispatches.length, 2);
  assert.deepEqual(
    dispatches.map((item) => new URL(item.client_payload.detected_url).searchParams.get("id")).sort(),
    ids.slice().sort()
  );
  assert.ok(dispatches.every((item) => item.client_payload.content_type === "application/pdf"));
});

test("official source HEAD 403 falls back to bounded GET on the same origin", async () => {
  const source = approvedSource();
  const methods = [];
  const { fetchImpl } = githubFetch([source], async (url, init) => {
    methods.push({ url, method: init.method, range: new Headers(init.headers).get("range") });
    if (init.method === "HEAD") return new Response(null, { status: 403 });
    return new Response("<html>Official results page</html>", {
      status: 200, headers: { "content-type": "text/html" }
    });
  });
  const report = await runScheduled({ env: envFor(), fetchImpl });
  assert.equal(report.first_check.results[0].status, "baseline_created");
  assert.deepEqual(methods.map((item) => item.method), ["HEAD", "GET"]);
  assert.equal(methods[1].range, "bytes=0-1023");
  assert.equal(methods[1].url, source.url);
});

test("approved Drive ID returning HTML is not dispatched as a PDF", async () => {
  const id = "1jQmBLSU2azhFvCgU6l8m6ljXGDmIRa1l";
  const source = approvedSource({
    drive_file_ids: [id], scan_page_on_baseline: true,
    url: "https://csc.example.gov.ph/results"
  });
  const { fetchImpl, dispatches } = githubFetch([source], async (url, init) => {
    if (url === source.url && init.method === "HEAD") {
      return new Response(null, { status: 200, headers: { etag: '"stable"', "content-type": "text/html" } });
    }
    if (url === source.url && init.method === "GET") {
      return new Response('<a href="https://drive.google.com/file/d/' + id + '/view">PDF</a>', {
        status: 200, headers: { "content-type": "text/html" }
      });
    }
    if (url.startsWith("https://drive.google.com/uc?")) {
      return new Response("<html>Access denied</html>", {
        status: 200, headers: { "content-type": "text/html" }
      });
    }
    throw new Error("Unexpected request: " + url);
  });
  const report = await runScheduled({ env: envFor(), fetchImpl });
  assert.equal(report.first_check.results[0].status, "baseline_created");
  assert.equal(report.first_check.results[0].pdf_results[0].status, "pdf_verification_failed_manual_review_required");
  assert.equal(dispatches.length, 0);
});

test("Google Drive redirects to an unapproved host are held for manual review", async () => {
  const id = "1jQmBLSU2azhFvCgU6l8m6ljXGDmIRa1l";
  const source = approvedSource({
    drive_file_ids: [id], scan_page_on_baseline: true,
    url: "https://csc.example.gov.ph/results"
  });
  const { fetchImpl, dispatches } = githubFetch([source], async (url, init) => {
    if (url === source.url && init.method === "HEAD") {
      return new Response(null, { status: 200, headers: { etag: '"stable"', "content-type": "text/html" } });
    }
    if (url === source.url && init.method === "GET") {
      return new Response('<a href="https://drive.google.com/file/d/' + id + '/view">PDF</a>', {
        status: 200, headers: { "content-type": "text/html" }
      });
    }
    if (url.startsWith("https://drive.google.com/uc?")) {
      return new Response(null, {
        status: 302, headers: { location: "https://malicious.example/download?id=" + id }
      });
    }
    throw new Error("Unexpected request: " + url);
  });
  const report = await runScheduled({ env: envFor(), fetchImpl });
  assert.equal(report.first_check.results[0].pdf_results[0].status, "pdf_verification_error_manual_review_required");
  assert.match(report.first_check.results[0].pdf_results[0].error, /Google Drive redirect rejected/);
  assert.equal(dispatches.length, 0);
});

test("same-origin PDF links require a real PDF byte signature", async () => {
  const source = approvedSource();
  const env = envFor();
  const { createHash } = await import("node:crypto");
  const hex = createHash("sha256").update(`${source.id}\n${source.url}`).digest("hex");
  await env.PEAK_WEEK.put(
    `baseline:${hex}`,
    JSON.stringify({ status: 200, contentType: "text/html", etag: '"v1"', lastModified: "", contentLength: "" })
  );
  const { fetchImpl, dispatches } = githubFetch([source], async (url, init) => {
    if (url === source.url && init.method === "HEAD") {
      return new Response(null, { status: 200, headers: { etag: '"v2"', "content-type": "text/html" } });
    }
    if (url === source.url && init.method === "GET") {
      return new Response('<a href="/downloads/not-really-a-pdf.pdf">Download</a>', {
        status: 200, headers: { "content-type": "text/html" }
      });
    }
    if (url.endsWith("/downloads/not-really-a-pdf.pdf")) {
      return init.method === "HEAD"
        ? new Response(null, { status: 200, headers: { "content-type": "application/pdf" } })
        : new Response("<html>Access denied</html>", { status: 200, headers: { "content-type": "text/html" } });
    }
    return new Response(null, { status: 404 });
  });
  const report = await runScheduled({ env, fetchImpl });
  assert.equal(report.first_check.results[0].pdf_results[0].status, "pdf_verification_failed_manual_review_required");
  assert.equal(dispatches.length, 0);
});

test("a PDF URL returning an HTML page is not dispatched", async () => {
  const source = approvedSource({ url: "https://csc.example.gov.ph/fake.pdf" });
  const { fetchImpl, dispatches } = githubFetch([source], async () => new Response(null, {
    status: 200, headers: { "content-type": "text/html" }
  }));
  const report = await runScheduled({ env: envFor(), fetchImpl });
  assert.equal(report.first_check.results[0].status, "not_pdf");
  assert.equal(dispatches.length, 0);
});

test("failed GitHub dispatch is not marked complete and can retry", async () => {
  const source = approvedSource({ url: "https://csc.example.gov.ph/current-list.pdf" });
  let dispatchAttempts = 0;
  const fetchImpl = async (input, init = {}) => {
    const url = String(input);
    if (url.includes("/contents/")) return registryResponse([source]);
    if (url.endsWith("/dispatches")) {
      dispatchAttempts += 1;
      return dispatchAttempts === 1
        ? new Response("temporary failure", { status: 500 })
        : new Response(null, { status: 204 });
    }
    return init.method === "HEAD"
      ? new Response(null, { status: 200, headers: { "content-type": "application/pdf" } })
      : new Response("%PDF-1.7\\nverified", { status: 206 });
  };
  const env = envFor();
  const first = await runScheduled({ env, fetchImpl });
  const second = await runScheduled({ env, fetchImpl });
  assert.equal(first.first_check.results[0].status, "dispatch_error");
  assert.equal(second.first_check.results[0].status, "dispatched");
  assert.equal(dispatchAttempts, 2);
});


test("verified third-party sources are skipped while an official source is reachable", async () => {
  const official = approvedSource();
  const thirdParty = approvedSource({
    id: "mirror", source_type: "verified_third_party", authorized: undefined,
    verified_by_owner: true, url: "https://mirror.example.gov.ph/results"
  });
  const { fetchImpl } = githubFetch([official, thirdParty], async (url) => {
    assert.notEqual(url, thirdParty.url, "third-party source must not be requested");
    return new Response(null, { status: 200, headers: { etag: '"official"', "content-type": "text/html" } });
  });
  const report = await runScheduled({ env: envFor(), fetchImpl });
  assert.equal(report.first_check.results[0].status, "baseline_created");
  assert.equal(report.first_check.results[1].status, "skipped_official_available");
});

test("verified third-party fallback is checked when the configured official source is unavailable", async () => {
  const official = approvedSource();
  const thirdParty = approvedSource({
    id: "mirror", source_type: "verified_third_party", authorized: undefined,
    verified_by_owner: true, url: "https://mirror.example.gov.ph/results.pdf"
  });
  const { fetchImpl, dispatches } = githubFetch([official, thirdParty], async (url, init) => {
    if (url === official.url) return new Response(null, { status: 503 });
    return init.method === "HEAD"
      ? new Response(null, { status: 200, headers: { "content-type": "application/pdf" } })
      : new Response("%PDF-1.7\\nverified", { status: 206 });
  });
  const report = await runScheduled({ env: envFor(), fetchImpl });
  assert.equal(report.first_check.results[0].http_status, 503);
  assert.equal(report.first_check.results[1].status, "dispatched");
  assert.equal(dispatches.length, 1);
});

test("third-party source is not used when no official source is configured", async () => {
  const mirror = approvedSource({
    id: "mirror", source_type: "verified_third_party", authorized: undefined,
    verified_by_owner: true, url: "https://mirror.example.gov.ph/results.pdf"
  });
  let requests = 0;
  const { fetchImpl } = githubFetch([mirror], async () => {
    requests += 1;
    return new Response(null, { status: 200 });
  });
  const report = await runScheduled({ env: envFor(), fetchImpl });
  assert.equal(report.first_check.results[0].status, "skipped_no_official_source_configured");
  assert.equal(requests, 0);
});


test("Peak Week safety budget counts HTTP and KV subrequests together", async () => {
  class CountingKV extends MemoryKV {
    calls = 0;
    async get(key) { this.calls += 1; return super.get(key); }
    async put(key, value, options) { this.calls += 1; return super.put(key, value, options); }
  }
  const sources = Array.from({ length: 12 }, (_, index) => approvedSource({
    id: `csc-cse-${index + 1}`,
    url: `https://csc.example.gov.ph/exam-results/${index + 1}`
  }));
  let fetchCalls = 0;
  const mocked = githubFetch(sources, async (_url, init) => {
    assert.equal(init.method, "HEAD");
    return new Response(null, {
      status: 200,
      headers: { etag: '"stable"', "content-type": "text/html" }
    });
  });
  const fetchImpl = async (...args) => {
    fetchCalls += 1;
    return mocked.fetchImpl(...args);
  };
  const env = envFor(true);
  const kv = new CountingKV({ PEAK_WEEK: "true" });
  env.PEAK_WEEK = kv;
  const report = await runScheduled({
    env, fetchImpl, sleepImpl: async () => {},
    scheduledTime: Date.UTC(2026, 10, 2)
  });
  assert.equal(report.mode, "peak_week");
  assert.equal(report.outbound_subrequest_safety_limit, 45);
  assert.equal(report.outbound_subrequests_used, 45);
  assert.equal(fetchCalls + kv.calls, report.outbound_subrequests_used);
  assert.ok(report.outbound_subrequests_used <= 45);
  assert.ok(report.second_check.results.some((item) => item.status === "subrequest_budget_reached" || item.status === "check_error"));
});


test("CSC 403 falls back to exact owner-approved Google Drive IDs without scraping the blocked page", async () => {
  const ids = [
    "1jQmBLSU2azhFvCgU6l8m6ljXGDmIRa1l",
    "1qYaCbxIZ_6DHyMD9FhgZdj-YtbIJh5Wf",
    "short-id",
    "1jQmBLSU2azhFvCgU6l8m6ljXGDmIRa1l"
  ];
  const source = approvedSource({
    drive_file_ids: ids,
    url: "https://www.csc.gov.ph/regional-offices/region-v/examination/results-10072026"
  });
  const env = envFor();
  env.GITHUB_EVENT_TYPE = "staging-source-detected";
  const { fetchImpl, dispatches } = githubFetch([source], async (url, init) => {
    if (url === source.url) {
      assert.ok(["HEAD", "GET"].includes(init.method));
      return new Response(null, { status: 403 });
    }
    if (url.startsWith("https://drive.google.com/uc?export=download&id=")) {
      const id = new URL(url).searchParams.get("id");
      return new Response(null, {
        status: 302,
        headers: { location: "https://drive.usercontent.google.com/download?id=" + id + "&export=download" }
      });
    }
    if (url.startsWith("https://drive.usercontent.google.com/download?id=")) {
      return new Response("%PDF-1.7\\nverified test PDF", {
        status: 206, headers: { "content-type": "application/pdf" }
      });
    }
    throw new Error("Unexpected request: " + url);
  });
  const report = await runScheduled({ env, fetchImpl, scheduledTime: Date.UTC(2026, 10, 2) });
  const result = report.first_check.results[0];
  assert.equal(result.status, "http_error");
  assert.equal(result.http_status, 403);
  assert.equal(result.fallback, "approved_drive_ids");
  assert.equal(result.pdf_results.length, 2);
  assert.ok(result.pdf_results.every((item) => item.status === "dispatched"));
  assert.equal(dispatches.length, 2);
  assert.ok(dispatches.every((item) => item.event_type === "staging-source-detected"));
  assert.ok(dispatches.every((item) => item.client_payload.detection_method === "approved_drive_id_fallback"));
  assert.deepEqual(
    dispatches.map((item) => new URL(item.client_payload.detected_url).searchParams.get("id")).sort(),
    ids.slice(0, 2).sort()
  );
});

test("CSC 403 direct Drive fallback still rejects non-PDF content", async () => {
  const id = "1jQmBLSU2azhFvCgU6l8m6ljXGDmIRa1l";
  const source = approvedSource({ drive_file_ids: [id] });
  const env = envFor();
  env.GITHUB_EVENT_TYPE = "staging-source-detected";
  const { fetchImpl, dispatches } = githubFetch([source], async (url) => {
    if (url === source.url) return new Response(null, { status: 403 });
    if (url.startsWith("https://drive.google.com/uc?")) {
      return new Response(null, {
        status: 302,
        headers: { location: "https://drive.usercontent.google.com/download?id=" + id + "&export=download" }
      });
    }
    if (url.startsWith("https://drive.usercontent.google.com/download?id=")) {
      return new Response("<html>Access denied</html>", { status: 200 });
    }
    throw new Error("Unexpected request: " + url);
  });
  const report = await runScheduled({ env, fetchImpl });
  assert.equal(report.first_check.results[0].pdf_results[0].status, "pdf_verification_failed_manual_review_required");
  assert.equal(dispatches.length, 0);
});


test("manual scan endpoint requires the Preview bearer token", async () => {
  const env = envFor();
  env.GITHUB_EVENT_TYPE = "staging-source-detected";
  env.STAGING_SCAN_TOKEN = "preview-test-secret";
  const response = await worker.fetch(new Request("https://preview.example/__staging/scan", {
    method: "POST"
  }), env);
  assert.equal(response.status, 401);
});

test("manual scan endpoint is unavailable outside Worker Previews", async () => {
  const env = envFor();
  env.GITHUB_EVENT_TYPE = "production";
  env.STAGING_SCAN_TOKEN = "preview-test-secret";
  const response = await worker.fetch(new Request("https://worker.example/__staging/scan", {
    method: "POST",
    headers: { authorization: "Bearer preview-test-secret" }
  }), env);
  assert.equal(response.status, 404);
});
