import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const loaderSource = readFileSync("public/assets/js/loader.js", "utf8")
  .replace('import { getCachedDataset, setCachedDataset } from "./storage.js";', "");
const loaderUrl = "data:text/javascript;base64," + Buffer.from(loaderSource).toString("base64");
const { fetchWithTimeout, loadSiteStatus, selectShards, validateDatasetPayload, validateManifestFileEntry } = await import(loaderUrl);

const valid = {
  columns: ["name", "rating", "region", "seq"],
  data: [["JUAN DELA CRUZ", 85.5, "NCR", 1]]
};

assert.equal(validateDatasetPayload(valid, 1), valid);
assert.throws(() => validateDatasetPayload(valid, 2), /record count/);

const shardFiles = {
  "A-M": { path: "/data/a-m.json" },
  "N-Z": { path: "/data/n-z.json" },
  OTHER: { path: "/data/other.json" }
};
assert.deepEqual(selectShards(shardFiles), Object.values(shardFiles));

const validHash = "a".repeat(64);
const validManifestFile = {
  path: `/data/prc/let/2026-A-M-${validHash}.json`,
  hash: validHash,
  record_count: 1,
  size_bytes: 100
};
assert.equal(
  validateManifestFileEntry(validManifestFile, "PRC", "LET", "2026", "A-M"),
  validManifestFile
);
assert.throws(
  () => validateManifestFileEntry({ ...validManifestFile, path: "/outside/2026-A-M.json" }, "PRC", "LET", "2026", "A-M"),
  /invalid dataset reference/
);
assert.throws(
  () => validateManifestFileEntry({ ...validManifestFile, hash: "bad" }, "PRC", "LET", "2026", "A-M"),
  /invalid dataset reference/
);
assert.throws(
  () => validateManifestFileEntry({ ...validManifestFile, record_count: 0 }, "PRC", "LET", "2026", "A-M"),
  /invalid dataset reference/
);
assert.throws(
  () => validateManifestFileEntry({ ...validManifestFile, size_bytes: 11 * 1024 * 1024 }, "PRC", "LET", "2026", "A-M"),
  /invalid dataset reference/
);
assert.throws(
  () => validateDatasetPayload({ columns: ["rating"], data: [[85]] }),
  /invalid structure/
);
assert.throws(
  () => validateDatasetPayload({ columns: ["name", "name"], data: [["A", "A"]] }),
  /invalid structure/
);
assert.throws(
  () => validateDatasetPayload({ columns: ["name", "rating", "region", "seq"], data: [["A"]] }),
  /invalid record/
);
assert.throws(
  () => validateDatasetPayload({ columns: ["name", "rating", "region", "seq"], data: [[null, null, null, null]] }),
  /invalid record/
);
assert.throws(
  () => validateDatasetPayload({ columns: ["name", "rating", "region", "seq"], data: [["   ", null, null, null]] }),
  /invalid record/
);
assert.throws(
  () => validateDatasetPayload({ columns: ["name", "rating", "region", "seq"], data: [["A", "85", null, null]] }),
  /invalid record/
);
assert.throws(
  () => validateDatasetPayload({ columns: ["name", "rating", "region", "seq"], data: [["A", null, 123, null]] }),
  /invalid record/
);
assert.throws(
  () => validateDatasetPayload({ columns: ["name", "rating", "region", "seq"], data: [["A", null, null, -1]] }),
  /invalid record/
);

const originalFetch = globalThis.fetch;
try {
  globalThis.fetch = async (url, options) => ({ url, signal: options.signal });
  const response = await fetchWithTimeout("/test-resource", {}, 1000);
  assert.equal(response.url, "/test-resource");
  assert.ok(response.signal instanceof AbortSignal);

  globalThis.fetch = async () => {
    throw new DOMException("Request aborted", "AbortError");
  };
  await assert.rejects(
    fetchWithTimeout("/slow-resource", {}, 1000),
    /took too long/
  );
  assert.deepEqual(
    await loadSiteStatus(),
    { mode: "search", preparation: null }
  );

  globalThis.fetch = async () => ({
    ok: true,
    json: async () => ({
      schema_version: 1,
      mode: "preparing",
      preparation: { percentage: 50 }
    })
  });
  assert.equal((await loadSiteStatus()).mode, "preparing");
} finally {
  globalThis.fetch = originalFetch;
}

console.log("Public dataset structure validation tests passed.");
