import {
  getExaminations,
  getYears,
  loadManifest,
  loadSearchDataset,
  loadSiteStatus
} from "./loader.js";

const searchPage = document.getElementById("search-page");
const preparingPage = document.getElementById("preparing-page");
const progressArc = document.getElementById("progress-arc");
const progressValue = document.getElementById("progress-value");
const progressRing = document.querySelector(".progress-ring");
const examinationTitle = document.querySelector(".exam-title");
const preparingStatus = document.querySelector(".preparing-status");
const preparationNote = document.getElementById("preparation-note");
const searchForm = document.getElementById("search-form");
const examinationSelect = document.getElementById("examination");
const yearSelect = document.getElementById("exam-year");
const passerNameInput = document.getElementById("passer-name");
const feedback = document.getElementById("search-feedback");
const resultsContainer = document.getElementById("search-results");
const menuButton = document.getElementById("menu-button");
const portalMenu = document.getElementById("portal-menu");

let manifest = null;
let activeAuthority = "PRC";
let workerDatasetKey = null;
let nextRequestId = 1;
const pendingSearches = new Map();
const pendingWorkerLoads = new Map();
const WORKER_RESPONSE_TIMEOUT_MS = 30000;
let searchWorker = null;

function showPage(page) {
  const showPreparing = page === "preparing";
  searchPage.hidden = showPreparing;
  preparingPage.hidden = !showPreparing;
  document.title = showPreparing
    ? "Results Preparation | Exam Results"
    : "Find Your Name | Exam Results";
}

function setProgress(value) {
  const percentage = Math.max(0, Math.min(100, Number(value) || 0));
  const circumference = 2 * Math.PI * 103;
  progressArc.style.strokeDasharray = String(circumference);
  progressArc.style.strokeDashoffset = String(circumference * (1 - percentage / 100));
  progressValue.textContent = percentage + "%";
  progressRing.setAttribute("aria-label", "Verified preparation progress: " + percentage + " percent");
}

function fillSelect(select, values, placeholder, emptyMessage) {
  select.replaceChildren();
  const first = document.createElement("option");
  first.value = "";
  first.textContent = values.length ? placeholder : emptyMessage;
  first.disabled = true;
  first.selected = true;
  select.append(first);
  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.append(option);
  }
  select.disabled = values.length === 0;
}

function refreshExaminations() {
  const examinations = manifest ? getExaminations(manifest, activeAuthority) : [];
  fillSelect(examinationSelect, examinations, "Select exam", "No published examinations yet");
  refreshYears();
}

function refreshYears() {
  const years = manifest && examinationSelect.value
    ? getYears(manifest, activeAuthority, examinationSelect.value)
    : [];
  fillSelect(yearSelect, years, "Year", "Select an examination first");
  resultsContainer.replaceChildren();
}

function setAuthority(authority) {
  activeAuthority = authority;
  document.querySelectorAll(".authority-tab").forEach(tab => {
    const active = tab.dataset.authority === authority;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  refreshExaminations();
  feedback.textContent = "";
}

function renderResults(rows, columns, totalMatches = rows.length) {
  resultsContainer.replaceChildren();
  const nameIndex = columns.indexOf("name");
  const ratingIndex = columns.indexOf("rating");
  const regionIndex = columns.indexOf("region");

  const summary = document.createElement("p");
  summary.className = "results-summary";
  summary.textContent = totalMatches === 0
    ? "No matching names found in the published dataset."
    : totalMatches > rows.length
      ? "Showing the first " + rows.length + " of " + totalMatches + " matching records. Refine your search to narrow the list."
      : totalMatches + (totalMatches === 1 ? " matching record" : " matching records");
  resultsContainer.append(summary);

  for (const row of rows) {
    const item = document.createElement("article");
    item.className = "result-item";
    const name = document.createElement("h2");
    name.className = "result-name";
    name.textContent = String(row[nameIndex] ?? "");
    item.append(name);

    const details = [];
    if (ratingIndex >= 0 && row[ratingIndex] !== null && row[ratingIndex] !== "") {
      details.push("Rating: " + row[ratingIndex]);
    }
    if (regionIndex >= 0 && row[regionIndex]) {
      details.push("Region: " + row[regionIndex]);
    }
    if (details.length) {
      const metadata = document.createElement("p");
      metadata.className = "result-metadata";
      metadata.textContent = details.join(" · ");
      item.append(metadata);
    }
    resultsContainer.append(item);
  }
}

function ensureWorkerDataset(dataset) {
  if (workerDatasetKey === dataset.datasetKey) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => failSearchWorker(searchWorker, new Error("The search engine did not respond. Please try your search again.")), WORKER_RESPONSE_TIMEOUT_MS);
    pendingWorkerLoads.set(dataset.datasetKey, { resolve, reject, timer });
    try {
      ensureSearchWorker().postMessage({
        type: "load",
        datasetKey: dataset.datasetKey,
        columns: dataset.columns,
        rows: dataset.rows
      });
    } catch (error) {
      clearTimeout(timer);
      pendingWorkerLoads.delete(dataset.datasetKey);
      reject(error);
    }
  });
}

