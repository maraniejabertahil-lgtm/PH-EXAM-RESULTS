const GITHUB_API = "https://api.github.com";
const GITHUB_API_VERSION = "2022-11-28";
const USER_AGENT = "PH-EXAM-RESULTS-Watcher/1.0";
const MAX_TARGETS_PER_SCAN = 10;
const MAX_SUBREQUESTS_PER_INVOCATION = 45;
const MAX_REDIRECTS = 5;
const MAX_HTML_BYTES = 1024 * 1024;
const REQUEST_TIMEOUT_MS = 10_000;
const BASELINE_TTL_SECONDS = 60 * 60 * 24 * 90;
const DISPATCH_TTL_SECONDS = 60 * 60 * 24 * 30;

function isoNow(date = new Date()) { return date.toISOString(); }
function parseBoolean(value) { return value === true || value === "true" || value === "1"; }

function isApprovedSource(source) {
  if (!source || typeof source !== "object" || source.enabled !== true) return false;
  if (source.source_type === "official") return source.authorized === true;
  if (source.source_type === "verified_third_party") return source.verified_by_owner === true;
  return false;
}

function validateHttpsUrl(value) {
  if (typeof value !== "string" || !value.trim()) throw new Error("Source URL must be a non-empty text URL.");
  const url = new URL(value);
  if (url.protocol !== "https:" || !url.hostname || url.username || url.password) {
    throw new Error("Only valid HTTPS URLs without embedded credentials are allowed.");
  }
  return url;
}

function monthParts(date, offset = 0) {
  const value = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + offset, 1));
  const year = String(value.getUTCFullYear());
  const month = String(value.getUTCMonth() + 1).padStart(2, "0");
  return { YYYY: year, YY: year.slice(-2), MM: month, YYYYMM: `${year}${month}` };
}

export function expandPreemptiveTemplates(sources, scheduledTime) {
  const date = new Date(scheduledTime);
  const targets = [];
  for (const source of sources) {
    if (!isApprovedSource(source)) continue;
    const templates = source.preemptive_url_templates ?? [];
    if (!Array.isArray(templates)) continue;
    let sourceOrigin;
    try { sourceOrigin = validateHttpsUrl(source.url).origin; } catch { continue; }
    for (const template of templates) {
      if (typeof template !== "string" || !template.trim()) continue;
      for (const offset of [0, 1]) {
        const parts = monthParts(date, offset);
        const expanded = template.replace(/\{(YYYY|YY|MM|YYYYMM|EXAM)\}/g, (_match, key) =>
          key === "EXAM" ? encodeURIComponent(String(source.exam ?? "")) : parts[key]
        );
        if (/\{[^}]+\}/.test(expanded)) continue;
        try {
          const url = validateHttpsUrl(expanded);
          if (url.origin === sourceOrigin) targets.push({ source, url: url.href, preemptive: true });
        } catch { /* Ignore invalid or cross-origin templates. */ }
      }
    }
  }
  return targets;
}

async function sha256Hex(value) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}
async function kvKey(prefix, sourceId, url) {
  return `${prefix}:${await sha256Hex(`${sourceId}\n${url}`)}`;
}

