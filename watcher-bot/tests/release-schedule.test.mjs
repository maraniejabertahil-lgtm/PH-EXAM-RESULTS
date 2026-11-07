import test from "node:test";
import assert from "node:assert/strict";
import {
  RELEASE_SCHEDULE_CACHE_KEY,
  parsePrcScheduleHtml,
  discoverSchedulePageUrls,
  robotsAllowsPath,
  refreshOfficialReleaseSchedule,
  getReleaseScheduleResponse
} from "../src/release-schedule.js";

class MemoryKV {
  constructor(initial = {}) { this.values = new Map(Object.entries(initial)); }
  async get(key) { return this.values.has(key) ? this.values.get(key) : null; }
  async put(key, value, options) { this.values.set(key, value); this.lastOptions = options; }
}

const scheduleHtml =
  '<html><table>' +
  '<tr><th>SEQ</th><th>NAME OF EXAMINATION</th><th>DATE/S OF EXAMINATION</th><th>DAY/S</th><th>TESTING CENTER/S</th><th colspan="2">APPLICATION PERIOD</th><th>TARGET DATE OF RELEASE OF EXAMINATION RESULTS</th><th>REQUIREMENTS</th></tr>' +
  '<tr><th></th><th></th><th></th><th></th><th></th><th>OPENING</th><th>DEADLINE</th><th></th><th></th></tr>' +
  '<tr><td>71</td><td>Veterinarians (CBLE)</td><td>November 04, 05, and 06, 2026</td><td>Wed, Thu, Fri</td><td>NCR</td><td>August 06, 2026</td><td>October 05, 2026</td><td>November 10, 2026</td><td>Click Here</td></tr>' +
  '<tr><td>72</td><td>Midwives</td><td>November 07 and 08, 2026</td><td>Sat, Sun</td><td>NCR</td><td>August 07, 2026</td><td>October 08, 2026</td><td>November 11, 2026</td><td>Click Here</td></tr>' +
  '<tr><td>73</td><td>Aeronautical Engineers (CBLE)</td><td>November 09, 10, and 11, 2026</td><td>Mon, Tue, Wed</td><td>NCR</td><td>August 11, 2026</td><td>October 12, 2026</td><td>November 13, 2026</td><td>Click Here</td></tr>' +
  '<tr><td>74</td><td>Old Examination</td><td>October 01, 2026</td><td>Thu</td><td>NCR</td><td>July 01, 2026</td><td>September 01, 2026</td><td>October 06, 2026</td><td>Click Here</td></tr>' +
  '</table></html>';

test("parses official PRC target-release column and chooses the nearest future date", () => {
  const now = new Date("2026-11-08T04:00:00.000Z");
  const result = parsePrcScheduleHtml(scheduleHtml, "https://www.prc.gov.ph/2026-schedule-examination", now);
  assert.equal(result.parsed_count, 4);
  assert.equal(result.upcoming_count, 3);
  assert.equal(result.nearest.exam, "Veterinarians (CBLE)");
  assert.equal(result.nearest.target_release_date, "2026-11-10");
  assert.equal(result.nearest.days_until, 2);
  assert.equal(result.upcoming[1].exam, "Midwives");
});

test("schedule index discovery accepts only same-origin current and next-year official paths", () => {
  const html = '<a href="/2025-schedule-examination">2025</a>' +
    '<a href="/2026-schedule-examination">2026</a>' +
    '<a href="https://www.prc.gov.ph/2027-schedule-examination">2027</a>' +
    '<a href="https://evil.example/2026-schedule-examination">bad</a>' +
    '<a href="/article/123">article</a>';
  const pages = discoverSchedulePageUrls(html, "https://www.prc.gov.ph/exam-schedules-menu", new Date("2026-11-08T00:00:00Z"));
  assert.deepEqual(pages, [
    { year: 2026, url: "https://www.prc.gov.ph/2026-schedule-examination" },
    { year: 2027, url: "https://www.prc.gov.ph/2027-schedule-examination" }
  ]);
});

test("robots rules block disallowed schedule pages and honor a more-specific Allow", () => {
  assert.equal(robotsAllowsPath("User-agent: *\nDisallow: /2026-schedule-examination", "/2026-schedule-examination"), false);
  assert.equal(robotsAllowsPath("User-agent: *\nDisallow: /\nAllow: /2026-schedule-examination$", "/2026-schedule-examination"), true);
  assert.equal(robotsAllowsPath("User-agent: *\nDisallow: /private/", "/2026-schedule-examination"), true);
});

