import test from "node:test";
import assert from "node:assert/strict";
import { createDiagnosticReference, safeErrorMessage } from "../assets/js/error-messages.mjs";

test("user-facing error messages are safe and context-specific", () => {
  assert.match(safeErrorMessage("startup"), /Published results could not be loaded/);
  assert.match(safeErrorMessage("dataset"), /could not be loaded or verified/);
  assert.match(safeErrorMessage("search"), /Search could not be completed/);
  assert.match(safeErrorMessage("unexpected"), /Something went wrong/);
  assert.equal(safeErrorMessage("unrecognized"), safeErrorMessage("unexpected"));
});

test("diagnostic reference is generated locally without user data", () => {
  const reference = createDiagnosticReference({
    randomUUID: () => "00000000-0000-4000-8000-000000000001",
  });
  assert.equal(reference, "00000000-0000-4000-8000-000000000001");
  assert.doesNotMatch(reference, /name|query|email/i);
});

test("diagnostic reference has a local fallback when crypto UUID is unavailable", () => {
  const reference = createDiagnosticReference({});
  assert.match(reference, /^[a-z0-9]+-[a-z0-9]+$/);
});
