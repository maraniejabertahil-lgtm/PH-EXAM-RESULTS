import test from "node:test";
import assert from "node:assert/strict";
import { validateReviewBundle } from "../assets/js/review-logic.mjs";

async function digest(value) {
  const bytes = typeof value === "string" ? new TextEncoder().encode(value) : value;
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
    .map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function fixture() {
  const records = [{ name: "DOE, JANE", sequence_number: "0001" }];
  const canonicalRecords = JSON.stringify(records);
  const image = new Uint8Array([1, 2, 3]);
  return {
    schema_version: 1,
    authority: "PRC",
    exam: "LEPT-SECONDARY",
    year: 2026,
    announced_count: 1,
    record_count: 1,
    candidate_sha256: await digest(canonicalRecords),
    capture_manifest_sha256: "a".repeat(64),
    official_article_url: "https://prc.gov.ph/article",
    official_content_url: "https://drive.google.com/file/view",
    public_preview_url: "https://drive.google.com/file/preview",
    records,
    evidence: [{
      sequence_number: "0001",
      expected_visible_text: "0001 DOE, JANE",
      viewer_text_confirmed: true,
      sha256: await digest(image),
      image_data: `data:image/png;base64,${Buffer.from(image).toString("base64")}`,
    }],
  };
}

test("validates the candidate fingerprint and hash-bound source evidence", async () => {
  const bundle = await fixture();
  await assert.doesNotReject(validateReviewBundle(bundle));
});

test("rejects candidate changes and tampered screenshots", async () => {
  const changedRecord = await fixture();
  changedRecord.records[0].name = "DOE, JANE CHANGED";
  await assert.rejects(validateReviewBundle(changedRecord), /fingerprint/);
  const changedImage = await fixture();
  changedImage.evidence[0].image_data = "data:image/png;base64,AQIDBA==";
  await assert.rejects(validateReviewBundle(changedImage), /integrity/);
});

test("rejects non-HTTPS evidence links and records with numeric sequences", async () => {
  const badLink = await fixture();
  badLink.public_preview_url = "javascript:alert(1)";
  await assert.rejects(validateReviewBundle(badLink), /metadata/);
  const badSequence = await fixture();
  badSequence.records[0].sequence_number = 1;
  await assert.rejects(validateReviewBundle(badSequence), /record/);
});

test("requires visual evidence to cover every unique candidate sequence", async () => {
  const missingEvidence = await fixture();
  missingEvidence.records.push({ name: "ROE, RICHARD", sequence_number: "0002" });
  missingEvidence.record_count = 2;
  missingEvidence.announced_count = 2;
  missingEvidence.candidate_sha256 = await digest(JSON.stringify(missingEvidence.records));
  await assert.rejects(validateReviewBundle(missingEvidence), /cover every candidate record/);

  const duplicateSequence = await fixture();
  duplicateSequence.records.push({ name: "ROE, RICHARD", sequence_number: "0001" });
  duplicateSequence.record_count = 2;
  duplicateSequence.announced_count = 2;
  duplicateSequence.candidate_sha256 = await digest(JSON.stringify(duplicateSequence.records));
  await assert.rejects(validateReviewBundle(duplicateSequence), /duplicate sequence/);
});