async function readSourceRegistry(env, fetchImpl) {
  const repository = env.GITHUB_REPOSITORY;
  const token = env.GITHUB_TOKEN;
  const ref = env.GITHUB_SOURCE_REF || "main";
  const path = env.GITHUB_SOURCE_PATH || "python-engine/config/sources.json";
  if (!repository || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository)) {
    throw new Error("GITHUB_REPOSITORY must be set to owner/repository.");
  }
  if (!token) throw new Error("GITHUB_TOKEN secret is not configured.");
  const url = `${GITHUB_API}/repos/${repository}/contents/${path.split("/").map(encodeURIComponent).join("/")}?ref=${encodeURIComponent(ref)}`;
  const response = await fetchImpl(url, {
    method: "GET",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": GITHUB_API_VERSION,
      "User-Agent": USER_AGENT
    },
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS)
  });
  if (!response.ok) throw new Error(`Could not read source registry from GitHub (HTTP ${response.status}).`);
  const file = await response.json();
  if (file.encoding !== "base64" || typeof file.content !== "string") {
    throw new Error("GitHub source registry response was not base64 content.");
  }
  const decoded = Uint8Array.from(atob(file.content.replace(/\s/g, "")), (char) => char.charCodeAt(0));
  const registry = JSON.parse(new TextDecoder().decode(decoded));
  if (!registry || !Array.isArray(registry.sources)) throw new Error("Source registry must contain a sources array.");
  return registry.sources;
}

async function fetchSameOrigin(urlValue, init, fetchImpl) {
  const original = validateHttpsUrl(urlValue);
  let current = original;
  for (let redirects = 0; redirects <= MAX_REDIRECTS; redirects += 1) {
    const response = await fetchImpl(current.href, {
      ...init, redirect: "manual", signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS)
    });
    if (![301, 302, 303, 307, 308].includes(response.status)) return { response, finalUrl: current.href };
    const location = response.headers.get("location");
    if (!location) return { response, finalUrl: current.href };
    const next = new URL(location, current);
    if (next.protocol !== "https:" || next.origin !== original.origin || next.username || next.password) {
      throw new Error("Cross-origin or non-HTTPS redirect rejected.");
    }
    current = next;
  }
  throw new Error("Too many redirects while checking an approved source.");
}

async function requestMetadata(url, fetchImpl) {
  let result = await fetchSameOrigin(url, {
    method: "HEAD",
    headers: { "User-Agent": USER_AGENT, Accept: "application/pdf,text/html,*/*" }
  }, fetchImpl);
  if (result.response.status === 405 || result.response.status === 501) {
    result = await fetchSameOrigin(url, {
      method: "GET",
      headers: { "User-Agent": USER_AGENT, Range: "bytes=0-0", Accept: "application/pdf,text/html,*/*" }
    }, fetchImpl);
    if (result.response.body) await result.response.body.cancel();
  }
  const response = result.response;
  return {
    status: response.status, url: result.finalUrl,
    contentType: (response.headers.get("content-type") || "").split(";")[0].trim().toLowerCase(),
    etag: response.headers.get("etag") || "",
    lastModified: response.headers.get("last-modified") || "",
    contentLength: response.headers.get("content-length") || ""
  };
}

function isPdfPath(url) { return new URL(url).pathname.toLowerCase().endsWith(".pdf"); }
function isPdf(url, contentType) {
  return contentType === "application/pdf" || (isPdfPath(url) && contentType !== "text/html");
}
function fingerprint(metadata) {
  return JSON.stringify({
    status: metadata.status, contentType: metadata.contentType, etag: metadata.etag,
    lastModified: metadata.lastModified, contentLength: metadata.contentLength
  });
}
function concatBytes(chunks, total) {
  const output = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) { output.set(chunk, offset); offset += chunk.length; }
  return output;
}

async function findSameOriginPdfLinks(pageUrl, fetchImpl) {
  const page = validateHttpsUrl(pageUrl);
  const { response, finalUrl } = await fetchSameOrigin(page.href, {
    method: "GET", headers: { "User-Agent": USER_AGENT, Accept: "text/html" }
  }, fetchImpl);
  if (!response.ok) {
    if (response.body) await response.body.cancel();
    return [];
  }
  const reader = response.body?.getReader();
  if (!reader) return [];
  const chunks = [];
  let total = 0;
  try {
    while (total < MAX_HTML_BYTES) {
      const { done, value } = await reader.read();
      if (done) break;
      const part = value.subarray(0, MAX_HTML_BYTES - total);
      chunks.push(part);
      total += part.length;
      if (part.length !== value.length) break;
    }
  } finally { await reader.cancel().catch(() => {}); }
  const html = new TextDecoder().decode(concatBytes(chunks, total));
  const links = new Set();
  const regex = /href\s*=\s*["']([^"']+\.pdf(?:\?[^"']*)?(?:#[^"']*)?)["']/gi;
  let match;
  while ((match = regex.exec(html))) {
    try {
      const candidate = new URL(match[1], finalUrl);
      if (candidate.protocol === "https:" && candidate.origin === page.origin && !candidate.username && !candidate.password) {
        links.add(candidate.href);
      }
    } catch { /* Ignore malformed links. */ }
  }
  return [...links];
}

