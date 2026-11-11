import test from "node:test";
import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";

globalThis.crypto ??= webcrypto;

import {
  validateReviewBundle,
  validateScreenshotFiles,
} from "./review-logic.mjs";

async function digest(bytes) {
  const value = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(value)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function candidate() {
  const bytes = new TextEncoder().encode("verified local screenshot");
  const screenshotHash = await digest(bytes);
  const records = [{ name: "AALA, TEST NAME", sequence_number: "1" }];
  return {
    bytes,
    bundle: {
      schema_version: 1,
      authority: "PRC",
      exam: "LEPT-ELEMENTARY",
      year: 2026,
      announced_count: 1,
      record_count: 1,
      official_article_url: "https://prc.gov.ph/article/march-2026-let-results",
      official_content_url: "https://drive.google.com/file/d/FILE123/view",
      public_preview_url: "https://drive.google.com/file/d/FILE123/preview",
      candidate_sha256: await digest(new TextEncoder().encode(JSON.stringify(records))),
      capture_manifest_sha256: "b".repeat(64),
      records,
      evidence: [{
        viewer_page: 1,
        sequence_numbers: ["1"],
        expected_visible_text: "1 AALA, TEST NAME",
        viewer_text_confirmed: true,
        sha256: screenshotHash,
        screenshot_path: "prc-lept-elementary-output/public-preview-capture/page-0001.png",
      }],
    },
  };
}

function localFile(bytes, relativePath) {
  const file = new File([bytes], "page-0001.png", { type: "image/png" });
  Object.defineProperty(file, "webkitRelativePath", { value: relativePath });
  return file;
}

test("validates compact review bundle and SHA-256-matched local screenshot", async () => {
  const { bytes, bundle } = await candidate();
  await validateReviewBundle(bundle);
  const file = localFile(
    bytes,
    "artifact/prc-lept-elementary-output/public-preview-capture/page-0001.png",
  );
  const urls = await validateScreenshotFiles(bundle, [file]);
  assert.equal(urls.size, 1);
  assert.ok(urls.get(bundle.evidence[0].screenshot_path).startsWith("blob:"));
  URL.revokeObjectURL(urls.get(bundle.evidence[0].screenshot_path));
});

test("rejects a screenshot whose bytes do not match the bundle hash", async () => {
  const { bundle } = await candidate();
  const file = localFile(
    new TextEncoder().encode("tampered screenshot"),
    "artifact/prc-lept-elementary-output/public-preview-capture/page-0001.png",
  );
  await assert.rejects(
    validateScreenshotFiles(bundle, [file]),
    /SHA-256 does not match/,
  );
});

test("rejects missing and ambiguous screenshot files", async () => {
  const { bytes, bundle } = await candidate();
  await assert.rejects(validateScreenshotFiles(bundle, []), /found 0/);
  const first = localFile(
    bytes,
    "one/prc-lept-elementary-output/public-preview-capture/page-0001.png",
  );
  const second = localFile(
    bytes,
    "two/prc-lept-elementary-output/public-preview-capture/page-0001.png",
  );
  await assert.rejects(
    validateScreenshotFiles(bundle, [first, second]),
    /found 2/,
  );
});

test("rejects path traversal in screenshot references", async () => {
  const { bundle } = await candidate();
  bundle.evidence[0].screenshot_path = "../outside/page-0001.png";
  await assert.rejects(validateReviewBundle(bundle), /invalid visual evidence/);
});
