import test from "node:test";
import assert from "node:assert/strict";
import { isApprovedPrcSource, selectApprovedSource, validateDriveUrl } from "../../tools/extract-prc-pdf.mjs";

const approved = {
  id: "PRC-NLE-2026-02", authority: "PRC", exam: "NLE",
  source_type: "official", authorized: true, enabled: true,
  drive_file_id: "1pyanD6eierylQeohhy2wm4HBWCfuSYX6"
};

test("accepts explicitly approved official PRC sources across exam types", () => {
  assert.equal(isApprovedPrcSource(approved), true);
  assert.equal(isApprovedPrcSource({ ...approved, exam: "LEPT" }), true);
});

test("rejects non-PRC, unapproved, disabled, non-official, or malformed sources", () => {
  for (const patch of [
    { authority: "CSC" }, { authorized: false }, { enabled: false },
    { source_type: "unverified" }, { exam: "" }, { drive_file_id: "../etc/passwd" }
  ]) assert.equal(isApprovedPrcSource({ ...approved, ...patch }), false);
});

test("requires one exact registry ID and refuses duplicates", () => {
  assert.equal(selectApprovedSource({ sources: [approved] }, approved.id), approved);
  assert.throws(() => selectApprovedSource({ sources: [approved] }, "missing"), /exactly one/);
  assert.throws(() => selectApprovedSource({ sources: [approved, approved] }, approved.id), /exactly one/);
});

test("allows only HTTPS Drive download URLs retaining the exact file ID", () => {
  const good = new URL("https://drive.google.com/uc?export=download&id=" + approved.drive_file_id);
  assert.doesNotThrow(() => validateDriveUrl(good, approved.drive_file_id));
  const alternateHost = new URL("https://evil.example/uc?id=" + approved.drive_file_id);
  const wrongId = new URL("https://drive.google.com/uc?id=another-file-id");
  const http = new URL("http://drive.google.com/uc?id=" + approved.drive_file_id);
  const wrongPath = new URL("https://drive.google.com/file/d/" + approved.drive_file_id);
  for (const url of [alternateHost, wrongId, http, wrongPath]) {
    assert.throws(() => validateDriveUrl(url, approved.drive_file_id), /Blocked Google Drive redirect/);
  }
});