async function dispatchDetectedPdf(env, source, pdfUrl, metadata, fetchImpl, now) {
  const key = await kvKey("dispatched", source.id, pdfUrl);
  if (await env.PEAK_WEEK.get(key)) return { status: "already_dispatched", url: pdfUrl };
  const response = await fetchImpl(`${GITHUB_API}/repos/${env.GITHUB_REPOSITORY}/dispatches`, {
    method: "POST",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      "X-GitHub-Api-Version": GITHUB_API_VERSION,
      "Content-Type": "application/json",
      "User-Agent": USER_AGENT
    },
    body: JSON.stringify({
      event_type: "source-detected",
      client_payload: {
        source_id: String(source.id), authority: source.authority, exam: source.exam,
        source_type: source.source_type, detected_url: pdfUrl, detected_at: isoNow(now),
        detection_method: metadata.preemptive ? "preemptive_head" : "source_page_change",
        http_status: metadata.status, content_type: metadata.contentType
      }
    }),
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS)
  });
  if (response.status !== 204) {
    const detail = await response.text().catch(() => "");
    throw new Error(`GitHub repository_dispatch failed (HTTP ${response.status})${detail ? `: ${detail.slice(0, 200)}` : ""}.`);
  }
  await env.PEAK_WEEK.put(key, isoNow(now), { expirationTtl: DISPATCH_TTL_SECONDS });
  return { status: "dispatched", url: pdfUrl };
}

async function checkTarget(target, env, fetchImpl, now, allowPageChange) {
  const source = target.source;
  const sourceId = String(source.id);
  let metadata;
  try { metadata = await requestMetadata(target.url, fetchImpl); }
  catch (error) {
    return { source_id: sourceId, url: target.url, status: "check_error", error: String(error.message || error).slice(0, 240) };
  }
  if (metadata.status < 200 || metadata.status >= 300) {
    return { source_id: sourceId, url: target.url, status: "http_error", http_status: metadata.status };
  }
  if (target.preemptive || isPdfPath(target.url) || metadata.contentType === "application/pdf") {
    if (!isPdf(target.url, metadata.contentType)) {
      return { source_id: sourceId, url: target.url, status: "not_pdf", http_status: metadata.status };
    }
    try {
      const result = await dispatchDetectedPdf(env, source, target.url, { ...metadata, preemptive: target.preemptive }, fetchImpl, now);
      return { source_id: sourceId, url: target.url, status: result.status, preemptive: target.preemptive };
    } catch (error) {
      return { source_id: sourceId, url: target.url, status: "dispatch_error", error: String(error.message || error).slice(0, 240) };
    }
  }
  const key = await kvKey("baseline", sourceId, target.url);
  const current = fingerprint(metadata);
  const previous = await env.PEAK_WEEK.get(key);
  if (previous === null) {
    await env.PEAK_WEEK.put(key, current, { expirationTtl: BASELINE_TTL_SECONDS });
    return { source_id: sourceId, url: target.url, status: "baseline_created" };
  }
  if (previous === current) return { source_id: sourceId, url: target.url, status: "unchanged" };
  await env.PEAK_WEEK.put(key, current, { expirationTtl: BASELINE_TTL_SECONDS });
  if (!allowPageChange) return { source_id: sourceId, url: target.url, status: "changed_no_page_scan" };
  try {
    const pdfLinks = await findSameOriginPdfLinks(target.url, fetchImpl);
    const results = [];
    for (const pdfUrl of pdfLinks.slice(0, 5)) {
      try {
        const pdfMetadata = await requestMetadata(pdfUrl, fetchImpl);
        if (pdfMetadata.status >= 200 && pdfMetadata.status < 300 && isPdf(pdfUrl, pdfMetadata.contentType)) {
          const result = await dispatchDetectedPdf(env, source, pdfUrl, { ...pdfMetadata, preemptive: false }, fetchImpl, now);
          results.push({ url: pdfUrl, status: result.status });
        }
      } catch (error) {
        results.push({ url: pdfUrl, status: "check_error", error: String(error.message || error).slice(0, 160) });
      }
    }
    return { source_id: sourceId, url: target.url, status: "changed", pdf_results: results };
  } catch (error) {
    return { source_id: sourceId, url: target.url, status: "page_scan_error", error: String(error.message || error).slice(0, 240) };
  }
}