test("refresh fetches official pages, checks robots, and stores the schedule snapshot", async () => {
  const source = {
    id: "PRC-OFFICIAL-SCHEDULE-INDEX",
    source_type: "official_schedule_index",
    authority: "PRC",
    authorized: true,
    enabled: true,
    url: "https://www.prc.gov.ph/exam-schedules-menu"
  };
  const kv = new MemoryKV();
  const calls = [];
  const fetchImpl = async (url) => {
    calls.push(url);
    if (url.endsWith("/robots.txt")) {
      return new Response("User-agent: *\nAllow: /exam-schedules-menu\nAllow: /2026-schedule-examination\n", {
        status: 200, headers: { "content-type": "text/plain" }
      });
    }
    if (url.endsWith("/exam-schedules-menu")) {
      return new Response('<a href="/2026-schedule-examination">2026</a>', {
        status: 200, headers: { "content-type": "text/html" }
      });
    }
    if (url.endsWith("/2026-schedule-examination")) {
      return new Response(scheduleHtml, { status: 200, headers: { "content-type": "text/html" } });
    }
    throw new Error("Unexpected URL " + url);
  };
  const now = new Date("2026-11-08T04:00:00.000Z");
  const result = await refreshOfficialReleaseSchedule({ sources: [source], kv, fetchImpl, now });
  assert.equal(result.status, "updated");
  assert.equal(result.snapshot.nearest.exam, "Veterinarians (CBLE)");
  assert.equal(calls.length, 3);
  assert.ok(kv.values.has(RELEASE_SCHEDULE_CACHE_KEY));
  assert.equal(kv.lastOptions.expirationTtl, 14 * 24 * 60 * 60);
});

test("refresh fails closed when robots.txt disallows the official schedule path", async () => {
  const source = {
    id: "PRC-OFFICIAL-SCHEDULE-INDEX",
    source_type: "official_schedule_index",
    authority: "PRC",
    authorized: true,
    enabled: true,
    url: "https://www.prc.gov.ph/exam-schedules-menu"
  };
  const kv = new MemoryKV();
  const fetchImpl = async (url) => {
    if (url.endsWith("/robots.txt")) return new Response("User-agent: *\nDisallow: /2026-schedule-examination", {
      status: 200, headers: { "content-type": "text/plain" }
    });
    if (url.endsWith("/exam-schedules-menu")) return new Response('<a href="/2026-schedule-examination">2026</a>', {
      status: 200, headers: { "content-type": "text/html" }
    });
    throw new Error("Schedule page must not be fetched when robots disallows it.");
  };
  const result = await refreshOfficialReleaseSchedule({
    sources: [source], kv, fetchImpl, now: new Date("2026-11-08T04:00:00.000Z")
  });
  assert.equal(result.status, "robots_disallowed");
  assert.equal(kv.values.has(RELEASE_SCHEDULE_CACHE_KEY), false);
});

test("fresh KV snapshot prevents repeated external schedule requests", async () => {
  const snapshot = { fetched_at: "2026-11-08T04:00:00.000Z", nearest: { exam: "Veterinarians" } };
  const kv = new MemoryKV({ [RELEASE_SCHEDULE_CACHE_KEY]: JSON.stringify(snapshot) });
  let calls = 0;
  const result = await refreshOfficialReleaseSchedule({
    sources: [{ source_type: "official_schedule_index", enabled: true, authorized: true, url: "https://www.prc.gov.ph/exam-schedules-menu" }],
    kv,
    fetchImpl: async () => { calls += 1; throw new Error("Should not fetch"); },
    now: new Date("2026-11-08T05:00:00.000Z")
  });
  assert.equal(result.status, "cached");
  assert.equal(result.snapshot.nearest.exam, "Veterinarians");
  assert.equal(calls, 0);
});

test("read-only upcoming endpoint returns cached public schedule data and rejects other paths", async () => {
  const snapshot = { authority: "PRC", upcoming_count: 1, nearest: { exam: "Veterinarians" } };
  const env = { PEAK_WEEK: new MemoryKV({ [RELEASE_SCHEDULE_CACHE_KEY]: JSON.stringify(snapshot) }) };
  const response = await getReleaseScheduleResponse(new Request("https://watcher.example/api/releases/upcoming"), env);
  assert.equal(response.status, 200);
  assert.equal((await response.json()).nearest.exam, "Veterinarians");
  assert.equal(response.headers.get("access-control-allow-origin"), "*");
  const missing = await getReleaseScheduleResponse(new Request("https://watcher.example/other"), env);
  assert.equal(missing.status, 404);
});
