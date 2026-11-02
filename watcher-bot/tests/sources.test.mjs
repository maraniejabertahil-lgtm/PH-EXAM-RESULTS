import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const registry = JSON.parse(
  readFileSync(new URL("../../python-engine/config/sources.json", import.meta.url), "utf8")
);

test("source registry has unique, valid, owner-authorized official sources", () => {
  assert.ok(Array.isArray(registry.sources));
  const ids = new Set();
  for (const source of registry.sources) {
    assert.equal(typeof source.id, "string");
    assert.ok(source.id.trim());
    assert.ok(!ids.has(source.id), "duplicate source ID: " + source.id);
    ids.add(source.id);
    assert.ok(["PRC", "CSC"].includes(source.authority));
    assert.ok(["official", "verified_third_party"].includes(source.source_type));
    assert.equal(source.enabled, true);
    if (source.source_type === "official") assert.equal(source.authorized, true);
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

test("PRC homepage connectivity source cannot dispatch historical attachments on baseline", () => {
  const source = registry.sources.find((item) => item.id === "PRC-EXAM-RESULTS-HOMEPAGE");
  assert.ok(source);
  assert.equal(source.url, "https://www.prc.gov.ph/");
  assert.equal(source.authority, "PRC");
  assert.equal(source.source_type, "official");
  assert.equal(source.authorized, true);
  assert.equal(source.enabled, true);
  assert.equal(source.scan_page_on_baseline, false);
  assert.equal(source.allow_linked_drive_documents, false);
  assert.equal(source.direct_drive_fallback, false);
  assert.deepEqual(source.drive_file_ids, []);
});
