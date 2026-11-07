const elements = {
  total: document.querySelector("#total-count"),
  failed: document.querySelector("#failed-count"),
  blocked: document.querySelector("#blocked-count"),
  running: document.querySelector("#running-count"),
  updated: document.querySelector("#last-updated"),
  message: document.querySelector("#load-message"),
  list: document.querySelector("#activity-list"),
  status: document.querySelector("#status-filter"),
  component: document.querySelector("#component-filter"),
  refresh: document.querySelector("#refresh-button"),
  signIn: document.querySelector("#sign-in-link"),
  signOut: document.querySelector("#sign-out-button"),
};

function safeText(value, fallback = "—") {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? safeText(value) : date.toLocaleString();
}

function addDetail(dl, label, value) {
  const term = document.createElement("dt");
  term.textContent = label;
  const description = document.createElement("dd");
  description.textContent = value;
  dl.append(term, description);
}

function renderEvents(events) {
  elements.list.replaceChildren();
  elements.total.textContent = String(events.length);
  elements.failed.textContent = String(events.filter((item) => item.status === "failed").length);
  elements.blocked.textContent = String(events.filter((item) => item.status === "blocked").length);
  elements.running.textContent = String(events.filter((item) => item.status === "running").length);
  const components = [...new Set(events.map((item) => item.component).filter(Boolean))].sort();
  const selected = elements.component.value;
  elements.component.replaceChildren(new Option("All components", ""));
  for (const component of components) elements.component.add(new Option(component, component));
  if (components.includes(selected)) elements.component.value = selected;

  const groups = new Map();
  for (const event of events) {
    const key = safeText(event.execution_id, "unlinked-events");
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(event);
  }
  for (const [executionId, items] of groups) {
    const group = document.createElement("section");
    group.className = "execution-group";
    const heading = document.createElement("div");
    heading.className = "execution-heading";
    const identity = document.createElement("div");
    const title = document.createElement("h3");
    title.textContent = "Execution " + executionId;
    const meta = document.createElement("p");
    meta.textContent = items.length + " activity event(s) · latest " + formatDate(items[0].occurred_at);
    identity.append(title, meta);
    const groupStatus = items.some((item) => item.status === "failed") ? "failed"
      : items.some((item) => item.status === "blocked") ? "blocked"
        : items[0]?.status === "running" ? "running"
          : items.some((item) => item.status === "warning") ? "warning" : "success";
    const badge = document.createElement("span");
    badge.className = "status status-" + groupStatus;
    badge.textContent = groupStatus;
    heading.append(identity, badge);
    group.append(heading);

    for (const event of items) {
      const card = document.createElement("article");
      card.className = "activity-card";
      const top = document.createElement("div");
      top.className = "activity-top";
      const left = document.createElement("div");
      const eventTitle = document.createElement("h4");
      eventTitle.className = "activity-title";
      eventTitle.textContent = safeText(event.operation, "Activity");
      const eventMeta = document.createElement("p");
      eventMeta.className = "activity-meta";
      const duration = event.duration_ms === null || event.duration_ms === undefined ? "—" : String(event.duration_ms) + " ms";
      eventMeta.textContent = formatDate(event.occurred_at) + " · " + safeText(event.component) + " · " + duration;
      left.append(eventTitle, eventMeta);
      const eventBadge = document.createElement("span");
      eventBadge.className = "status status-" + event.status;
      eventBadge.textContent = safeText(event.status, "unknown");
      top.append(left, eventBadge);
      card.append(top);

      const details = document.createElement("details");
      details.className = "activity-details";
      const summary = document.createElement("summary");
      summary.textContent = "Inspect activity details";
      const dl = document.createElement("dl");
      dl.className = "detail-grid";
      addDetail(dl, "Event ID", safeText(event.event_id));
      addDetail(dl, "Operation", safeText(event.operation));
      addDetail(dl, "Source", safeText(event.source));
      addDetail(dl, "Message", safeText(event.message));
      addDetail(dl, "Error code", safeText(event.error_code));
      const metadata = event.metadata && typeof event.metadata === "object" ? event.metadata : {};
      addDetail(dl, "Metadata", JSON.stringify(metadata, null, 2));
      details.append(summary, dl);
      if (event.error_message) {
        const error = document.createElement("pre");
        error.className = "error-detail";
        error.textContent = event.error_message;
        details.append(error);
      }
      const runUrl = typeof metadata.run_url === "string" &&
        /^https:\/\/github\.com\/maraniejabertahil-lgtm\/PH-EXAM-RESULTS\/actions\/runs\/\d+$/.test(metadata.run_url)
        ? metadata.run_url
        : (metadata.run_id ? "https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/actions/runs/" +
          encodeURIComponent(String(metadata.run_id)) : "");
      if (runUrl) {
        const link = document.createElement("a");
        link.href = runUrl;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = "Open GitHub workflow run";
        details.append(link);
      }
      card.append(details);
      group.append(card);
    }
    elements.list.append(group);
  }
  elements.updated.textContent = "Loaded " + events.length + " latest events · " + new Date().toLocaleTimeString();
}

let csrfToken = "";
async function initializeAuth() {
  try {
    const response = await fetch("/auth/session", { credentials: "same-origin", cache: "no-store" });
    const session = await response.json();
    if (session.authenticated) { csrfToken = session.csrf; elements.signIn.hidden = true; elements.signOut.hidden = false; return true; }
  } catch { /* remain signed out */ }
  elements.signIn.hidden = false; elements.signOut.hidden = true; return false;
}

async function loadEvents() {
  elements.message.textContent = "Loading private activity history…";
  elements.message.dataset.kind = "info";
  elements.refresh.disabled = true;
  try {
    const params = new URLSearchParams({ limit: "100" });
    if (elements.status.value) params.set("status", elements.status.value);
    if (elements.component.value) params.set("component", elements.component.value);
    const response = await fetch("/api/activity?" + params, {
      credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" },
    });
    if (response.status === 404 || response.status === 401) {
      throw new Error("Owner access was not verified. Sign in with the authorized owner account.");
    }
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      throw new Error("Your private access session may have expired. Sign in again, then refresh this dashboard.");
    }
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Activity history could not be loaded.");
    if (!Array.isArray(payload.events)) throw new Error("Activity history response is invalid.");
    renderEvents(payload.events);
    elements.message.textContent = payload.events.length ? "" : "No activity events have been recorded yet.";
  } catch (error) {
    elements.message.textContent = error instanceof Error ? error.message : "Activity history could not be loaded.";
    elements.message.dataset.kind = "error";
    elements.list.replaceChildren();
  } finally {
    elements.refresh.disabled = false;
  }
}

elements.signOut.addEventListener("click", async () => {
  elements.signOut.disabled = true;
  try { const response = await fetch("/auth/logout", { method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": csrfToken } });
    if (response.ok) location.assign("/"); else elements.message.textContent = "Sign out failed. Reload and try again.";
  } finally { elements.signOut.disabled = false; }
});
elements.refresh.addEventListener("click", loadEvents);
elements.status.addEventListener("change", loadEvents);
elements.component.addEventListener("change", loadEvents);
initializeAuth().then(authenticated => {
  if (authenticated) loadEvents();
  else { elements.message.textContent = "Sign in from the public PH Exam Results page using your verified Firebase Owner account and authorized GitHub account."; elements.list.replaceChildren(); }
});
