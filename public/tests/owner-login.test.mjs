import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const status = JSON.parse(await readFile(new URL("../status.json", import.meta.url), "utf8"));
const html = await readFile(new URL("../index.html", import.meta.url), "utf8");
const css = await readFile(new URL("../assets/css/owner-login.css", import.meta.url), "utf8");
const app = await readFile(new URL("../assets/js/app.mjs", import.meta.url), "utf8");

test("public Owner Login entry is enabled and placed as an accessible top-right icon", () => {
  assert.equal(status.owner_login_enabled, true);
  assert.match(html, /<div class="header-actions">\s*<button id="owner-login-open"/);
  assert.match(html, /class="owner-login-icon"/);
  assert.match(html, /aria-label="Owner Login · دخول المالك"/);
  assert.match(html, /id="owner-login-dialog"/);
  assert.doesNotMatch(html, /class="header-note"/);
  assert.match(css, /\.header-actions\{[^}]*margin-left:auto/);
  assert.match(css, /\.owner-login-button\{[^}]*border-radius:50%/);
});

test("Owner Login stays available while status is loading, and obeys an explicit disable flag", () => {
  assert.match(app, /siteStatus\?\.owner_login_enabled !== false/);
  assert.match(app, /fetch\(OWNER_DASHBOARD_URL \+ "\/auth\/firebase"/);
  assert.match(app, /result\.authenticated !== true/);
  assert.match(app, /location\.assign\(OWNER_DASHBOARD_URL/);
});
