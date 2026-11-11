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

test("selects only the uniquely labelled successful-examinee roster from multiple official PRC links", () => {
  const result = buildReleaseEvent(source, {
    ...officialArticle,
    links: [
      { url: "https://drive.google.com/file/d/1FullTextOfficialResult2026/view", label: "Full text of the Official Result" },
      { url: "https://drive.google.com/file/d/1PerformanceSchools2026/view", label: "Performance of Schools" },
      { url: "https://drive.google.com/file/d/1TopTenSuccessfulExaminees2026/view", label: "Successful Examinees who garnered the top 10 highest places" },
      { url: "https://drive.google.com/file/d/1AlphabeticalRoster2026/view", label: "List of Successful Examinees" }
    ]
  });
  assert.equal(result.ok, true);
  assert.deepEqual(result.event.content_urls, [{
    url: "https://drive.google.com/file/d/1AlphabeticalRoster2026/view",
    format: "pdf"
  }]);
});

test("keeps multiple official links in human review when the roster label is missing or duplicated", () => {
  const missing = buildReleaseEvent(source, {
    ...officialArticle,
    links: [
      { url: "https://drive.google.com/file/d/1TopTen2026/view", label: "Top Ten" },
      { url: "https://drive.google.com/file/d/1Schools2026/view", label: "Performance of Schools" }
    ]
  });
  assert.equal(missing.ok, false);
  assert.match(missing.reason, /unique labelled successful-examinee list/);

  const duplicated = buildReleaseEvent(source, {
    ...officialArticle,
    links: [
      { url: "https://drive.google.com/file/d/1RosterA2026/view", label: "List of Successful Examinees" },
      { url: "https://drive.google.com/file/d/1RosterB2026/view", label: "Roll of Successful Examinees" }
    ]
  });
  assert.equal(duplicated.ok, false);
  assert.match(duplicated.reason, /unique labelled successful-examinee list/);
});

test("recognizes a new single-exam PRC title without a fixed allowlist entry", () => {
  const result = buildReleaseEvent(source, {
    ...officialArticle,
    title: "November 2026 Unlisted Professional Examination Results Released"
  });

  assert.equal(result.ok, true);
  assert.equal(result.event.exam_code, "EXAM-UNLISTED-PROFESSIONAL");
  assert.equal(result.event.exam_year, 2026);
  assert.equal(result.event.announced_count, 1083);
});

test("keeps articles with more than one recognized exam in human review", () => {
  const result = buildReleaseEvent(source, {
    ...officialArticle,
    title: "November 2026 Certified Public Accountants and Veterinarians Licensure Examination Results Released"
  });

  assert.equal(result.ok, false);
  assert.match(result.reason, /ambiguous|safely identified/);
});

test("dynamically identifies a previously unseen single-exam PRC headline", () => {
  const result = buildReleaseEvent(source, {
    ...officialArticle,
    title: "November 2026 Unlisted Professional Examination Results Released",
    text: "The PRC announces that 123 out of 200 passed.",
  });
  assert.equal(result.ok, true);
  assert.equal(result.event.exam_code, "EXAM-UNLISTED-PROFESSIONAL");
  assert.equal(result.event.exam_year, 2026);
  assert.equal(result.event.announced_count, 123);
});

test("keeps vague examination headlines in human review", () => {
  const result = buildReleaseEvent(source, {
    ...officialArticle,
    title: "November 2026 Examination Results Released",
  });
  assert.equal(result.ok, false);
  assert.match(result.reason, /ambiguous|safely identified/);
});


const leptArticle = {
  title: "March 2026 Licensure Examination for Professional Teachers Results Released in Thirty-Nine (39) Working Days",
  url: "https://prc.gov.ph/article/march-2026-licensure-examination-professional-teachers-results-released-thirty-nine-39",
  text: "The PRC announces that 18,376 elementary teachers out of 32,796 examinees and 45,001 secondary teachers out of 61,561 examinees successfully passed the Licensure Examination for Professional Teachers given March 15, 2026.",
  links: [
    { url: "https://drive.google.com/file/d/1FullTextOfficialResult/view", label: "Full text of the Official Result" },
    { url: "https://drive.google.com/file/d/1kY0CTSuwdxDwnf1UEvWe27HDEXU3rolE/view?usp=sharing", label: "List of Successful Examinees for Elementary" },
    { url: "https://drive.google.com/file/d/1RFuFGN4D1T3hkGC-iib9pRmJP1vJiJJ7/view?usp=sharing", label: "List of Successful Examinees for Secondary" }
  ]
};

test("selects the Elementary LEPT roster and its own announced count", () => {
  const result = buildReleaseEvent(source, leptArticle, { resultLevel: "elementary" });
  assert.equal(result.ok, true);
  assert.equal(result.event.exam_code, "LEPT");
  assert.equal(result.event.result_level, "elementary");
  assert.equal(result.event.announced_count, 18376);
  assert.deepEqual(result.event.content_urls, [{
    url: "https://drive.google.com/file/d/1kY0CTSuwdxDwnf1UEvWe27HDEXU3rolE/view?usp=sharing",
    format: "pdf"
  }]);
});

test("selects the Secondary LEPT roster and its own announced count", () => {
  const result = buildReleaseEvent(source, leptArticle, { resultLevel: "secondary" });
  assert.equal(result.ok, true);
  assert.equal(result.event.exam_code, "LEPT");
  assert.equal(result.event.result_level, "secondary");
  assert.equal(result.event.announced_count, 45001);
  assert.deepEqual(result.event.content_urls, [{
    url: "https://drive.google.com/file/d/1RFuFGN4D1T3hkGC-iib9pRmJP1vJiJJ7/view?usp=sharing",
    format: "pdf"
  }]);
});

test("keeps multi-level LEPT articles in review unless a roster level is selected", () => {
  const result = buildReleaseEvent(source, leptArticle);
  assert.equal(result.ok, false);
  assert.match(result.reason, /result level is ambiguous/);
});
