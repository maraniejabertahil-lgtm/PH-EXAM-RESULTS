import { getCachedDataset, setCachedDataset } from "./storage.js";

export async function fetchWithTimeout(resource, options = {}, timeoutMs = 45000) {
  // The signal remains active while the response body is being read, not just
  // until fetch() receives the response headers.
  const signal = AbortSignal.timeout(timeoutMs);
  try {
    return await fetch(resource, { ...options, signal });
  } catch (error) {
    if (error?.name === "AbortError" || error?.name === "TimeoutError") {
      throw new Error("The request took too long. Check your connection and try again.");
    }
    throw error;
  }
}

export async function loadManifest() {
  const response = await fetchWithTimeout("/data/manifest.json", { cache: "no-store" });
  if (!response.ok) throw new Error("The published examination catalogue is unavailable.");
  const manifest = await response.json();
  if (manifest.schema_version !== 2 || !manifest.authorities) {
    throw new Error("The published examination catalogue has an unsupported format.");
  }
  return manifest;
}

export async function loadSiteStatus() {
  try {
    const response = await fetchWithTimeout("/data/site-status.json", { cache: "no-store" });
    if (!response.ok) return { mode: "search", preparation: null };
    const status = await response.json();
    return status && status.schema_version === 1 && status.mode === "preparing"
      ? status
      : { mode: "search", preparation: null };
  } catch {
    // Status is supplemental; a status-file outage must not disable result search.
    return { mode: "search", preparation: null };
  }
}

export function getExaminations(manifest, authority) {
  return Object.keys(manifest.authorities?.[authority]?.examinations || {}).sort();
}

export function getYears(manifest, authority, examination) {
  const years = manifest.authorities?.[authority]?.examinations?.[examination]?.years || {};
  return Object.keys(years).sort((a, b) => Number(b) - Number(a));
}

export function validateManifestFileEntry(file, authority, examination, year, shard) {
  const yearText = String(year);
  if (!/^(?:PRC|CSC)$/.test(String(authority)) ||
      !/^[A-Za-z0-9._-]{1,80}$/.test(String(examination)) ||
      !/^\d{4}$/.test(yearText) ||
      !/^S[0-9]{3}$/.test(String(shard))) {
    throw new Error("The examination catalogue contains an invalid dataset reference.");
  }
  const expectedPrefix = "/data/" + authority + "/" + examination + "/" + yearText + "/";
  if (!file || typeof file !== "object" || typeof file.path !== "string" ||
      !file.path.startsWith(expectedPrefix) ||
      !/^\d{4}-.+\.json$/.test(file.path.slice(expectedPrefix.length)) ||
      !/^[a-f0-9]{64}$/.test(file.hash || "") ||
      !Number.isInteger(file.record_count) || file.record_count < 1 ||
      !Number.isInteger(file.size_bytes) || file.size_bytes < 1 ||
      file.size_bytes > 10 * 1024 * 1024) {
    throw new Error("The examination catalogue contains an invalid dataset reference.");
  }
  return file;
}

export function selectShards(files) {
  // Search uses substring matching, so a query can occur anywhere in a name.
  // Selecting only the shard matching the query's first letter would miss
  // names such as "ZAMORA, JUAN" when the visitor searches for "JUAN".
  return Object.values(files);
}

async function sha256Hex(buffer) {
  if (!globalThis.crypto?.subtle) {
    throw new Error("This browser cannot verify dataset integrity.");
  }
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest))
    .map(byte => byte.toString(16).padStart(2, "0"))
    .join("");
}

const EXPECTED_DATASET_COLUMNS = ["name", "rating", "region", "seq"];

export function validateDatasetPayload(payload, expectedRecordCount) {
  if (
    !payload ||
    typeof payload !== "object" ||
    !Array.isArray(payload.columns) ||
    JSON.stringify(payload.columns) !== JSON.stringify(EXPECTED_DATASET_COLUMNS) ||
    !Array.isArray(payload.data) ||
    (Number.isInteger(expectedRecordCount) && payload.data.length !== expectedRecordCount)
  ) {
    throw new Error("The selected examination dataset has an invalid structure or record count.");
  }
  for (let index = 0; index < payload.data.length; index += 1) {
    const row = payload.data[index];
    const validRating = row?.[1] === null || (
      typeof row?.[1] === "number" && Number.isFinite(row[1]) && row[1] >= 0 && row[1] <= 100
    );
    const validRegion = row?.[2] === null || typeof row?.[2] === "string";
    const validSequence = typeof row?.[3] === "string" && /^[0-9]+$/.test(row[3]) && Number(row[3]) > 0;
    if (
      !Array.isArray(row) ||
      row.length !== EXPECTED_DATASET_COLUMNS.length ||
      typeof row[0] !== "string" ||
      !row[0].trim() ||
      !validRating ||
      !validRegion ||
      !validSequence
    ) {
      throw new Error("The selected examination dataset contains an invalid record.");
    }
  }
  return payload;
}

async function fetchVerifiedDataset(file) {
  try {
    const cached = await getCachedDataset(file.path, file.hash);
    if (cached) {
      try {
        validateDatasetPayload(cached, file.record_count);
        return cached;
      } catch {
        // A damaged local cache must never bypass validation; fetch a clean copy.
      }
    }
  } catch {
    // Continue without IndexedDB when browser privacy settings disable it.
  }

  const response = await fetchWithTimeout(file.path, { cache: "default" });
  if (!response.ok) throw new Error("The selected examination dataset could not be downloaded.");
  const buffer = await response.arrayBuffer();
  const actualHash = await sha256Hex(buffer);
  if (actualHash !== file.hash) {
    throw new Error("Dataset integrity check failed. Please try again later.");
  }
  const payload = JSON.parse(new TextDecoder().decode(buffer));
  validateDatasetPayload(payload, file.record_count);

  try {
    await setCachedDataset(file.path, file.hash, payload);
  } catch {
    // Search remains available even if local caching is unavailable.
  }
  return payload;
}

export async function loadSearchDataset(manifest, authority, examination, year, query) {
  const yearEntry = manifest.authorities?.[authority]?.examinations?.[examination]?.years?.[year];
  if (!yearEntry || !yearEntry.files) throw new Error("No published results exist for that selection.");

  const files = yearEntry.files;
  if (!files || typeof files !== "object" || Array.isArray(files)) {
    throw new Error("The examination catalogue contains invalid dataset references.");
  }
  const validatedFiles = Object.fromEntries(
    Object.entries(files).map(([shard, file]) => [
      shard,
      validateManifestFileEntry(file, authority, examination, year, shard)
    ])
  );
  const selected = selectShards(validatedFiles);
  if (!selected.length) throw new Error("No published dataset is available.");
  const datasets = await Promise.all(selected.map(fetchVerifiedDataset));
  if (!datasets.length) throw new Error("No published dataset is available.");

  const columns = datasets[0].columns;
  if (datasets.some(dataset => JSON.stringify(dataset.columns) !== JSON.stringify(columns))) {
    throw new Error("The published dataset shards use inconsistent columns.");
  }
  return {
    columns,
    rows: datasets.flatMap(dataset => dataset.data),
    datasetKey: selected.map(file => file.path + ":" + file.hash).join("|")
  };
}
