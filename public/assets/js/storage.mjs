const DB_NAME = "ph-exam-results";
const DB_VERSION = 1;
const STORE_NAME = "datasets";
const EXPECTED_COLUMNS = ["name", "rating", "region", "seq"];

function requestResult(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("IndexedDB request failed."));
  });
}

export function validateShard(shard, expectedCount) {
  if (!shard || !Array.isArray(shard.columns)
      || shard.columns.length !== EXPECTED_COLUMNS.length
      || shard.columns.some((column, index) => column !== EXPECTED_COLUMNS[index])
      || !Array.isArray(shard.data)
      || shard.data.length !== expectedCount
      || shard.data.some((row) => !Array.isArray(row)
        || row.length !== EXPECTED_COLUMNS.length
        || typeof row[0] !== "string"
        || typeof row[3] !== "string")) {
    throw new Error("Dataset shard has an invalid schema or record count.");
  }
  return shard;
}

export class DatasetCache {
  constructor(indexedDB = globalThis.indexedDB) {
    this.indexedDB = indexedDB;
    this.databasePromise = null;
  }

  open() {
    if (!this.indexedDB) return Promise.reject(new Error("This browser does not support IndexedDB."));
    if (!this.databasePromise) {
      this.databasePromise = new Promise((resolve, reject) => {
        const request = this.indexedDB.open(DB_NAME, DB_VERSION);
        request.onupgradeneeded = () => {
          const db = request.result;
          if (!db.objectStoreNames.contains(STORE_NAME)) {
            db.createObjectStore(STORE_NAME, { keyPath: "key" });
          }
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error || new Error("Could not open the local dataset cache."));
        request.onblocked = () => reject(new Error("The local dataset cache is blocked by another tab."));
      }).catch((error) => {
        this.databasePromise = null;
        throw error;
      });
    }
    return this.databasePromise;
  }

  async get(key) {
    const db = await this.open();
    const transaction = db.transaction(STORE_NAME, "readonly");
    const value = await requestResult(transaction.objectStore(STORE_NAME).get(key));
    return value?.payload;
  }

  async put(key, payload) {
    const db = await this.open();
    const transaction = db.transaction(STORE_NAME, "readwrite");
    await requestResult(transaction.objectStore(STORE_NAME).put({ key, payload }));
  }
}

export function normalizeSearchText(value) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .trim();
}

export async function fetchVerifiedShard(
  shardEntry,
  baseUrl,
  { cache = new DatasetCache(), fetchImpl = globalThis.fetch, cryptoImpl = globalThis.crypto } = {},
) {
  if (!shardEntry || typeof shardEntry.file !== "string"
      || !/^[a-f0-9]{64}$/.test(shardEntry.sha256)
      || !Number.isSafeInteger(shardEntry.record_count)
      || shardEntry.record_count < 0) {
    throw new Error("Manifest contains invalid shard metadata.");
  }
  const url = new URL(shardEntry.file, baseUrl);
  const base = new URL(baseUrl, globalThis.location?.href ?? "https://localhost/");
  if (url.origin !== base.origin || !url.pathname.startsWith(base.pathname.slice(0, base.pathname.lastIndexOf("/") + 1))) {
    throw new Error("Manifest shard must remain within its dataset directory.");
  }
  const key = `${url.href}#${shardEntry.sha256}`;
  const cached = await cache.get(key);
  if (cached) return validateShard(cached, shardEntry.record_count);

  const response = await fetchImpl(url.href, { credentials: "same-origin" });
  if (!response.ok) throw new Error(`Dataset download failed (HTTP ${response.status}).`);
  const bytes = await response.arrayBuffer();
  if (bytes.byteLength !== shardEntry.size_bytes) throw new Error("Dataset shard size does not match its manifest.");
  if (!cryptoImpl?.subtle) throw new Error("This browser cannot verify dataset integrity.");
  const digest = await cryptoImpl.subtle.digest("SHA-256", bytes);
  const sha256 = [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  if (sha256 !== shardEntry.sha256) throw new Error("Dataset shard SHA-256 does not match its manifest.");

  let shard;
  try {
    shard = JSON.parse(new TextDecoder().decode(bytes));
  } catch (error) {
    throw new Error("Dataset shard is not valid UTF-8 JSON.", { cause: error });
  }
  validateShard(shard, shardEntry.record_count);
  await cache.put(key, shard);
  return shard;
}

export async function loadDataset(entry, { fetchImpl = globalThis.fetch, cache, cryptoImpl } = {}) {
  if (!entry || typeof entry.manifest !== "string") throw new Error("Dataset catalog entry is invalid.");
  const manifestUrl = new URL(entry.manifest, globalThis.location?.href ?? "https://localhost/");
  const response = await fetchImpl(manifestUrl.href, { credentials: "same-origin" });
  if (!response.ok) throw new Error(`Dataset manifest could not be loaded (HTTP ${response.status}).`);
  const manifest = await response.json();
  if (manifest.authority !== entry.authority || manifest.exam !== entry.exam || manifest.year !== entry.year
      || manifest.greenlight_score !== 100 || manifest.record_count !== manifest.announced_count
      || !Array.isArray(manifest.shards) || manifest.shards.length !== manifest.shard_count) {
    throw new Error("Dataset manifest does not match the selected catalog entry or validation status.");
  }
  const shards = await Promise.all(manifest.shards.map((shard) =>
    fetchVerifiedShard(shard, manifestUrl.href, { cache, fetchImpl, cryptoImpl })
  ));
  const rows = shards.flatMap((shard) => shard.data);
  if (rows.length !== manifest.record_count) throw new Error("Combined dataset record count does not match its manifest.");
  return { manifest, rows };
}
