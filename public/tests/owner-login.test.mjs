import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const status = JSON.parse(await readFile(new URL("../status.json", import.meta.url), "utf8"));
const html = await readFile(new URL("../index.html", import.meta.url), "utf8");
const css = await readFile(new URL("../assets/css/owner-login.css", import.meta.url), "utf8");
const app = await readFile(new URL("../assets/js/app.mjs", import.meta.url), "utf8");
const headers = await readFile(new URL("../_headers", import.meta.url), "utf8");

test("public header contains only the accessible Log in icon", () => {
  assert.equal(status.owner_login_enabled, true);
  const start = html.indexOf('<header class="site-header">');
  const end = html.indexOf("</header>", start);
  assert.notEqual(start, -1, "site header must exist");
  assert.notEqual(end, -1, "site header must close");
  const header = html.slice(start, end);
  assert.ok(header.includes('<div class="header-actions">'));
  assert.ok(header.includes('<button id="owner-login-open"'));
  assert.equal((header.match(/<button\b/g) || []).length, 1, "the Log in icon must be the only header button");
  assert.ok(header.includes('class="owner-login-icon"'));
  assert.ok(header.includes('aria-label="Log in"'));
  assert.ok(header.includes('title="Log in"'));
  assert.doesNotMatch(header, /search|release\s*status|menu|ellipsis/i);
  assert.ok(html.includes('id="owner-login-dialog"'));
  const loginStart = html.indexOf('<dialog id="owner-login-dialog"');
  const loginEnd = html.indexOf("</dialog>", loginStart);
  const loginDisplay = html.slice(loginStart, loginEnd);
  assert.equal([...loginDisplay].some((character) => character >= "\u0600" && character <= "\u06FF"), false);
  assert.equal([...header].some((character) => character >= "\u0600" && character <= "\u06FF"), false);
  assert.ok(!header.includes('class="header-note"'));
  assert.match(css, /\.header-actions\{[^}]*margin-left:auto/);
  assert.match(css, /\.owner-login-button\{[^}]*border-radius:50%/);
});

test("Log in icon uses the same-origin proxy before opening the private dashboard", () => {
  assert.ok(app.includes('ownerLogin.open?.addEventListener("click", showOwnerLogin)'));
  assert.ok(!app.includes("ownerLogin.open.hidden ="), "runtime status must never hide the permanent Log in icon");
  assert.ok(app.includes('fetch("/auth/firebase"'));
  assert.ok(!app.includes('fetch(OWNER_DASHBOARD_URL + "/auth/firebase"'),
    "browser login must not depend on a cross-origin dashboard request");
  assert.ok(app.includes("result.authenticated !== true"));
  assert.ok(app.includes("location.assign(OWNER_DASHBOARD_URL"));
});

test("public CSP no longer needs a cross-origin connection for Owner login", () => {
  assert.ok(headers.includes("connect-src 'self';"));
  assert.ok(!headers.includes("ph-exam-results-owner.pages.dev"));
});
