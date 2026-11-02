import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const registry = JSON.parse(
  readFileSync(new URL("../../python-engine/config/sources.json", import.meta.url), "utf8")
);

test("source registry has unique, valid official sources and explicit disable reasons", () => {
  assert.ok(Array.isArray(registry.sources));
  const ids = new Set();
  for (const source of registry.sources) {
    assert.equal(typeof source.id, "string");
    assert.ok(source.id.trim());
    assert.ok(!ids.has(source.id), "duplicate source ID: " + source.id);
    ids.add(source.id);
    assert.ok(["PRC", "CSC"].includes(source.authority));
    assert.ok(["official", "verified_third_party"].includes(source.source_type));
    assert.equal(source.file_format, "pdf");
    if (source.enabled === true && source.source_type === "official") {
      assert.equal(source.authorized, true);
    } else if (source.enabled === false) {
      assert.equal(typeof source.disable_reason, "string");
      assert.ok(source.disable_reason.trim());
    } else {
      assert.fail("Source must be explicitly enabled or disabled: " + source.id);
    }
    const url = new URL(source.url);
    assert.equal(url.protocol, "https:");
    assert.ok(url.hostname);
    assert.equal(url.username, "");
    assert.equal(url.password, "");
    if (source.drive_file_ids !== undefined) {
      assert.ok(Array.isArray(source.drive_file_ids));
      for (const id of source.drive_file_ids) assert.match(id, /^[A-Za-z0-9_-]{10,200}$/);
    }
    if (source.allow_linked_drive_documents !== undefined) {
      assert.equal(typeof source.allow_linked_drive_documents, "boolean");
    }
    if (source.drive_link_text_patterns !== undefined) {
      assert.ok(Array.isArray(source.drive_link_text_patterns));
      for (const pattern of source.drive_link_text_patterns) {
        assert.equal(typeof pattern, "string");
        assert.ok(pattern.trim());
      }
    }
  }
});

test("CSC source remains paused until its official security verification barrier is resolved", () => {
  const source = registry.sources.find((item) => item.id === "CSC-CSE-PPT-2026-08-09-REGION-V");
  assert.ok(source);
  assert.equal(source.enabled, false);
  assert.equal(source.manual_drop_required, true);
  assert.match(source.disable_reason, /HTTP 403/i);
  assert.deepEqual(source.drive_file_ids, [
    "1jQmBLSU2azhFvCgU6l8m6ljXGDmIRa1l",
    "1qYaCbxIZ_6DHyMD9FhgZdj-YtbIJh5Wf"
  ]);
});

test("PRC source monitors the official exam-results listing and bounded article discovery", () => {
  const source = registry.sources.find((item) => item.id === "PRC-EXAM-RESULTS-HOMEPAGE");
  assert.ok(source);
  assert.equal(source.url, "https://www.prc.gov.ph/articles/exam-results");
  assert.equal(source.authority, "PRC");
  assert.equal(source.source_type, "official");
  assert.equal(source.authorized, true);
  assert.equal(source.enabled, true);
  assert.equal(source.file_format, "pdf");
  assert.equal(source.auto_acquire, false);
  assert.equal(source.scan_page_on_baseline, true);
  assert.equal(source.result_listing_page_count, 3);
  assert.equal(source.max_result_articles_per_scan, 3);
  assert.equal(source.allow_linked_drive_documents, true);
  assert.equal(source.discover_official_result_articles, true);
  assert.deepEqual(source.drive_link_text_patterns, ["list of successful examinees"]);
  assert.equal(source.direct_drive_fallback, false);
  assert.deepEqual(source.drive_file_ids, []);
  assert.deepEqual(source.preemptive_url_templates, []);
  assert.equal(source.robots_policy_verified, true);
  assert.equal(source.robots_policy_url, "https://www.prc.gov.ph/robots.txt");
});