async function runScan(sources, env, fetchImpl, now, peakWeek) {
  const targets = [];
  for (const source of sources) {
    if (!isApprovedSource(source)) continue;
    try { targets.push({ source, url: validateHttpsUrl(source.url).href, preemptive: false }); }
    catch (error) { console.warn(`Skipping invalid source ${String(source.id || "unknown")}: ${error.message}`); }
  }
  if (peakWeek) targets.push(...expandPreemptiveTemplates(sources, now.getTime()));
  const selected = targets.slice(0, MAX_TARGETS_PER_SCAN);
  const results = [];
  for (const target of selected) results.push(await checkTarget(target, env, fetchImpl, now, !target.preemptive));
  return {
    checked_targets: selected.length,
    skipped_targets: Math.max(0, targets.length - selected.length),
    results
  };
}

export async function runScheduled({
  env, fetchImpl = fetch,
  sleepImpl = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  scheduledTime = Date.now()
}) {
  if (!env.PEAK_WEEK || typeof env.PEAK_WEEK.get !== "function" || typeof env.PEAK_WEEK.put !== "function") {
    throw new Error("The PEAK_WEEK KV namespace binding is not configured.");
  }
  let subrequestsUsed = 0;
  const budgetFetch = async (...args) => {
    if (subrequestsUsed >= MAX_SUBREQUESTS_PER_INVOCATION) {
      throw new Error("Cloudflare free-tier subrequest safety budget reached; remaining checks were skipped.");
    }
    subrequestsUsed += 1;
    return fetchImpl(...args);
  };
  const peakWeek = parseBoolean(await env.PEAK_WEEK.get("PEAK_WEEK"));
  const sources = await readSourceRegistry(env, budgetFetch);
  const activeSources = sources.filter(isApprovedSource);
  const first = await runScan(activeSources, env, budgetFetch, new Date(scheduledTime), peakWeek);
  let second = null;
  if (peakWeek) {
    await sleepImpl(30_000);
    second = await runScan(activeSources, env, budgetFetch, new Date(scheduledTime + 30_000), true);
  }
  const report = {
    checked_at: isoNow(new Date(scheduledTime)),
    mode: peakWeek ? "peak_week" : "standard",
    configured_sources: sources.length,
    approved_enabled_sources: activeSources.length,
    outbound_subrequests_used: subrequestsUsed,
    outbound_subrequest_safety_limit: MAX_SUBREQUESTS_PER_INVOCATION,
    first_check: first,
    second_check: second
  };
  console.log(JSON.stringify(report));
  return report;
}

export default {
  async scheduled(controller, env) {
    return runScheduled({ env, scheduledTime: controller.scheduledTime || Date.now() });
  },
  async fetch() { return new Response("Not found", { status: 404 }); }
};