function runWorkerSearch(query) {
  const requestId = nextRequestId++;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => failSearchWorker(searchWorker, new Error("The search engine did not respond. Please try your search again.")), WORKER_RESPONSE_TIMEOUT_MS);
    pendingSearches.set(requestId, { resolve, reject, timer });
    try {
      ensureSearchWorker().postMessage({ type: "search", requestId, query });
    } catch (error) {
      clearTimeout(timer);
      pendingSearches.delete(requestId);
      reject(error);
    }
  });
}

function rejectPendingWorkerRequests(error) {
  workerDatasetKey = null;
  for (const pending of pendingWorkerLoads.values()) {
    clearTimeout(pending.timer);
    pending.reject(error);
  }
  for (const pending of pendingSearches.values()) {
    clearTimeout(pending.timer);
    pending.reject(error);
  }
  pendingWorkerLoads.clear();
  pendingSearches.clear();
}

function handleWorkerMessage(event) {
  const message = event.data || {};
  if (message.type === "loaded") {
    const pending = pendingWorkerLoads.get(message.datasetKey);
    if (pending) {
      pendingWorkerLoads.delete(message.datasetKey);
      clearTimeout(pending.timer);
      if (message.error) pending.reject(new Error(message.error));
      else {
        workerDatasetKey = message.datasetKey;
        pending.resolve();
      }
    }
    return;
  }
  if (message.type === "results") {
    const pending = pendingSearches.get(message.requestId);
    if (pending) {
      pendingSearches.delete(message.requestId);
      clearTimeout(pending.timer);
      if (message.error) pending.reject(new Error(message.error));
      else pending.resolve({ matches: message.matches || [], totalMatches: message.totalMatches || 0 });
    }
  }
}

function failSearchWorker(worker, error) {
  if (worker && searchWorker !== worker) return;
  if (worker) worker.terminate();
  searchWorker = null;
  rejectPendingWorkerRequests(error);
}

function ensureSearchWorker() {
  if (searchWorker) return searchWorker;
  const worker = new Worker(new URL("./search.js", import.meta.url), { type: "module" });
  worker.addEventListener("message", handleWorkerMessage);
  const handleFailure = () => failSearchWorker(
    worker,
    new Error("The search engine stopped unexpectedly. Please submit your search again.")
  );
  worker.addEventListener("error", handleFailure);
  worker.addEventListener("messageerror", handleFailure);
  searchWorker = worker;
  return worker;
}

document.querySelectorAll(".authority-tab").forEach(tab => {
  tab.addEventListener("click", () => setAuthority(tab.dataset.authority));
});
examinationSelect.addEventListener("change", refreshYears);

menuButton.addEventListener("click", () => {
  const expanded = menuButton.getAttribute("aria-expanded") === "true";
  menuButton.setAttribute("aria-expanded", String(!expanded));
  portalMenu.hidden = expanded;
});
portalMenu.querySelector("a").addEventListener("click", () => {
  menuButton.setAttribute("aria-expanded", "false");
  portalMenu.hidden = true;
  document.getElementById("passer-name").focus();
});

