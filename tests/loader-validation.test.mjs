import assert from "node:assert/strict";
import { validateDatasetPayload } from "../public/assets/js/loader.js";

const valid = {
  columns: ["name", "rating", "region", "seq"],
  data: [["JUAN DELA CRUZ", 85.5, "NCR", 1]]
};

assert.equal(validateDatasetPayload(valid), valid);
assert.throws(
  () => validateDatasetPayload({ columns: ["rating"], data: [[85]] }),
  /invalid structure/
);
assert.throws(
  () => validateDatasetPayload({ columns: ["name", "name"], data: [["A", "A"]] }),
  /invalid structure/
);
assert.throws(
  () => validateDatasetPayload({ columns: ["name", "rating"], data: [["A"]] }),
  /invalid record/
);
assert.throws(
  () => validateDatasetPayload({ columns: ["name"], data: [[null]] }),
  /invalid record/
);
assert.throws(
  () => validateDatasetPayload({ columns: ["name"], data: [["   "]] }),
  /invalid record/
);

console.log("Public dataset structure validation tests passed.");
