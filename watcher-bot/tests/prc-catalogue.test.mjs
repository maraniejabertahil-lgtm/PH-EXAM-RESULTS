import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const catalogueUrl = new URL("../../python-engine/config/prc-examination-catalogue.json", import.meta.url);
const catalogue = JSON.parse(await readFile(catalogueUrl, "utf8"));

test("PRC examination catalogue declares its official 2026 schedule provenance", () => {
  assert.equal(catalogue.schema_version, 1);
  assert.equal(catalogue.authority, "Professional Regulation Commission");
  assert.equal(catalogue.catalogue_type, "examination_names");
  assert.match(catalogue.source.url, /^https:\/\/www\.prc\.gov\.ph\//);
  assert.match(catalogue.source.official_pdf_url, /^https:\/\/www\.prc\.gov\.ph\/.*\.pdf$/);
  assert.equal(catalogue.source.resolution, "Resolution No. 2113 s. 2025");
});

test("PRC examination entries have unique stable IDs and names", () => {
  assert.ok(Array.isArray(catalogue.examinations));
  assert.equal(catalogue.examinations.length, catalogue.counts.total_catalogue_entries);
  const ids = catalogue.examinations.map((item) => item.id);
  const names = catalogue.examinations.map((item) => item.name);
  assert.equal(new Set(ids).size, ids.length, "examination IDs must be unique");
  assert.equal(new Set(names).size, names.length, "canonical examination names must be unique");
  for (const item of catalogue.examinations) {
    assert.match(item.id, /^PRC-[A-Z0-9-]+$/);
    assert.equal(typeof item.name, "string");
    assert.ok(item.name.trim().length > 0);
    if (item.variants !== undefined) {
      assert.ok(Array.isArray(item.variants));
      assert.ok(item.variants.every((variant) => typeof variant === "string" && variant.trim()));
    }
  }
});

test("catalogue keeps profession categories separate from the SPLE umbrella", () => {
  const professions = catalogue.examinations.filter((item) => item.id !== "PRC-SPLE");
  const sple = catalogue.examinations.filter((item) => item.id === "PRC-SPLE");
  assert.equal(professions.length, catalogue.counts.named_professional_exam_categories);
  assert.equal(sple.length, catalogue.counts.separate_sple_umbrella_entries);
  assert.equal(catalogue.counts.numbered_2026_schedule_sittings, 88);
  assert.match(catalogue.scope, /not a complete historical register/i);
});

const sourceRegistryUrl = new URL("../../python-engine/config/prc-sources.json", import.meta.url);
const sourceRegistry = JSON.parse(await readFile(sourceRegistryUrl, "utf8"));

test("PRC source records match the watcher and extractor contracts", () => {
  assert.ok(Array.isArray(sourceRegistry.sources));
  assert.ok(sourceRegistry.sources.length > 0);
  const ids = new Set();
  for (const source of sourceRegistry.sources) {
    assert.equal(source.authority, "PRC");
    assert.equal(source.source_type, "official");
    assert.equal(source.authorized, true);
    assert.equal(source.enabled, true);
    assert.equal(typeof source.exam, "string");
    assert.ok(source.exam.trim());
    assert.equal(source.url, source.announcement_url);
    assert.match(source.url, /^https:\/\/www\.prc\.gov\.ph\//);
    assert.ok(Array.isArray(source.drive_file_ids));
    assert.deepEqual(source.drive_file_ids, [source.drive_file_id]);
    assert.equal(source.scan_page_on_baseline, true);
    assert.equal(source.direct_drive_fallback, true);
    assert.ok(!ids.has(source.id), "source IDs must be unique");
    ids.add(source.id);
  }
});
