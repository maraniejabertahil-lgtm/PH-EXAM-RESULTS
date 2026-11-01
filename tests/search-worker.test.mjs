import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { performance } from "node:perf_hooks";
import vm from "node:vm";

const source = readFileSync("public/assets/js/search.js", "utf8");
const messages = [];
const self = {
  postMessage(message) {
    messages.push(message);
  },
};
vm.runInNewContext(source, { self });

const rows = Array.from(
  { length: 50_000 },
  (_, index) => [`PASSER ${String(index).padStart(5, "0")}`]
);

self.onmessage({
  data: {
    type: "load",
    datasetKey: "synthetic-50k",
    columns: ["name"],
    rows,
  },
});
assert.equal(messages.at(-1).type, "loaded");

const start = performance.now();
self.onmessage({
  data: {
    type: "search",
    requestId: 1,
    query: "passer 49999",
  },
});
const elapsedMs = performance.now() - start;
const exactResult = messages.at(-1);
assert.equal(exactResult.type, "results");
assert.equal(exactResult.totalMatches, 1);
assert.equal(exactResult.matches[0][0], "PASSER 49999");

self.onmessage({
  data: {
    type: "search",
    requestId: 2,
    query: "passer",
  },
});
const broadResult = messages.at(-1);
assert.equal(broadResult.totalMatches, 50_000);
assert.equal(broadResult.matches.length, 100);

console.log(
  `50,000-row worker search passed; exact search took ${elapsedMs.toFixed(2)} ms.`
);
if (elapsedMs > 5_000) {
  throw new Error(`50,000-row search exceeded 5 seconds: ${elapsedMs.toFixed(2)} ms`);
}
