import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const status = JSON.parse(await readFile(new URL("../status.json", import.meta.url), "utf8"));
const html = await readFile(new URL("../index.html", import.meta.url), "utf8");
const css = await readFile(new URL("../assets/css/owner-login.css", import.meta.url), "utf8");
const app = await readFile(new URL("../assets/js/app.mjs", import.meta.url), "utf8");

test("public header contains only the accessible Log in icon", () => {
  assert.equal(status.owner_login_enabled, true);
  const header = html.match(/<header class="site-header">([\s\S]*?)<\/header>/)?.[1];
  assert.ok(header, "site header must exist");
  assert.match(header, /<div class="header-actions">\s*<button id="owner-login-open"/);
  assert.equal((header.match(/<button\b/g) || []).length, 1, "the Log in icon must be the only header button");
  assert.match(header, /class="owner-login-icon"/);
  assert.match(header, /aria-label="Log in"/);
  assert.match(header, /title="Log in"/);
  assert.doesNotMatch(header, /search|release\s*status|menu|ellipsis/i, "Search, Release Status, and overflow controls must not appear in the header");
  assert.match(html, /id="owner-login-dialog"/);
  const loginDisplay = html.match(/<dialog id="owner-login-dialog"[\s\S]*?<\/dialog>/)?.[0] || "";
  assert.doesNotMatch(loginDisplay, /[\u0600-\u06FF]/, "the login display must contain English only");
  assert.doesNotMatch(header, /[\u0600-\u06FF]/, "the login icon must contain English only");
  assert.doesNotMatch(header, /class="header-note"/);
  assert.match(css, /\.header-actions\{[^}]*margin-left:auto/);
  assert.match(css, /\.owner-login-button\{[^}]*border-radius:50%/);
});

test("Log in icon opens the Firebase Owner login flow", () => {
  assert.match(app, /ownerLogin\.open\?\.addEventListener\("click", showOwnerLogin\)/);
  assert.doesNotMatch(app, /ownerLogin\.open\.hidden\s*=/, "runtime status must never hide the permanent Log in icon");
  assert.match(app, /fetch\(OWNER_DASHBOARD_URL \+ "\/auth\/firebase"/);
  assert.match(app, /result\.authenticated !== true/);
  assert.match(app, /location\.assign\(OWNER_DASHBOARD_URL/);
});
