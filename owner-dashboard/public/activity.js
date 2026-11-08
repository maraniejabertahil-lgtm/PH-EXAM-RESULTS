const $ = (selector) => document.querySelector(selector);
const state = { days: 30, csrf: "", events: [] };
const number = (value) => Number.isFinite(Number(value)) ? Number(value) : 0;
const fmt = (value) => new Intl.NumberFormat().format(number(value));
const dateLabel = (value) => new Date(value + "T00:00:00Z").toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });

async function initializeAuth() {
  try {
    const response = await fetch("/auth/session", { credentials: "same-origin", cache: "no-store" });
    const session = await response.json();
    if (session.authenticated) {
      state.csrf = session.csrf;
      $("#sign-in-link").hidden = true;
      $("#sign-out-button").hidden = false;
      return true;
    }
  } catch { /* signed out */ }
  $("#sign-in-link").hidden = false;
  $("#sign-out-button").hidden = true;
  return false;
}

function setMetric(id, value, hint) {
  $(id).textContent = value;
  if (hint) $(hint).textContent = "";
}

function makeSvg(tag, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  return node;
}

function smoothPath(points) {
  if (!points.length) return "";
  let path = "M " + points[0].x + " " + points[0].y;
  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1], current = points[i], mid = (prev.x + current.x) / 2;
    path += " Q " + mid + " " + prev.y + " " + current.x + " " + current.y;
  }
  return path;
}

function drawChart(target, labels, series) {
  const host = $(target);
  host.replaceChildren();
  const hasData = series.some((item) => item.values.some((value) => value > 0));
  if (!hasData) {
    const empty = document.createElement("p");
    empty.className = "chart-empty";
    empty.textContent = "No recorded activity in this period";
    host.append(empty);
    return;
  }
  const width = 720, height = 180, left = 10, right = 10, top = 12, bottom = 25;
  const plotWidth = width - left - right, plotHeight = height - top - bottom;
  const max = Math.max(1, ...series.flatMap((item) => item.values)) * 1.12;
  const svg = makeSvg("svg", { viewBox: "0 0 720 180", role: "img", "aria-label": "Trend line chart" });
  for (let i = 0; i < 4; i++) {
    const y = top + plotHeight * i / 3;
    svg.append(makeSvg("line", { x1: left, y1: y, x2: width - right, y2: y, class: "chart-gridline" }));
  }
  for (const item of series) {
    const points = item.values.map((value, index) => ({
      x: left + (labels.length < 2 ? plotWidth / 2 : plotWidth * index / (labels.length - 1)),
      y: top + plotHeight - (value / max) * plotHeight,
    }));
    const path = smoothPath(points);
    if (item.area) {
      const area = path + " L " + points[points.length - 1].x + " " + (top + plotHeight) +
        " L " + points[0].x + " " + (top + plotHeight) + " Z";
      svg.append(makeSvg("path", { d: area, class: "chart-area" }));
    }
    svg.append(makeSvg("path", { d: path, class: "chart-line" + (item.secondary ? " secondary" : "") }));
    const last = points[points.length - 1];
    if (last) svg.append(makeSvg("circle", { cx: last.x, cy: last.y, r: 4, class: "chart-dot" }));
  }
  const labelIndexes = [...new Set([0, Math.floor((labels.length - 1) / 2), labels.length - 1])];
  for (const index of labelIndexes) {
    const x = left + (labels.length < 2 ? plotWidth / 2 : plotWidth * index / (labels.length - 1));
    const label = makeSvg("text", { x, y: height - 5, "text-anchor": index === 0 ? "start" : index === labels.length - 1 ? "end" : "middle", class: "chart-label" });
    label.textContent = dateLabel(labels[index]);
    svg.append(label);
  }
  host.append(svg);
}

function normalizeSeries(days, daily, batches) {
  const byDay = new Map();
  for (const row of daily) byDay.set(row.day, { ...row });
  for (const row of batches) byDay.set(row.day, { ...(byDay.get(row.day) || {}), ...row });
  const labels = [];
  const values = [];
  const start = new Date();
  start.setUTCHours(0, 0, 0, 0);
  start.setUTCDate(start.getUTCDate() - (days - 1));
  for (let i = 0; i < days; i++) {
    const date = new Date(start);
    date.setUTCDate(start.getUTCDate() + i);
    const key = date.toISOString().slice(0, 10);
    labels.push(key);
    values.push(byDay.get(key) || {});
  }
  return { labels, values };
}

