import test from "node:test";
import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { searchRecords } from "../assets/js/search-worker.mjs";
import { fetchVerifiedShard, loadDataset, validateShard } from "../assets/js/storage.mjs";

const columns = ["name", "rating", "region", "seq"];
const rows = [
  ["AALA, DESIREE JOY DE RAMOS", null, null, "1"],
  ["ABA, JUNAIRA M'LA", null, null, "2"],
  ["ABABA, LADY MAMAC", null, null, "3"],
];
const shard = { columns, data: rows };
const shardText = JSON.stringify(shard);
const shardBytes = new TextEncoder().encode(shardText);
const shardHash = [...new Uint8Array(await webcrypto.subtle.digest("SHA-256", shardBytes))]
  .map((byte) => byte.toString(16).padStart(2, "0")).join("");

class MemoryCache {
  constructor() { this.values = new Map(); }
  async get(key) { return this.values.get(key); }
  async put(key, value) { this.values.set(key, value); }
  async delete(key) { this.values.delete(key); }
}

function response(data, status = 200) {
  return new Response(data, { status, headers: { "content-type": "application/json" } });
}

test("searches case- and accent-insensitively and returns official sequence strings", () => {
  const result = searchRecords(rows, "aala, desiree");
  assert.equal(result.total, 1);
  assert.deepEqual(result.results[0], {
    name: "AALA, DESIREE JOY DE RAMOS",
    rating: null,
    region: null,
    sequence_number: "1",
  });
  assert.equal(searchRecords(rows, "aala, désirée").total, 1);
});

test("requires two query characters and caps returned rows without losing the total", () => {
  assert.deepEqual(searchRecords(rows, "A"), { results: [], total: 0, truncated: false });
  const result = searchRecords(rows, "a", 1);
  assert.equal(result.total, 0);
  const many = searchRecords(rows, "a", 1);
  assert.equal(many.total, 0);
  const capped = searchRecords(rows, "ab", 1);
  assert.equal(capped.total, 2);
  assert.equal(capped.results.length, 1);
  assert.equal(capped.truncated, true);
});

test("rejects shard schema and record count mismatches", () => {
  assert.throws(() => validateShard({ columns: ["name"], data: [] }, 0), /invalid schema/);
  assert.throws(() => validateShard(shard, 4), /record count/);
});

test("downloads and verifies a shard before caching it", async () => {
  const cache = new MemoryCache();
  let fetchCount = 0;
  const entry = {
    file: "records.json",
    sha256: shardHash,
    size_bytes: shardBytes.byteLength,
    record_count: rows.length,
  };
  const result = await fetchVerifiedShard(entry, "https://example.test/data/manifest.json", {
    cache,
    cryptoImpl: webcrypto,
    fetchImpl: async (url) => {
      fetchCount += 1;
      assert.equal(url, "https://example.test/data/records.json");
      return response(shardBytes);
    },
  });
  assert.deepEqual(result, shard);
  assert.equal(fetchCount, 1);
});

test("rejects hash mismatch and does not cache unverified data", async () => {
  const cache = new MemoryCache();
  const entry = {
    file: "records.json",
    sha256: "0".repeat(64),
    size_bytes: shardBytes.byteLength,
    record_count: rows.length,
  };
  await assert.rejects(
    fetchVerifiedShard(entry, "https://example.test/data/manifest.json", {
      cache,
      cryptoImpl: webcrypto,
      fetchImpl: async () => response(shardBytes),
    }),
    /SHA-256/,
  );
  assert.equal(cache.values.size, 0);
});

test("loads all manifest shards and checks catalog identity and counts", async () => {
  const manifest = {
    authority: "PRC",
    exam: "LEPT-ELEMENTARY",
    year: 2026,
    greenlight_score: 100,
    record_count: rows.length,
    announced_count: rows.length,
    shard_count: 1,
    shards: [{
      file: "records.json",
      sha256: shardHash,
      size_bytes: shardBytes.byteLength,
      record_count: rows.length,
    }],
  };
  const calls = [];
  const loaded = await loadDataset({
    authority: "PRC",
    exam: "LEPT-ELEMENTARY",
    year: 2026,
    manifest: "/data/PRC/LEPT-ELEMENTARY/2026/manifest.json",
  }, {
    cache: new MemoryCache(),
    cryptoImpl: webcrypto,
    fetchImpl: async (url) => {
      calls.push(url);
      if (url.endsWith("manifest.json")) return response(JSON.stringify(manifest));
      return response(shardBytes);
    },
  });
  assert.equal(loaded.rows.length, rows.length);
  assert.equal(calls.length, 2);

  await assert.rejects(
    loadDataset({
      authority: "CSC",
      exam: "LEPT-ELEMENTARY",
      year: 2026,
      manifest: "/data/manifest.json",
    }, {
      fetchImpl: async () => response(JSON.stringify(manifest)),
      cache: new MemoryCache(),
      cryptoImpl: webcrypto,
    }),
    /does not match/,
  );
});
