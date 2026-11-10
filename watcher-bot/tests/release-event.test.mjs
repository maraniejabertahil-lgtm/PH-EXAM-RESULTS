import test from "node:test";
import assert from "node:assert/strict";
import { buildReleaseEvent } from "../src/release-event.js";

const source = { id: "PRC-EXAM-RESULTS-HOMEPAGE", authority: "PRC" };
const officialArticle = {
  title: "November 2026 Veterinarians Computer-Based Licensure Examination Results Released in One (1) Working Day",
  url: "https://www.prc.gov.ph/node/9538",
  text: "The PRC announces that 1,083 out of 1,503 passed the Veterinarians Computer-Based Licensure Examination.",
  links: [
    {
      url: "https://drive.google.com/file/d/1OfficialVeterinariansList2026/view",
      label: "List of Successful Examinees"
    }
  ]
};

test("recognizes the official November 2026 Veterinarians result article", () => {
  const result = buildReleaseEvent(source, officialArticle);

  assert.equal(result.ok, true);
  assert.equal(result.event.exam_code, "VET");
  assert.equal(result.event.exam_year, 2026);
  assert.equal(result.event.announced_count, 1083);
  assert.equal(result.event.list_type, "successful_examinees");
  assert.deepEqual(result.event.content_urls, [{
    url: "https://drive.google.com/file/d/1OfficialVeterinariansList2026/view",
    format: "pdf"
  }]);
});

test("keeps unknown PRC exam titles in human review", () => {
  const result = buildReleaseEvent(source, {
    ...officialArticle,
    title: "November 2026 Unlisted Professional Examination Results Released"
  });

  assert.equal(result.ok, false);
  assert.match(result.reason, /exam code ambiguous or missing/);
});

test("keeps articles with more than one recognized exam in human review", () => {
  const result = buildReleaseEvent(source, {
    ...officialArticle,
    title: "November 2026 Certified Public Accountants and Veterinarians Licensure Examination Results Released"
  });

  assert.equal(result.ok, false);
  assert.match(result.reason, /exam code ambiguous or missing/);
});

test("dynamically identifies a previously unseen single-exam PRC headline", () => {
  const result = buildReleaseEvent(source, {
    ...officialArticle,
    title: "November 2026 Unlisted Professional Examination Results Released",
    text: "The PRC announces that 12 out of 20 passed.",
  });
  assert.equal(result.ok, true);
  assert.equal(result.event.exam_code, "EXAM-UNLISTED-PROFESSIONAL");
  assert.equal(result.event.exam_year, 2026);
  assert.equal(result.event.announced_count, 12);
});

test("keeps vague examination headlines in human review", () => {
  const result = buildReleaseEvent(source, {
    ...officialArticle,
    title: "November 2026 Examination Results Released",
  });
  assert.equal(result.ok, false);
  assert.match(result.reason, /ambiguous|safely identified/);
});