function renderAnalytics(payload) {
  const { labels, values } = normalizeSeries(payload.days, payload.daily || [], payload.batches || []);
  const sum = (key) => values.reduce((total, row) => total + number(row[key]), 0);
  const monitor = payload.monitor || {};
  const monitorText = monitor.status === "active" ? "Active" : monitor.status === "stale" ? "Stale" : "No data";
  setMetric("#monitor-status", monitorText);
  $("#monitor-status").dataset.state = monitor.status === "active" ? "active" : monitor.status === "stale" ? "stale" : "none";
  $("#monitor-updated").textContent = monitor.last_watcher_scan ? "Last check " + new Date(monitor.last_watcher_scan).toLocaleString() : "No watcher check recorded";
  setMetric("#peak-count", fmt(sum("watcher_scans")));
  const predictions = payload.predictions || {};
  setMetric("#prediction-count", fmt(predictions.active));
  $("#next-release").textContent = predictions.next_release ? "Next " + predictions.next_release : "No upcoming prediction";
  setMetric("#extracted-count", fmt(sum("validated_records")));
  setMetric("#published-count", fmt(sum("published")));
  drawChart("#monitor-chart", labels, [
    { values: values.map((row) => number(row.watcher_scans)), area: true },
    { values: values.map((row) => number(row.releases)), secondary: true },
  ]);
  drawChart("#extraction-chart", labels, [{ values: values.map((row) => number(row.validated_records)), area: true }]);
  drawChart("#publication-chart", labels, [{ values: values.map((row) => number(row.published)), area: true }]);
}

function renderRecent(events) {
  const host = $("#activity-list");
  host.replaceChildren();
  for (const event of events.slice(0, 12)) {
    const card = document.createElement("article");
    card.className = "activity-card";
    const top = document.createElement("div");
    top.className = "activity-top";
    const title = document.createElement("h3");
    title.className = "activity-title";
    title.textContent = event.operation || event.event_type || "Activity";
    const status = document.createElement("span");
    status.className = "status status-" + (event.status || "warning");
    status.textContent = event.status || "unknown";
    top.append(title, status);
    const meta = document.createElement("p");
    meta.className = "activity-meta";
    meta.textContent = new Date(event.occurred_at || event.created_at).toLocaleString() + " · " + (event.component || "System");
    card.append(top, meta);
    host.append(card);
  }
  $("#load-message").textContent = events.length ? "" : "No recent activity recorded.";
}

async function loadDashboard() {
  const message = $("#load-message");
  message.textContent = "Loading analytics…";
  try {
    const [analyticsResponse, activityResponse] = await Promise.all([
      fetch("/api/analytics?days=" + state.days, { credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } }),
      fetch("/api/activity?limit=12", { credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } }),
    ]);
    if (analyticsResponse.status === 401 || activityResponse.status === 401) throw new Error("Owner session expired. Sign in again.");
    const analytics = await analyticsResponse.json();
    if (!analyticsResponse.ok) throw new Error(analytics.error || "Analytics unavailable.");
    renderAnalytics(analytics);
    if (activityResponse.ok) {
      const activity = await activityResponse.json();
      state.events = Array.isArray(activity.events) ? activity.events : [];
      renderRecent(state.events);
    } else {
      message.textContent = "Analytics loaded; recent activity unavailable.";
    }
  } catch (error) {
    message.textContent = error instanceof Error ? error.message : "Dashboard data unavailable.";
    message.dataset.kind = "error";
  }
}

document.querySelectorAll("[data-days]").forEach((button) => button.addEventListener("click", () => {
  state.days = Number(button.dataset.days);
  document.querySelectorAll("[data-days]").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
  loadDashboard();
}));

$("#sign-out-button").addEventListener("click", async () => {
  const button = $("#sign-out-button");
  button.disabled = true;
  try {
    const response = await fetch("/auth/logout", { method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": state.csrf } });
    if (response.ok) location.assign("/");
    else { $("#load-message").textContent = "Sign out failed. Reload and try again."; button.disabled = false; }
  } catch {
    $("#load-message").textContent = "Sign out failed. Check connection and retry.";
    button.disabled = false;
  }
});

initializeAuth().then((authenticated) => {
  if (authenticated) loadDashboard();
  else $("#load-message").textContent = "Sign in from the public website with your verified Owner account.";
});
