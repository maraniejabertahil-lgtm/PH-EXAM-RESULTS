const $ = (id) => document.getElementById(id);
const columns = {
  events: ["created_at", "event_type", "status", "authority", "exam", "exam_year", "summary"],
  batches: ["updated_at", "authority", "exam", "exam_year", "status", "greenlight_score", "announced_count", "extracted_count", "summary"],
  predictions: ["created_at", "authority", "exam", "exam_year", "predicted_release_date", "method", "confidence", "evidence_count"],
};
function cellText(value) { return value === null || value === undefined || value === "" ? "—" : String(value); }
function renderTable(target, rows, keys) {
  const host = $(target); host.replaceChildren();
  if (!Array.isArray(rows) || rows.length === 0) {
    const empty = document.createElement("p"); empty.className = "owner-empty"; empty.textContent = "No activity has been recorded yet."; host.append(empty); return;
  }
  const table = document.createElement("table"); table.className = "owner-table";
  const head = document.createElement("thead"), headRow = document.createElement("tr");
  for (const key of keys) { const th = document.createElement("th"); th.scope = "col"; th.textContent = key.replaceAll("_", " "); headRow.append(th); }
  head.append(headRow); table.append(head);
  const body = document.createElement("tbody");
  for (const row of rows) { const tr = document.createElement("tr"); for (const key of keys) { const td = document.createElement("td"); td.textContent = cellText(row?.[key]); tr.append(td); } body.append(tr); }
  table.append(body); host.append(table);
}
async function refresh() {
  const error = $("owner-error"); error.hidden = true;
  $("updated-at").textContent = "Loading private activity…";
  $("refresh-button").disabled = true;
  try {
    const response = await fetch("/api/activity", { credentials: "same-origin", cache: "no-store", headers: { accept: "application/json" } });
    if (response.status === 401 || response.status === 403) throw new Error("Your Cloudflare Access session is not authorized for this dashboard.");
    if (!response.ok) throw new Error("Private activity data is temporarily unavailable.");
    const data = await response.json();
    for (const [key, keys] of Object.entries(columns)) renderTable(key, data[key], keys);
    $("updated-at").textContent = "Updated " + new Date(data.generated_at).toLocaleString();
  } catch (cause) {
    error.textContent = cause instanceof Error ? cause.message : "Private activity data is temporarily unavailable.";
    error.hidden = false; $("updated-at").textContent = "Dashboard not refreshed";
  } finally { $("refresh-button").disabled = false; }
}
$("refresh-button").addEventListener("click", refresh);
refresh();