document.getElementById("open-search").addEventListener("click", () => showPage("search"));
document.querySelector(".preparing-brand").addEventListener("click", event => {
  event.preventDefault();
  showPage("search");
});
document.querySelector(".brand").addEventListener("click", event => {
  event.preventDefault();
  showPage("search");
});

searchForm.addEventListener("submit", async event => {
  event.preventDefault();
  feedback.textContent = "";
  resultsContainer.replaceChildren();

  const query = passerNameInput.value.trim();
  const authority = activeAuthority;
  const examination = examinationSelect.value;
  const year = yearSelect.value;
  if (!manifest || !query || !examination || !year) {
    feedback.textContent = "Select an authority, examination, year, and enter a name.";
    return;
  }

  const submitButton = searchForm.querySelector(".submit-button");
  const searchControls = [
    ...document.querySelectorAll(".authority-tab"),
    examinationSelect,
    yearSelect,
    passerNameInput
  ];
  const previousDisabledStates = searchControls.map(control => control.disabled);
  searchControls.forEach(control => { control.disabled = true; });
  submitButton.disabled = true;
  submitButton.setAttribute("aria-busy", "true");
  feedback.textContent = "Loading the published examination dataset…";

  try {
    // Revalidate the tiny static manifest on each search so a page left open
    // across a publication sees the latest immutable shard URLs.
    try {
      const latestManifest = await loadManifest();
      if (latestManifest.last_updated !== manifest.last_updated) {
        manifest = latestManifest;
      }
    } catch {
      // Keep the last known-good manifest if the static catalogue is temporarily unavailable.
    }

    let dataset;
    try {
      dataset = await loadSearchDataset(
        manifest, authority, examination, year, query
      );
    } catch (firstError) {
      // A page left open across a publication may still hold the previous
      // manifest. Refresh it once if the published manifest has changed.
      const refreshedManifest = await loadManifest();
      if (refreshedManifest.last_updated === manifest.last_updated) {
        throw firstError;
      }
      manifest = refreshedManifest;
      feedback.textContent = "The catalogue was updated. Refreshing the selected results…";
      dataset = await loadSearchDataset(
        manifest, authority, examination, year, query
      );
    }
    await ensureWorkerDataset(dataset);
    const searchResult = await runWorkerSearch(query);
    feedback.textContent = "Source: published examination dataset · " +
      authority + " · " + examination + " · " + year;
    renderResults(searchResult.matches, dataset.columns, searchResult.totalMatches);
  } catch (error) {
    feedback.textContent = error instanceof Error
      ? error.message
      : "The search could not be completed. Please try again.";
  } finally {
    submitButton.disabled = false;
    submitButton.removeAttribute("aria-busy");
    searchControls.forEach((control, index) => {
      control.disabled = previousDisabledStates[index];
    });
  }
});

async function initialize() {
  try {
    const [loadedManifest, status] = await Promise.all([
      loadManifest(),
      loadSiteStatus()
    ]);
    manifest = loadedManifest;
    setAuthority("PRC");

    const preparation = status.preparation;
    const validPreparation = status.mode === "preparing"
      && preparation
      && Number.isFinite(Number(preparation.percentage))
      && typeof preparation.examination_name === "string"
      && preparation.examination_name.trim();

    if (validPreparation) {
      setProgress(preparation.percentage);
      examinationTitle.textContent = preparation.examination_name;
      preparingStatus.textContent = preparation.status || "Preparing examination results…";
      preparationNote.textContent = "Progress reflects verified preparation workflow stages.";
      showPage("preparing");
    } else {
      showPage("search");
    }
  } catch {
    manifest = { authorities: {} };
    setAuthority("PRC");
    showPage("search");
    feedback.textContent = "The examination catalogue is temporarily unavailable. Please try again later.";
  }
}

initialize();
