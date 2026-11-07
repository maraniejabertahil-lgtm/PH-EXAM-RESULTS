import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const status = JSON.parse(await readFile(new URL("../status.json", import.meta.url), "utf8"));
const html = await readFile(new URL("../index.html", import.meta.url), "utf8");
const app = await readFile(new URL("../assets/js/app.mjs", import.meta.url), "utf8");

test("public Owner Login entry is enabled after private production smoke checks", () => {
  assert.equal(status.owner_login_enabled, true);
  assert.match(html, /id="owner-login-open"/);
  assert.match(html, /id="owner-login-dialog"/);
  assert.match(html, /Owner Login.*دخول المالك/);
});

test("Owner Login visibility follows the explicit status flag and remains Firebase-first", () => {
  assert.match(app, /siteStatus\?\.owner_login_enabled === true/);
  assert.match(app, /fetch\(OWNER_DASHBOARD_URL \+ "\/auth\/firebase"/);
  assert.match(app, /result\.authenticated !== true/);
  assert.match(app, /location\.assign\(OWNER_DASHBOARD_URL/);
});
