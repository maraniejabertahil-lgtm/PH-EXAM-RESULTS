import { getCachedDataset, setCachedDataset } from "./storage.js";

export async function loadManifest() {
  const response = await fetch("/data/manifest.json", { cache: "no-store" });
  if (!response.ok) throw new Error("The published examination catalogue is unavailable.");
  const manifest = await response.json();
  if (manifest.schema_version !== 2 || !manifest.authorities) {
    throw new Error("The published examination catalogue has an unsupported format.");
  }
  return manifest;
}

export async function loadSiteStatus() {
  const response = await fetch("/data/site-status.json", { cache: "no-store" });
  if (!response.ok) return { mode: "search", preparation: null };
  const status = await response.json();
  return status && status.mode === "preparing"
    ? status
    : { mode: "search", preparation: null };
}

export function getExaminations(manifest, authority) {
  return Object.keys(manifest.authorities?.[authority]?.examinations || {}).sort();
}

export function getYears(manifest, authority, examination) {
  const years = manifest.authorities?.[authority]?.examinations?.[examination]?.years || {};
  return Object.keys(years).sort((a, b) => Number(b) - Number(a));
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

export function validateDatasetPayload(payload) {
if (
    !payload ||
    typeof payload !== "object" ||
    !Array.isArray(payload.columns) ||
    !Array.isArray(payload.data) ||
    payload.columns.length === 0 ||
    payload.columns.some(column => typeof column !== "string" || !column.trim()) ||
    new Set(payload.columns).size !== payload.columns.length ||
    !payload.columns.includes("name")
  ) {
    throw new Error("The selected examination dataset has an invalid structure.");
  }
  const nameIndex = payload.columns.indexOf("name");
  for (let index = 0; index < payload.data.length; index += 1) {
    const row = payload.data[index];
    if (
      !Array.isArray(row) ||
      row.length !== payload.columns.length ||
      typeof row[nameIndex] !== "string" ||
      !row[nameIndex].trim()
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
        validateDatasetPayload(cached);
        return cached;
      } catch {
        // A damaged local cache must never bypass validation; fetch a clean copy.
      }
    }
  } catch {
    // Continue without IndexedDB when browser privacy settings disable it.
  }

  const response = await fetch(file.path, { cache: "default" });
  if (!response.ok) throw new Error("The selected examination dataset could not be downloaded.");
  const buffer = await response.arrayBuffer();
  const actualHash = await sha256Hex(buffer);
  if (actualHash !== file.hash) {
    throw new Error("Dataset integrity check failed. Please try again later.");
  }
  const payload = JSON.parse(new TextDecoder().decode(buffer));
  validateDatasetPayload(payload);

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
  const selected = selectShards(files, query);
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
