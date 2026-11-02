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
  // Some official sites reject HEAD (403) while allowing an ordinary bounded GET.
  // Retry only the approved URL, with a small byte range and the same-origin redirect guard.
  if ([403, 405, 501].includes(result.response.status)) {
    result = await fetchSameOrigin(url, {
      method: "GET",
      headers: { "User-Agent": USER_AGENT, Range: "bytes=0-1023", Accept: "application/pdf,text/html,*/*" }
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

async function findApprovedGoogleDriveLinks(pageUrl, source, fetchImpl) {
  const allowed = new Set(Array.isArray(source.drive_file_ids) ? source.drive_file_ids : []);
  if (allowed.size === 0) return [];
  const page = validateHttpsUrl(pageUrl);
  const { response, finalUrl } = await fetchSameOrigin(page.href, {
    method: "GET", headers: { "User-Agent": USER_AGENT, Accept: "text/html" }
  }, fetchImpl);
  if (!response.ok) { if (response.body) await response.body.cancel(); return []; }
  const reader = response.body?.getReader();
  if (!reader) return [];
  const chunks = []; let total = 0;
  try {
    while (total < MAX_HTML_BYTES) {
      const { done, value } = await reader.read();
      if (done) break;
      const part = value.subarray(0, MAX_HTML_BYTES - total);
      chunks.push(part); total += part.length;
      if (part.length !== value.length) break;
    }
  } finally { await reader.cancel().catch(() => {}); }
  const html = new TextDecoder().decode(concatBytes(chunks, total));
  const found = new Set();
  const hrefs = /href\s*=\s*["']([^"']+)["']/gi;
  let match;
  while ((match = hrefs.exec(html))) {
    try {
      const link = new URL(match[1], finalUrl);
      if (link.protocol !== "https:" || link.hostname.toLowerCase() !== "drive.google.com" ||
          link.username || link.password) continue;
      const fileMatch = link.pathname.match(/^\/file\/d\/([A-Za-z0-9_-]{10,})\/view\/?$/);
      if (fileMatch && allowed.has(fileMatch[1])) found.add(fileMatch[1]);
    } catch { /* Ignore malformed or non-Drive links. */ }
  }
  return [...found].map((id) => ({
    id,
    url: `https://drive.google.com/uc?export=download&id=${encodeURIComponent(id)}`
  }));
}

async function fetchDriveDownload(urlValue, fileId, init, fetchImpl) {
  const original = validateHttpsUrl(urlValue);
  if (original.hostname.toLowerCase() !== "drive.google.com" ||
      original.pathname !== "/uc" || original.searchParams.get("id") !== fileId ||
      original.searchParams.get("export") !== "download") {
    throw new Error("Google Drive candidate URL does not match its approved file ID.");
  }
  const allowedHosts = new Set(["drive.google.com", "drive.usercontent.google.com"]);
  let current = original;
  for (let redirects = 0; redirects <= MAX_REDIRECTS; redirects += 1) {
    const response = await fetchImpl(current.href, {
      ...init, redirect: "manual", signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS)
    });
    if (![301, 302, 303, 307, 308].includes(response.status)) return { response, finalUrl: current.href };
    const location = response.headers.get("location");
    if (!location) return { response, finalUrl: current.href };
    const next = new URL(location, current);
    if (next.protocol !== "https:" || !allowedHosts.has(next.hostname.toLowerCase()) ||
        next.username || next.password || next.searchParams.get("id") !== fileId ||
        !["/uc", "/download"].includes(next.pathname)) {
      throw new Error("Google Drive redirect rejected: host, path, or approved file ID did not match.");
    }
    current = next;
  }
  throw new Error("Too many redirects while checking an approved Google Drive file.");
}

async function verifyPdfCandidate(url, fetchImpl, driveFileId = null) {
  const request = {
    method: "GET",
    headers: {
      "User-Agent": USER_AGENT,
      Range: "bytes=0-1023",
      Accept: "application/pdf,application/octet-stream,*/*"
    }
  };
  const { response } = driveFileId
    ? await fetchDriveDownload(url, driveFileId, request, fetchImpl)
    : await fetchSameOrigin(url, request, fetchImpl);
  if (![200, 206].includes(response.status)) {
    if (response.body) await response.body.cancel();
    return false;
  }
  const reader = response.body?.getReader();
  if (!reader) return false;
  const chunks = [];
  let total = 0;
  try {
    while (total < 1024) {
      const { done, value } = await reader.read();
      if (done) break;
      const part = value.subarray(0, 1024 - total);
      chunks.push(part);
      total += part.length;
      if (part.length !== value.length) break;
    }
  } finally {
    await reader.cancel().catch(() => {});
  }
  const prefix = concatBytes(chunks, total);
  const signature = new TextDecoder("latin1").decode(prefix);
  return signature.includes("%PDF-");
}

async function scanApprovedDriveFiles(source, env, fetchImpl, now) {
  // The CSC announcement may return 403 even while its already-approved public
  // Google Drive PDFs remain downloadable. Try only IDs explicitly approved in
  // the source registry; never discover arbitrary Drive files.
  const ids = [...new Set(Array.isArray(source.drive_file_ids) ? source.drive_file_ids : [])]
    .filter((id) => typeof id === "string" && /^[A-Za-z0-9_-]{10,}$/.test(id));
  const results = [];
  for (const id of ids) {
    const url = `https://drive.google.com/uc?export=download&id=${encodeURIComponent(id)}`;
    try {
      const verified = await verifyPdfCandidate(url, fetchImpl, id);
      if (!verified) {
        results.push({ drive_file_id: id, status: "pdf_verification_failed_manual_review_required" });
        continue;
      }
      const dispatched = await dispatchDetectedPdf(env, source, url, {
        status: 206, contentType: "application/pdf", preemptive: false,
        detectionMethod: "approved_drive_id_fallback", driveFileId: id
      }, fetchImpl, now);
      results.push({ url, drive_file_id: id, status: dispatched.status });
    } catch (error) {
      results.push({
        drive_file_id: id, status: "pdf_verification_error_manual_review_required",
        error: String(error.message || error).slice(0, 160)
      });
    }
  }
  return results;
}

async function scanApprovedDocuments(source, pageUrl, env, fetchImpl, now) {
  const sameOriginLinks = await findSameOriginPdfLinks(pageUrl, fetchImpl);
  const driveLinks = await findApprovedGoogleDriveLinks(pageUrl, source, fetchImpl);
  const results = [];
  for (const pdfUrl of sameOriginLinks.slice(0, 5)) {
    try {
      const pdfMetadata = await requestMetadata(pdfUrl, fetchImpl);
      if (pdfMetadata.status >= 200 && pdfMetadata.status < 300 && isPdf(pdfUrl, pdfMetadata.contentType)) {
        const verified = await verifyPdfCandidate(pdfUrl, fetchImpl);
        if (!verified) {
          results.push({ url: pdfUrl, status: "pdf_verification_failed_manual_review_required" });
          continue;
        }
        const dispatched = await dispatchDetectedPdf(env, source, pdfUrl, { ...pdfMetadata, preemptive: false }, fetchImpl, now);
        results.push({ url: pdfUrl, status: dispatched.status });
      }
    } catch (error) {
      results.push({ url: pdfUrl, status: "check_error", error: String(error.message || error).slice(0, 160) });
    }
  }
  // Use the same strict ID allowlist and PDF signature check for page-discovered links.
  for (const item of driveLinks) {
    try {
      const verified = await verifyPdfCandidate(item.url, fetchImpl, item.id);
      if (!verified) {
        results.push({ drive_file_id: item.id, status: "pdf_verification_failed_manual_review_required" });
        continue;
      }
      const dispatched = await dispatchDetectedPdf(env, source, item.url, {
        status: 206, contentType: "application/pdf", preemptive: false, driveFileId: item.id
      }, fetchImpl, now);
      results.push({ url: item.url, drive_file_id: item.id, status: dispatched.status });
    } catch (error) {
      results.push({ drive_file_id: item.id, status: "pdf_verification_error_manual_review_required", error: String(error.message || error).slice(0, 160) });
    }
  }
  return results;
}

async function dispatchDetectedPdf(env, source, pdfUrl, metadata, fetchImpl, now) {
  const eventType = env.GITHUB_EVENT_TYPE || "source-detected";
  if (!["source-detected", "staging-source-detected"].includes(eventType)) {
    throw new Error("GITHUB_EVENT_TYPE must be source-detected or staging-source-detected.");
  }
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
      event_type: eventType,
      client_payload: {
        source_id: String(source.id), authority: source.authority, exam: source.exam,
        source_type: source.source_type, detected_url: pdfUrl, detected_at: isoNow(now),
        detection_method: metadata.detectionMethod || (metadata.preemptive ? "preemptive_head" : "source_page_change"),
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
    // A 403 from CSC must not prevent retrieval of public PDFs whose exact Drive
    // IDs were already approved in the registry. This fallback does not scrape
    // mirrors or broaden the allowed Drive hosts/IDs.
    if (metadata.status === 403 && Array.isArray(source.drive_file_ids) && source.drive_file_ids.length > 0) {
      const pdf_results = await scanApprovedDriveFiles(source, env, fetchImpl, now);
      return {
        source_id: sourceId, url: target.url, status: "http_error",
        http_status: metadata.status, fallback: "approved_drive_ids", pdf_results
      };
    }
    return { source_id: sourceId, url: target.url, status: "http_error", http_status: metadata.status };
  }
  if (target.preemptive || isPdfPath(target.url) || metadata.contentType === "application/pdf") {
    if (!isPdf(target.url, metadata.contentType)) {
      return { source_id: sourceId, url: target.url, status: "not_pdf", http_status: metadata.status };
    }
    try {
      const verified = await verifyPdfCandidate(target.url, fetchImpl);
      if (!verified) {
        return { source_id: sourceId, url: target.url, status: "pdf_verification_failed_manual_review_required", preemptive: target.preemptive };
      }
      const result = await dispatchDetectedPdf(env, source, target.url, { ...metadata, preemptive: target.preemptive }, fetchImpl, now);
      return { source_id: sourceId, url: target.url, status: result.status, preemptive: target.preemptive };
    } catch (error) {
      return { source_id: sourceId, url: target.url, status: "dispatch_error", error: String(error.message || error).slice(0, 240) };
    }
  }
  const key = await kvKey("baseline", sourceId, target.url);
  const current = fingerprint(metadata);
  let previous;
  try {
    previous = await env.PEAK_WEEK.get(key);
  } catch (error) {
    return { source_id: sourceId, url: target.url, status: "subrequest_budget_reached", error: String(error.message || error).slice(0, 200) };
  }
  if (previous === null) {
    try {
      await env.PEAK_WEEK.put(key, current, { expirationTtl: BASELINE_TTL_SECONDS });
    } catch (error) {
      return { source_id: sourceId, url: target.url, status: "subrequest_budget_reached", error: String(error.message || error).slice(0, 200) };
    }
    if (source.scan_page_on_baseline === true && !target.preemptive) {
      try {
        const pdf_results = await scanApprovedDocuments(source, target.url, env, fetchImpl, now);
        return { source_id: sourceId, url: target.url, status: "baseline_created", pdf_results };
      } catch (error) {
        return { source_id: sourceId, url: target.url, status: "baseline_created_page_scan_error", error: String(error.message || error).slice(0, 240) };
      }
    }
    return { source_id: sourceId, url: target.url, status: "baseline_created" };
  }
  if (previous === current) return { source_id: sourceId, url: target.url, status: "unchanged" };
  try {
    await env.PEAK_WEEK.put(key, current, { expirationTtl: BASELINE_TTL_SECONDS });
  } catch (error) {
    return { source_id: sourceId, url: target.url, status: "subrequest_budget_reached", error: String(error.message || error).slice(0, 200) };
  }
  if (!allowPageChange) return { source_id: sourceId, url: target.url, status: "changed_no_page_scan" };
  try {
    const results = await scanApprovedDocuments(source, target.url, env, fetchImpl, now);
    return { source_id: sourceId, url: target.url, status: "changed", pdf_results: results };
  } catch (error) {
    return { source_id: sourceId, url: target.url, status: "page_scan_error", error: String(error.message || error).slice(0, 240) };
  }
}

function buildTargets(sources, now, peakWeek) {
  const targets = [];
  for (const source of sources) {
    if (!isApprovedSource(source)) continue;
    try { targets.push({ source, url: validateHttpsUrl(source.url).href, preemptive: false }); }
    catch (error) { console.warn(`Skipping invalid source ${String(source.id || "unknown")}: ${error.message}`); }
  }
  if (peakWeek) targets.push(...expandPreemptiveTemplates(sources, now.getTime()));
  return targets;
}

function officialSourceAvailable(results) {
  const availableStatuses = new Set([
    "baseline_created", "unchanged", "changed", "changed_no_page_scan",
    "page_scan_error", "not_pdf", "dispatched", "already_dispatched"
  ]);
  return results.some((item) => availableStatuses.has(item.status));
}

async function runScan(sources, env, fetchImpl, now, peakWeek) {
  const scopes = new Map();
  for (const source of sources) {
    if (!source || !["PRC", "CSC"].includes(source.authority) || typeof source.exam !== "string") continue;
    const key = `${source.authority}:${source.exam}`;
    if (!scopes.has(key)) scopes.set(key, []);
    scopes.get(key).push(source);
  }

  const results = [];
  let checkedTargets = 0;
  let skippedTargets = 0;
  for (const scopeSources of scopes.values()) {
    const official = scopeSources.filter((item) => item.source_type === "official");
    const thirdParty = scopeSources.filter((item) => item.source_type === "verified_third_party");
    if (official.length === 0) {
      for (const item of thirdParty) results.push({
        source_id: String(item.id || "unknown"),
        status: "skipped_no_official_source_configured"
      });
      continue;
    }

    const officialTargets = buildTargets(official, now, peakWeek);
    const officialBudget = Math.max(0, MAX_TARGETS_PER_SCAN - checkedTargets);
    const selectedOfficial = officialTargets.slice(0, officialBudget);
    const officialStart = results.length;
    for (const target of selectedOfficial) {
      results.push(await checkTarget(target, env, fetchImpl, now, !target.preemptive));
    }
    checkedTargets += selectedOfficial.length;
    skippedTargets += Math.max(0, officialTargets.length - selectedOfficial.length);

    // Do not fall back while any configured official target remains unchecked.
    const officialFullyChecked = selectedOfficial.length === officialTargets.length;
    if (!officialFullyChecked) {
      for (const item of thirdParty) results.push({
        source_id: String(item.id || "unknown"),
        status: "skipped_official_checks_incomplete"
      });
      continue;
    }
    if (officialSourceAvailable(results.slice(officialStart))) {
      for (const item of thirdParty) results.push({
        source_id: String(item.id || "unknown"),
        status: "skipped_official_available"
      });
      continue;
    }

    const thirdTargets = buildTargets(thirdParty, now, peakWeek);
    const thirdBudget = Math.max(0, MAX_TARGETS_PER_SCAN - checkedTargets);
    const selectedThird = thirdTargets.slice(0, thirdBudget);
    for (const target of selectedThird) {
      results.push(await checkTarget(target, env, fetchImpl, now, !target.preemptive));
    }
    checkedTargets += selectedThird.length;
    skippedTargets += Math.max(0, thirdTargets.length - selectedThird.length);
  }
  return { checked_targets: checkedTargets, skipped_targets: skippedTargets, results };
}

function createSubrequestBudget(env, fetchImpl) {
  let used = 0;
  const consume = () => {
    if (used >= MAX_SUBREQUESTS_PER_INVOCATION) {
      throw new Error("Cloudflare Free subrequest safety budget reached; remaining checks were skipped.");
    }
    used += 1;
  };
  return {
    fetch: async (...args) => {
      consume();
      return fetchImpl(...args);
    },
    kv: {
      get: async (...args) => {
        consume();
        return env.PEAK_WEEK.get(...args);
      },
      put: async (...args) => {
        consume();
        return env.PEAK_WEEK.put(...args);
      }
    },
    used: () => used
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
  const budget = createSubrequestBudget(env, fetchImpl);
  const budgetEnv = { ...env, PEAK_WEEK: budget.kv };
  const peakWeek = parseBoolean(await budget.kv.get("PEAK_WEEK"));
  const sources = await readSourceRegistry(env, budget.fetch);
  const activeSources = sources.filter(isApprovedSource);
  const first = await runScan(sources, budgetEnv, budget.fetch, new Date(scheduledTime), peakWeek);
  let second = null;
  if (peakWeek) {
    await sleepImpl(30_000);
    second = await runScan(sources, budgetEnv, budget.fetch, new Date(scheduledTime + 30_000), true);
  }
  const report = {
    checked_at: isoNow(new Date(scheduledTime)),
    mode: peakWeek ? "peak_week" : "standard",
    configured_sources: sources.length,
    approved_enabled_sources: activeSources.length,
    outbound_subrequests_used: budget.used(),
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
