import test from "node:test";
import assert from "node:assert/strict";
import { buildReleaseEvent } from "../src/release-event.js";

const source = { id: "PRC-EXAM-RESULTS-HOMEPAGE" };
const articleBase = {
  title: "October 2026 Certified Public Accountants Licensure Examination Results Released",
  url: "https://www.prc.gov.ph/node/12345",
  text: "3,988 passers",
};

function drive(id, label) {
  return { url: `https://drive.google.com/file/d/${id}/view`, label };
}

test("release identification selects the uniquely labelled successful-examinees list", () => {
  const result = buildReleaseEvent(source, {
    ...articleBase,
    links: [
      drive("1FullCPAResultDocument2026", "Full text of the Official Result"),
      drive("1CPAPerformanceSchools2026", "Performance of Schools"),
      drive("1CPATopTenPlacesDoc2026", "Successful Examinees who garnered the top 10 highest places"),
      drive("1CPASuccessfulExaminees2026", "List of Successful Examinees"),
    ],
  });
  assert.equal(result.ok, true);
  assert.equal(result.event.exam_code, "CPALE");
  assert.equal(result.event.exam_year, 2026);
  assert.equal(result.event.announced_count, 3988);
  assert.equal(result.event.content_urls.length, 1);
  assert.equal(result.event.content_urls[0].label, "List of Successful Examinees");
  assert.match(result.event.content_urls[0].url, /1CPASuccessfulExaminees2026/);
});

test("release identification fails closed when multiple links claim to be the passer list", () => {
  const result = buildReleaseEvent(source, {
    ...articleBase,
    links: [
      drive("1CPASuccessfulExamineesA2026", "List of Successful Examinees"),
      drive("1CPASuccessfulExamineesB2026", "List of Passers"),
    ],
  });
  assert.equal(result.ok, false);
  assert.match(result.reason, /uniquely labelled successful-examinees list/);
});

test("release identification never mistakes a top-ten document for the passer list", () => {
  const result = buildReleaseEvent(source, {
    ...articleBase,
    links: [
      drive("1CPATopTenPlacesDoc2026", "Successful Examinees who garnered the top 10 highest places"),
      drive("1CPAPerformanceSchools2026", "Performance of Schools"),
    ],
  });
  assert.equal(result.ok, false);
  assert.match(result.reason, /uniquely labelled successful-examinees list/);
});

test("single supported content link remains compatible with existing official articles", () => {
  const result = buildReleaseEvent(source, {
    ...articleBase,
    links: [drive("1SingleOfficialResult2026", "Official list")],
  });
  assert.equal(result.ok, true);
  assert.equal(result.event.content_urls.length, 1);
});
