import test from "node:test";
import assert from "node:assert/strict";
import { runScheduled, expandPreemptiveTemplates, classifySourceOutcome, fetchOfficialArticleMetadata } from "../src/index.js";
import worker from "../src/index.js";

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

async function runApprovedDriveFallback(eventType) {
  const ids = [
    "1jQmBLSU2azhFvCgU6l8m6ljXGDmIRa1l",
    "1qYaCbxIZ_6DHyMD9FhgZdj-YtbIJh5Wf"
  ];
  const source = approvedSource({
    url: "https://www.csc.gov.ph/regional-offices/region-v/examination/results-10072026",
    drive_file_ids: ids,
    direct_drive_fallback: true
  });
  const env = envFor();
  if (eventType) env.GITHUB_EVENT_TYPE = eventType;
  const { fetchImpl, dispatches } = githubFetch([source], async (url) => {
    if (url === source.url) return new Response("Forbidden", { status: 403 });
    if (url.startsWith("https://drive.google.com/uc?export=download&id=")) {
      const id = new URL(url).searchParams.get("id");
      return new Response(null, {
        status: 302,
        headers: { location: "https://drive.usercontent.google.com/download?id=" + id + "&export=download" }
      });
    }
    if (url.startsWith("https://drive.usercontent.google.com/download?id=")) {
      return new Response("%PDF-1.7\\nverified fallback PDF", { status: 206 });
    }
    throw new Error("Unexpected request: " + url);
  });
  const report = await runScheduled({ env, fetchImpl, scheduledTime: Date.UTC(2026, 10, 2) });
  return { ids, report, dispatches };
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

test.skip("CSC 403 production fallback dispatches only exact approved Drive IDs to the production receiver", async () => {
  const { ids, report, dispatches } = await runApprovedDriveFallback();
  const result = report.first_check.results[0];
  assert.equal(result.status, "http_error_drive_fallback_recovered");
  assert.equal(result.http_status, 403);
  assert.equal(result.drive_fallback_results.length, 2);
  assert.ok(result.drive_fallback_results.every((item) => item.status === "dispatched"));
  assert.equal(dispatches.length, 2);
  assert.ok(dispatches.every((item) => item.event_type === "source-detected"));
  assert.ok(dispatches.every((item) => item.client_payload.detection_method === "approved_drive_fallback"));
  assert.deepEqual(
    dispatches.map((item) => new URL(item.client_payload.detected_url).searchParams.get("id")).sort(),
    ids.slice().sort()
  );
});

test.skip("CSC 403 fallback in preview preserves the isolated staging event type", async () => {
  const { report, dispatches } = await runApprovedDriveFallback("staging-source-detected");
  assert.equal(report.first_check.results[0].status, "http_error_drive_fallback_recovered");
  assert.equal(dispatches.length, 2);
  assert.ok(dispatches.every((item) => item.event_type === "staging-source-detected"));
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



test("official-page discovery retries a normal GET when HEAD and Range GET are blocked", async () => {
  const discoveredId = "1NormalGetFallbackOfficialFile_2026";
  const source = approvedSource({
    url: "https://csc.gov.ph/regional-offices/region-v/examination",
    allow_linked_drive_documents: true,
    scan_page_on_baseline: true,
    drive_file_ids: []
  });
  const html = '<a href="https://drive.google.com/file/d/' + discoveredId + '/view">Official List of Passers</a>';
  const { fetchImpl, dispatches } = githubFetch([source], async (url, init) => {
    if (url === source.url && init.method === "HEAD") {
      return new Response(null, { status: 403 });
    }
    if (url === source.url && init.method === "GET" && init.headers?.Range) {
      return new Response(null, { status: 403 });
    }
    if (url === source.url && init.method === "GET") {
      return new Response(html, { status: 200, headers: { etag: '"normal-get"', "content-type": "text/html" } });
    }
    if (url === "https://drive.google.com/uc?export=download&id=" + discoveredId) {
      return new Response(null, {
        status: 302,
        headers: { location: "https://drive.usercontent.google.com/download?id=" + discoveredId + "&export=download" }
      });
    }
    if (url === "https://drive.usercontent.google.com/download?id=" + discoveredId + "&export=download") {
      return new Response("%PDF-1.7\\nnormal GET fallback PDF", { status: 206 });
    }
    throw new Error("Unexpected request: " + url);
  });
  const report = await runScheduled({ env: envFor(), fetchImpl, scheduledTime: Date.UTC(2026, 10, 2) });
  assert.equal(report.first_check.results[0].status, "baseline_created");
  assert.equal(dispatches.length, 1);
  assert.equal(dispatches[0].client_payload.detection_method, "official_page_drive_link");
  assert.equal(dispatches[0].client_payload.source_page_url, source.url);
});

test("owner-enabled official-page Drive discovery verifies and dispatches a newly linked PDF", async () => {
  const discoveredId = "1NewlyPublishedOfficialDriveFile_2026";
  const source = approvedSource({
    url: "https://www.prc.gov.ph/article/official-results-announcement",
    allow_linked_drive_documents: true,
    scan_page_on_baseline: true,
    drive_file_ids: []
  });
  const { fetchImpl, dispatches } = githubFetch([source], async (url, init) => {
    if (url === source.url && init.method === "HEAD") {
      return new Response(null, { status: 200, headers: { etag: '"stable"', "content-type": "text/html" } });
    }
    if (url === source.url && init.method === "GET") {
      return new Response(
        '<a href="https://drive.google.com/file/d/' + discoveredId + '/view?usp=sharing">Official list</a>' +
        '<a href="https://evil.example/file/d/attackerfile000/view">Hostile link</a>' +
        '<a href="https://drive.google.com/open?id=anotherfile000000">Unsupported Drive format</a>',
        { status: 200, headers: { "content-type": "text/html" } }
      );
    }
    if (url === "https://drive.google.com/uc?export=download&id=" + discoveredId) {
      return new Response(null, {
        status: 302,
        headers: { location: "https://drive.usercontent.google.com/download?id=" + discoveredId + "&export=download" }
      });
    }
    if (url === "https://drive.usercontent.google.com/download?id=" + discoveredId + "&export=download") {
      return new Response("%PDF-1.7\\nverified official page PDF", { status: 206 });
    }
    throw new Error("Unexpected request: " + url);
  });
  const report = await runScheduled({ env: envFor(), fetchImpl, scheduledTime: Date.UTC(2026, 10, 2) });
  assert.equal(report.first_check.results[0].status, "baseline_created");
  assert.equal(dispatches.length, 1);
  assert.equal(dispatches[0].client_payload.detection_method, "official_page_drive_link");
  assert.equal(dispatches[0].client_payload.source_page_url, source.url);
  assert.equal(dispatches[0].client_payload.detected_url,
    "https://drive.google.com/uc?export=download&id=" + discoveredId);
});



test("owner-configured Drive link labels select only the successful-examinees document", async () => {
  const targetId = "1SuccessfulExamineesList_2026";
  const source = approvedSource({
    url: "https://www.prc.gov.ph/article/official-exam-results",
    allow_linked_drive_documents: true,
    drive_link_text_patterns: ["list of successful examinees"],
    scan_page_on_baseline: true,
    drive_file_ids: []
  });
  const html = [
    '<a href="https://drive.google.com/file/d/1FullOfficialResultDocument_2026/view">Full text of the Official Result</a>',
    '<a href="https://drive.google.com/file/d/1PerformanceOfSchoolsDoc_2026/view">Performance of Schools</a>',
    '<a href="https://drive.google.com/file/d/1TopTenHighestPlacesDoc_2026/view">Successful Examinees who garnered the top 10 highest places</a>',
    '<a href="https://drive.google.com/file/d/' + targetId + '/view">List of Successful Examinees</a>'
  ].join("");
  const { fetchImpl, dispatches } = githubFetch([source], async (url, init) => {
    if (url === source.url && init.method === "HEAD") {
      return new Response(null, { status: 200, headers: { etag: '"prc-results"', "content-type": "text/html" } });
    }
    if (url === source.url && init.method === "GET") {
      return new Response(html, { status: 200, headers: { "content-type": "text/html" } });
    }
    if (url === "https://drive.google.com/uc?export=download&id=" + targetId) {
      return new Response(null, {
        status: 302,
        headers: { location: "https://drive.usercontent.google.com/download?id=" + targetId + "&export=download" }
      });
    }
    if (url === "https://drive.usercontent.google.com/download?id=" + targetId + "&export=download") {
      return new Response("%PDF-1.7\\nsuccessful examinees only", { status: 206 });
    }
    if (url.includes("drive.google.com")) throw new Error("Non-target PRC attachment must not be fetched");
    throw new Error("Unexpected request: " + url);
  });
  const report = await runScheduled({ env: envFor(), fetchImpl, scheduledTime: Date.UTC(2026, 10, 2) });
  assert.equal(report.first_check.results[0].status, "baseline_created");
  assert.equal(dispatches.length, 1);
  assert.equal(dispatches[0].client_payload.detected_url,
    "https://drive.google.com/uc?export=download&id=" + targetId);
});

test("owner-enabled official-page discovery finds plain-text Drive URLs without accepting lookalike hosts", async () => {
  const discoveredId = "1PlainTextOfficialDriveFile_2026";
  const source = approvedSource({
    url: "https://csc.gov.ph/regional-offices/region-v/examination",
    allow_linked_drive_documents: true,
    scan_page_on_baseline: true,
    drive_file_ids: []
  });
  const html =
    '<div>Professional: https://drive.google.com/file/d/' + discoveredId + '/view?usp=drive_link</div>' +
    '<div>Hostile: https://drive.google.com.evil.example/file/d/attackerfile000/view</div>';
  const { fetchImpl, dispatches } = githubFetch([source], async (url, init) => {
    if (url === source.url && init.method === "HEAD") {
      return new Response(null, { status: 200, headers: { etag: '"plain-text"', "content-type": "text/html" } });
    }
    if (url === source.url && init.method === "GET") {
      return new Response(html, { status: 200, headers: { "content-type": "text/html" } });
    }
    if (url === "https://drive.google.com/uc?export=download&id=" + discoveredId) {
      return new Response(null, {
        status: 302,
        headers: { location: "https://drive.usercontent.google.com/download?id=" + discoveredId + "&export=download" }
      });
    }
    if (url === "https://drive.usercontent.google.com/download?id=" + discoveredId + "&export=download") {
      return new Response("%PDF-1.7\\nplain-text official PDF", { status: 206 });
    }
    if (url.includes("drive.google.com.evil.example")) throw new Error("Lookalike host must never be fetched");
    throw new Error("Unexpected request: " + url);
  });
  const report = await runScheduled({ env: envFor(), fetchImpl, scheduledTime: Date.UTC(2026, 10, 2) });
  assert.equal(report.first_check.results[0].status, "baseline_created");
  assert.equal(dispatches.length, 1);
  assert.equal(dispatches[0].client_payload.detection_method, "official_page_drive_link");
  assert.equal(dispatches[0].client_payload.source_page_url, source.url);
});


test("opt-in PRC listing discovery scans only same-origin result articles and verifies their Drive PDFs", async () => {
  const discoveredId = "1PRCArticleOfficialDriveFile2026";
  const listingUrl = "https://www.prc.gov.ph/articles/exam-results";
  const articleUrl = "https://www.prc.gov.ph/node/9450";
  const source = approvedSource({
    id: "prc-exam-results",
    authority: "PRC",
    exam: "PRC-LICENSURE",
    url: listingUrl,
    scan_page_on_baseline: true,
    allow_linked_drive_documents: true,
    discover_official_result_articles: true,
    drive_file_ids: []
  });
  const listingHtml =
    '<a href="/node/9450">October 2026 Physicians Licensure Examination Results Released In Four Working Days</a>' +
    '<a href="/article/oathtaking">Face-to-Face Oathtaking of New Chemists</a>' +
    '<a href="https://evil.example/node/999">October 2026 Examination Results Released</a>';
  const articleHtml =
    '<h1>October 2026 Certified Public Accountants Licensure Examination Results Released</h1>' +
    '<a href="https://drive.google.com/file/d/' + discoveredId + '/view?usp=sharing">List of Successful Examinees</a>';
  const ingestUrl = "https://ph-exam-results.pages.dev/api/test-mode/events";
  let ingestRequest = null;
  const { fetchImpl, dispatches } = githubFetch([source], async (url, init) => {
    if (url === ingestUrl) {
      ingestRequest = { headers: init.headers, body: JSON.parse(init.body) };
      return new Response(JSON.stringify({ event_id: "prc_0123456789abcdef0123456789abcdef", duplicate: false }), { status: 201 });
    }
    if (url === listingUrl && init.method === "HEAD") {
      return new Response(null, { status: 200, headers: { etag: '"listing-v1"', "content-type": "text/html" } });
    }
    if (url === listingUrl && init.method === "GET") {
      return new Response(listingHtml, { status: 200, headers: { "content-type": "text/html" } });
    }
    if (url === articleUrl && init.method === "GET") {
      return new Response(articleHtml, { status: 200, headers: { "content-type": "text/html" } });
    }
    if (url === "https://drive.google.com/uc?export=download&id=" + discoveredId) {
      return new Response(null, {
        status: 302,
        headers: { location: "https://drive.usercontent.google.com/download?id=" + discoveredId + "&export=download" }
      });
    }
    if (url === "https://drive.usercontent.google.com/download?id=" + discoveredId + "&export=download") {
      return new Response("%PDF-1.7\\nPRC official article PDF", { status: 206 });
    }
    if (url.includes("evil.example")) throw new Error("Cross-origin article must never be fetched");
    throw new Error("Unexpected request: " + url);
  });
  const env = envFor();
  env.TEST_MODE_EVENT_INGEST_URL = ingestUrl;
  env.TEST_MODE_EVENT_INGEST_TOKEN = "t".repeat(40);
  const report = await runScheduled({ env, fetchImpl, scheduledTime: Date.UTC(2026, 10, 2) });
  assert.equal(report.first_check.results[0].status, "baseline_created");
  assert.equal(dispatches.length, 1);
  assert.equal(dispatches[0].event_type, "prc-release-detected");
  assert.equal(ingestRequest.headers.Authorization, "Bearer " + "t".repeat(40));
  assert.equal(ingestRequest.body.authority, "PRC");
  assert.equal(ingestRequest.body.source_id, "prc-exam-results");
  assert.equal(ingestRequest.body.article_url, articleUrl);
  assert.equal(dispatches[0].client_payload.event.exam_code, "CPALE");
  assert.equal(dispatches[0].client_payload.event.exam_year, 2026);
  assert.equal(dispatches[0].client_payload.event.article_url, articleUrl);
  assert.equal(dispatches[0].client_payload.event.content_urls[0].format, "pdf");
  assert.equal(dispatches[0].client_payload.event.content_urls[0].url,
    "https://drive.google.com/file/d/" + discoveredId + "/view?usp=sharing");
});

test("PRC article discovery stays off unless explicitly enabled by the approved source", async () => {
  const listingUrl = "https://www.prc.gov.ph/articles/exam-results";
  const source = approvedSource({
    id: "prc-exam-results",
    authority: "PRC",
    exam: "PRC-LICENSURE",
    url: listingUrl,
    scan_page_on_baseline: true,
    allow_linked_drive_documents: true,
    discover_official_result_articles: false,
    drive_file_ids: []
  });
  const { fetchImpl, dispatches } = githubFetch([source], async (url, init) => {
    if (url === listingUrl && init.method === "HEAD") {
      return new Response(null, { status: 200, headers: { etag: '"listing-v1"', "content-type": "text/html" } });
    }
    if (url === listingUrl && init.method === "GET") {
      return new Response('<a href="/node/9450">October 2026 Physicians Licensure Examination Results Released</a>', {
        status: 200, headers: { "content-type": "text/html" }
      });
    }
    if (url.includes("/node/")) throw new Error("Article must not be fetched without explicit opt-in");
    throw new Error("Unexpected request: " + url);
  });
  const report = await runScheduled({ env: envFor(), fetchImpl, scheduledTime: Date.UTC(2026, 10, 2) });
  assert.equal(report.first_check.results[0].status, "baseline_created");
  assert.equal(dispatches.length, 0);
});

test("new Drive IDs linked from official pages remain blocked unless owner enables discovery", async () => {
  const discoveredId = "1UnapprovedDiscoveryMustNotDispatch";
  const source = approvedSource({
    url: "https://www.prc.gov.ph/article/official-results-announcement",
    allow_linked_drive_documents: false,
    scan_page_on_baseline: true,
    drive_file_ids: []
  });
  let driveRequests = 0;
  const { fetchImpl, dispatches } = githubFetch([source], async (url, init) => {
    if (url === source.url && init.method === "HEAD") {
      return new Response(null, { status: 200, headers: { etag: '"stable"', "content-type": "text/html" } });
    }
    if (url === source.url && init.method === "GET") {
      return new Response(
        '<a href="https://drive.google.com/file/d/' + discoveredId + '/view">Official list</a>',
        { status: 200, headers: { "content-type": "text/html" } }
      );
    }
    if (url.includes("drive.google.com")) driveRequests += 1;
    return new Response(null, { status: 404 });
  });
  const report = await runScheduled({ env: envFor(), fetchImpl, scheduledTime: Date.UTC(2026, 10, 2) });
  assert.equal(report.first_check.results[0].status, "baseline_created");
  assert.equal(driveRequests, 0);
  assert.equal(dispatches.length, 0);
});






test("PRC listing snapshots historical pages and processes newly posted result articles in bounded batches", async () => {
  const source = approvedSource({
    id: "PRC-EXAM-RESULTS-HOMEPAGE",
    authority: "PRC",
    exam: "LICENSURE-EXAM-RESULTS",
    url: "https://www.prc.gov.ph/articles/exam-results",
    scan_page_on_baseline: false,
    allow_linked_drive_documents: true,
    discover_official_result_articles: true,
    track_new_articles_only: true,
    result_listing_page_count: 3,
    max_result_articles_per_page: 10,
    max_new_result_articles_per_scan: 3,
    drive_link_text_patterns: ["list of successful examinees"],
    drive_file_ids: []
  });
  const oldArticles = [
    "https://www.prc.gov.ph/node/9450",
    "https://www.prc.gov.ph/node/9451",
    "https://www.prc.gov.ph/node/9452",
    "https://www.prc.gov.ph/node/9453",
    "https://www.prc.gov.ph/node/9454",
    "https://www.prc.gov.ph/node/9455"
  ];
  const newArticles = [
    "https://www.prc.gov.ph/node/9990",
    "https://www.prc.gov.ph/node/9991",
    "https://www.prc.gov.ph/node/9992",
    "https://www.prc.gov.ph/node/9993"
  ];
  const driveIds = [
    "1PRCNewSuccessfulExamineesResultA2026",
    "1PRCNewSuccessfulExamineesResultB2026",
    "1PRCNewSuccessfulExamineesResultC2026",
    "1PRCNewSuccessfulExamineesResultD2026"
  ];
  let listingVersion = 1;
  const env = envFor();
  const anchors = (urls, label) => urls.map((url) =>
    '<a href="' + url.replace("https://www.prc.gov.ph", "") + '">' + label + '</a>'
  ).join("");
  const listingPage = (pageIndex) => {
    if (pageIndex === 0) {
      const urls = listingVersion === 1
        ? oldArticles.slice(0, 2)
        : [...newArticles, ...oldArticles.slice(0, 2)];
      return anchors(urls, "November 2026 Licensure Examination Results Released") +
        '<a href="https://evil.example/node/999">November 2026 Licensure Examination Results Released</a>';
    }
    return anchors(oldArticles.slice(pageIndex * 2, pageIndex * 2 + 2),
      "October 2026 Licensure Examination Results Released");
  };
  const { fetchImpl, dispatches } = githubFetch([source], async (url, init = {}) => {
    if (url === source.url && init.method === "HEAD") {
      return new Response(null, { status: 200, headers: { etag: '"prc-listing-stable"', "content-type": "text/html" } });
    }
    if (url === source.url && init.method === "GET") {
      return new Response(listingPage(0), { status: 200, headers: { "content-type": "text/html" } });
    }
    if (url === source.url + "?page=1" && init.method === "GET") {
      return new Response(listingPage(1), { status: 200, headers: { "content-type": "text/html" } });
    }
    if (url === source.url + "?page=2" && init.method === "GET") {
      return new Response(listingPage(2), { status: 200, headers: { "content-type": "text/html" } });
    }
    const articleIndex = newArticles.indexOf(url);
    if (articleIndex >= 0 && init.method === "GET") {
      const titles = [
        "November 2026 Certified Public Accountants Licensure Examination Results Released",
        "November 2026 Nurse Licensure Examination Results Released",
        "November 2026 Criminologist Licensure Examination Results Released",
        "November 2026 Licensure Examination for Professional Teachers Secondary Results Released"
      ];
      const announcedText = articleIndex === 3
        ? '<p>The PRC announces that 45,001 secondary teachers out of 61,561 examinees successfully passed.</p>'
        : '<p>The PRC announces that 1,083 out of 1,503 examinees successfully passed.</p>';
      return new Response(
        '<h1>' + titles[articleIndex] + '</h1>' + announcedText +
        '<a href="https://drive.google.com/file/d/' + driveIds[articleIndex] + '/view">List of Successful Examinees</a>',
        { status: 200, headers: { "content-type": "text/html" } }
      );
    }
    if (oldArticles.includes(url)) throw new Error("Historical PRC article must never be opened for acquisition");
    if (url.startsWith("https://drive.google.com/uc?export=download&id=")) {
      const id = new URL(url).searchParams.get("id");
      return new Response(null, {
        status: 302,
        headers: { location: "https://drive.usercontent.google.com/download?id=" + id + "&export=download" }
      });
    }
    if (url.startsWith("https://drive.usercontent.google.com/download?id=")) {
      return new Response("%PDF-1.7\\nPRC official successful examinees", { status: 206 });
    }
    if (url.includes("evil.example")) throw new Error("Cross-origin result links must never be fetched");
    throw new Error("Unexpected PRC request: " + url + " " + init.method);
  });

  const baseline = await runScheduled({ env, fetchImpl, scheduledTime: Date.UTC(2026, 10, 3) });
  assert.equal(baseline.first_check.results[0].status, "baseline_created");
  assert.equal(baseline.first_check.results[0].discovered_article_count, 6);
  assert.equal(baseline.first_check.results[0].historical_articles_skipped, 6);
  assert.equal(dispatches.length, 0, "baseline must never import historical result PDFs");

  listingVersion = 2;
  const firstBatch = await runScheduled({ env, fetchImpl, scheduledTime: Date.UTC(2026, 10, 3, 0, 1) });
  assert.equal(firstBatch.first_check.results[0].status, "changed");
  assert.equal(dispatches.length, 3);
  assert.ok(firstBatch.first_check.results[0].pdf_results.some((item) => item.status === "article_batch_pending"));
  assert.ok(firstBatch.outbound_subrequests_used <= firstBatch.outbound_subrequest_safety_limit);

  const secondBatch = await runScheduled({ env, fetchImpl, scheduledTime: Date.UTC(2026, 10, 3, 0, 2) });
  assert.equal(secondBatch.first_check.results[0].status, "changed");
  assert.equal(dispatches.length, 4);
  assert.equal(dispatches[3].event_type, "prc-release-detected");
  assert.equal(dispatches[3].client_payload.event.exam_code, "LEPT");
  assert.equal(dispatches[3].client_payload.event.result_level, "secondary");
  assert.equal(dispatches[3].client_payload.event.article_url, newArticles[3]);
  assert.ok(secondBatch.outbound_subrequests_used <= secondBatch.outbound_subrequest_safety_limit);
});


test("official PRC article metadata keeps the visible label beside each linked document", async () => {
  const articleUrl = "https://www.prc.gov.ph/article/november-2026-veterinarians-computer-based-licensure-examination-results-released-one-1";
  const html = `
    <html><head><title>November 2026 Veterinarians Results Released | PRC</title></head>
    <body><article>
      <h5>November 2026 Veterinarians Computer-Based Licensure Examination Results Released</h5>
      <p>The PRC announces that 1,083 out of 1,503 passed the Veterinarians Computer-Based Licensure Examination.</p>
      <ul>
        <li><a href="https://drive.google.com/file/d/1FullTextOfficialResult2026/view">Full text of the Official Result</a></li>
        <li><a href="https://drive.google.com/file/d/1PerformanceSchools2026/view">Performance of Schools</a></li>
        <li><a href="https://drive.google.com/file/d/1TopTenSuccessfulExaminees2026/view">Successful Examinees who garnered the top 10 highest places</a></li>
        <li><a href="https://drive.google.com/file/d/1AlphabeticalRoster2026/view">List of Successful Examinees</a></li>
      </ul>
    </article></body></html>`;
  const result = await fetchOfficialArticleMetadata(articleUrl, async () =>
    new Response(html, { status: 200, headers: { "content-type": "text/html" } })
  );
  assert.equal(result.title, "November 2026 Veterinarians Results Released | PRC");
  assert.deepEqual(result.links.map((link) => link.label), [
    "Full text of the Official Result",
    "Performance of Schools",
    "Successful Examinees who garnered the top 10 highest places",
    "List of Successful Examinees"
  ]);
});

test("source activity classification is conservative and includes nested PDF outcomes", () => {
  assert.equal(classifySourceOutcome({ status: "unchanged" }), "success");
  assert.equal(classifySourceOutcome({ status: "article_snapshot_rebuilt_historical_skipped" }), "success");
  assert.equal(classifySourceOutcome({ status: "needs_human_review_no_dispatch" }), "blocked");
  assert.equal(classifySourceOutcome({ status: "official_listing_page_unavailable" }), "failed");
  assert.equal(classifySourceOutcome({ status: "article_has_no_matching_pdf_yet" }), "warning");
  assert.equal(classifySourceOutcome({ status: "changed", pdf_results: [{ status: "failed_pdf_check" }] }), "failed");
  assert.equal(classifySourceOutcome({ status: "changed", pdf_results: [{ status: "article_batch_pending" }] }), "warning");
  assert.equal(classifySourceOutcome({ status: "a_new_unrecognized_state" }), "warning");
});

test("scheduled Watcher discovers the nearest official PRC release and rejects its old public snapshot", async () => {
  const scheduleSource = {
    id: "PRC-OFFICIAL-SCHEDULE-INDEX",
    authority: "PRC",
    exam: "ALL-LICENSURE-EXAMS",
    source_type: "official_schedule_index",
    authorized: true,
    enabled: true,
    url: "https://www.prc.gov.ph/exam-schedules-menu",
    max_schedule_pages: 2
  };
  const scheduleHtml =
    '<table>' +
    '<tr><th>SEQ</th><th>NAME OF EXAMINATION</th><th>DATE/S OF EXAMINATION</th><th>DAY/S</th><th>TESTING CENTER/S</th><th colspan="2">APPLICATION PERIOD</th><th>TARGET DATE OF RELEASE OF EXAMINATION RESULTS</th><th>REQUIREMENTS</th></tr>' +
    '<tr><td>71</td><td>Veterinarians</td><td>November 04, 05, and 06, 2026</td><td>Wed, Thu, Fri</td><td>NCR</td><td>August 06, 2026</td><td>October 05, 2026</td><td>November 10, 2026</td><td>Click Here</td></tr>' +
    '<tr><td>72</td><td>Midwives</td><td>November 07 and 08, 2026</td><td>Sat, Sun</td><td>NCR</td><td>August 07, 2026</td><td>October 08, 2026</td><td>November 11, 2026</td><td>Click Here</td></tr>' +
    '</table>';
  const env = envFor();
  const { fetchImpl } = githubFetch([scheduleSource], async (url) => {
    if (url === "https://www.prc.gov.ph/robots.txt") {
      return new Response("User-agent: *\nAllow: /exam-schedules-menu\nAllow: /2026-schedule-examination\n", {
        status: 200, headers: { "content-type": "text/plain" }
      });
    }
    if (url === "https://www.prc.gov.ph/exam-schedules-menu") {
      return new Response('<a href="/2026-schedule-examination">2026</a>', {
        status: 200, headers: { "content-type": "text/html" }
      });
    }
    if (url === "https://www.prc.gov.ph/2026-schedule-examination") {
      return new Response(scheduleHtml, { status: 200, headers: { "content-type": "text/html" } });
    }
    throw new Error("Unexpected request: " + url);
  });
  const report = await runScheduled({
    env,
    fetchImpl,
    scheduledTime: Date.UTC(2026, 10, 8, 4)
  });
  assert.equal(report.schedule_discovery.status, "updated");
  assert.equal(report.schedule_discovery.nearest_release.exam, "Veterinarians");
  assert.equal(report.schedule_discovery.nearest_release.target_release_date, "2026-11-10");

  const response = await worker.fetch(
    new Request("https://watcher.example/api/releases/upcoming"),
    env
  );
  assert.equal(response.status, 503);
  const payload = await response.json();
  assert.equal(payload.status, "stale");
});

test("Watcher fans out LEPT rosters independently and retries only the list whose dispatch failed", async () => {
  const listingUrl = "https://www.prc.gov.ph/articles/exam-results";
  const articleUrl = "https://www.prc.gov.ph/article/march-2026-lept-results";
  const source = approvedSource({
    id: "PRC-EXAM-RESULTS-HOMEPAGE",
    authority: "PRC",
    exam: "LICENSURE-EXAM-RESULTS",
    url: listingUrl,
    scan_page_on_baseline: false,
    allow_linked_drive_documents: true,
    discover_official_result_articles: true,
    track_new_articles_only: true,
    result_listing_page_count: 1,
    max_result_articles_per_page: 10,
    max_new_result_articles_per_scan: 3,
    drive_file_ids: []
  });
  const articleHtml = `
    <html><body>
      <h1>March 2026 Licensure Examination for Professional Teachers Results Released</h1>
      <p>18,376 elementary teachers out of 32,796 examinees and 45,001 secondary teachers out of 61,561 examinees successfully passed.</p>
      <a href="https://drive.google.com/file/d/1FullTextOfficialResult/view">Full text of the Official Result</a>
      <a href="https://drive.google.com/file/d/1PerformanceSchools/view">Performance of Schools</a>
      <a href="https://drive.google.com/file/d/1Top10Elementary/view">Successful Examinees who garnered the top 10 highest places for Elementary</a>
      <a href="https://drive.google.com/file/d/1Top10Secondary/view">Successful Examinees who garnered the top 10 highest places for Secondary</a>
      <a href="https://drive.google.com/file/d/1ElementaryRoster/view">List of Successful Examinees for Elementary</a>
      <a href="https://drive.google.com/file/d/1SecondaryRoster/view">List of Successful Examinees for Secondary</a>
    </body></html>`;
  let listingVersion = 1;
  let failSecondaryOnce = true;
  const dispatchAttempts = [];
  const env = envFor();
  const fetchImpl = async (input, init = {}) => {
    const url = String(input);
    if (url.includes("api.github.com/repos/owner/repository/contents/")) {
      return registryResponse([source]);
    }
    if (url === "https://api.github.com/repos/owner/repository/dispatches") {
      const event = JSON.parse(init.body).client_payload.event;
      dispatchAttempts.push(event);
      if (event.result_level === "secondary" && failSecondaryOnce) {
        failSecondaryOnce = false;
        return new Response("temporary dispatch failure", { status: 500 });
      }
      return new Response(null, { status: 204 });
    }
    if (url === listingUrl && init.method === "HEAD") {
      return new Response(null, {
        status: 200,
        headers: { etag: `"listing-v${listingVersion}"`, "content-type": "text/html" }
      });
    }
    if (url === listingUrl && init.method === "GET") {
      const listingHtml = listingVersion === 1 ? "" :
        '<a href="' + articleUrl + '">March 2026 Licensure Examination for Professional Teachers Results Released</a>';
      return new Response(listingHtml, { status: 200, headers: { "content-type": "text/html" } });
    }
    if (url === articleUrl && init.method === "GET") {
      return new Response(articleHtml, { status: 200, headers: { "content-type": "text/html" } });
    }
    throw new Error("Unexpected request: " + url + " " + init.method);
  };

  const baseline = await runScheduled({ env, fetchImpl, scheduledTime: Date.UTC(2026, 10, 3) });
  assert.equal(baseline.first_check.results[0].status, "baseline_created");
  assert.equal(dispatchAttempts.length, 0);

  listingVersion = 2;
  const partial = await runScheduled({ env, fetchImpl, scheduledTime: Date.UTC(2026, 10, 3, 0, 1) });
  const partialResults = partial.first_check.results[0].pdf_results;
  assert.deepEqual(partialResults.map((item) => item.status), [
    "prc-release-event-dispatched",
    "dispatch_failed_manual_review_required"
  ]);
  assert.deepEqual(dispatchAttempts.map((event) => event.result_level), ["elementary", "secondary"]);
  assert.deepEqual(dispatchAttempts.map((event) => event.announced_count), [18376, 45001]);
  assert.deepEqual(dispatchAttempts.map((event) => event.content_urls[0].url), [
    "https://drive.google.com/file/d/1ElementaryRoster/view",
    "https://drive.google.com/file/d/1SecondaryRoster/view"
  ]);

  listingVersion = 3;
  const retried = await runScheduled({ env, fetchImpl, scheduledTime: Date.UTC(2026, 10, 3, 0, 2) });
  const retryResults = retried.first_check.results[0].pdf_results;
  assert.deepEqual(retryResults.map((item) => item.status), [
    "already_dispatched",
    "prc-release-event-dispatched"
  ]);
  assert.equal(dispatchAttempts.length, 3, "the successful Elementary list must not be dispatched twice");
  assert.equal(dispatchAttempts[2].result_level, "secondary");
});

