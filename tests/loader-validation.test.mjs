import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const loaderSource = readFileSync("public/assets/js/loader.js", "utf8")
  .replace('import { getCachedDataset, setCachedDataset } from "./storage.js";', "");
const loaderUrl = "data:text/javascript;base64," + Buffer.from(loaderSource).toString("base64");
const { selectShards, validateDatasetPayload } = await import(loaderUrl);

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

console.log("Public dataset structure validation tests passed.");
