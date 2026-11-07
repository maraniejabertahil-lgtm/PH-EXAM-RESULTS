import { loadDataset } from "./storage.mjs";
import { createDiagnosticReference, safeErrorMessage } from "./error-messages.mjs";

const CATALOG_URL = "/data/catalog.json";
const STATUS_URL = "/status.json";
let siteStatus = null;
const MAX_RESULTS = 100;
const elements = {
  searchView: document.querySelector("#search-view"),
  preparingView: document.querySelector("#preparing-view"),
  authority: document.querySelector("#authority"),
  exam: document.querySelector("#exam"),
  year: document.querySelector("#year"),
  name: document.querySelector("#name-query"),
  form: document.querySelector("#search-form"),
  button: document.querySelector("#search-button"),
  message: document.querySelector("#status-message"),
  resultsSection: document.querySelector("#results-section"),
  resultCount: document.querySelector("#result-count"),
  resultNote: document.querySelector("#result-note"),
  resultsList: document.querySelector("#results-list"),
  errorActions: document.querySelector("#error-actions"),
  errorReference: document.querySelector("#error-reference"),
  retryButton: document.querySelector("#retry-button"),
};

let catalog = [];
let selectedDataset = null;
let worker = null;
let requestId = 0;
let pendingSearch = null;

function setMessage(message, kind = "info") {
  elements.message.textContent = message;
  elements.message.dataset.kind = kind;
  if (kind !== "error") elements.errorActions.hidden = true;
}

function showSafeError(context, error) {
  const diagnosticReference = createDiagnosticReference();
  elements.message.textContent = safeErrorMessage(context);
  elements.message.dataset.kind = "error";
  elements.errorReference.textContent = `Reference: ${diagnosticReference}`;
  elements.errorActions.hidden = false;
  // Keep diagnostics local. Do not log the raw error, stack, URL, or search input.
  console.error("[PH Exam Results] Browser operation failed.", {
    context,
    diagnosticReference,
    errorType: error instanceof Error ? error.name : "UnknownError",
  });
}

function resetSelect(select, placeholder) {
  select.replaceChildren(new Option(placeholder, ""));
  select.disabled = true;
}

function showPreparingMode() {
  elements.searchView.hidden = true;
  elements.preparingView.hidden = false;
}

async function loadStatus() {
  const response = await fetch(STATUS_URL, { cache: "no-store", credentials: "same-origin" });
  if (!response.ok) throw new Error(`Site status could not be loaded (HTTP ${response.status}).`);
  const status = await response.json();
  siteStatus = status;
  if (!["searching", "preparing"].includes(status.mode)) throw new Error("Site status has an invalid mode.");
  if (status.mode === "preparing") showPreparingMode();
}

async function loadCatalog() {
  const response = await fetch(CATALOG_URL, { credentials: "same-origin" });
  if (!response.ok) throw new Error(`Published dataset catalog could not be loaded (HTTP ${response.status}).`);
  const value = await response.json();
  if (!Array.isArray(value.datasets) || value.datasets.some((item) =>
    !item || typeof item.authority !== "string" || typeof item.exam !== "string"
    || !Number.isInteger(item.year) || typeof item.manifest !== "string"
  )) {
    throw new Error("Published dataset catalog has an invalid format.");
  }
  catalog = value.datasets;
  const authorities = [...new Set(catalog.map((item) => item.authority))].sort();
  for (const authority of authorities) elements.authority.add(new Option(authority, authority));
  if (authorities.length === 1) {
    elements.authority.value = authorities[0];
    updateExams();
  }
}

function updateExams() {
  resetSelect(elements.exam, "Choose examination");
  resetSelect(elements.year, "Choose year");
  elements.button.disabled = true;
  const exams = [...new Set(catalog
    .filter((item) => item.authority === elements.authority.value)
    .map((item) => item.exam))].sort();
  for (const exam of exams) elements.exam.add(new Option(exam, exam));
  elements.exam.disabled = exams.length === 0;
}

function updateYears() {
  resetSelect(elements.year, "Choose year");
  elements.button.disabled = true;
  const years = [...new Set(catalog
    .filter((item) => item.authority === elements.authority.value && item.exam === elements.exam.value)
    .map((item) => item.year))].sort((a, b) => b - a);
  for (const year of years) elements.year.add(new Option(String(year), String(year)));
  elements.year.disabled = years.length === 0;
}

function getSelectedEntry() {
  return catalog.find((item) => item.authority === elements.authority.value
    && item.exam === elements.exam.value
    && item.year === Number(elements.year.value));
}

async function ensureDataset() {
  const entry = getSelectedEntry();
  if (!entry) throw new Error("Choose an available authority, examination, and year.");
  if (selectedDataset?.entry === entry) return selectedDataset;
  setMessage("Loading and verifying the published dataset…");
  elements.button.disabled = true;
  selectedDataset = { entry, ...(await loadDataset(entry)) };
  elements.button.disabled = false;
  setMessage(`${selectedDataset.manifest.record_count.toLocaleString()} verified records ready.`, "success");
  return selectedDataset;
}

function createWorker() {
  if (!worker) {
    worker = new Worker("/assets/js/search-worker.mjs", { type: "module" });
    worker.onmessage = ({ data }) => {
      if (!pendingSearch || data.requestId !== pendingSearch.requestId) return;
      const { resolve, reject } = pendingSearch;
      pendingSearch = null;
      if (data.error) reject(new Error(data.error));
      else resolve(data);
    };
    worker.onerror = () => {
      pendingSearch?.reject(new Error("Search worker failed. Reload the page and try again."));
      pendingSearch = null;
    };
  }
  return worker;
}

function search(query, rows) {
  if (pendingSearch) pendingSearch.reject(new Error("Search was replaced by a newer request."));
  const id = ++requestId;
  return new Promise((resolve, reject) => {
    pendingSearch = { requestId: id, resolve, reject };
    createWorker().postMessage({ requestId: id, rows, query, limit: MAX_RESULTS });
  });
}

function renderResults(result) {
  elements.resultsList.replaceChildren();
  elements.resultCount.textContent = `${result.total.toLocaleString()} found`;
  elements.resultNote.textContent = result.truncated
    ? `Showing the first ${MAX_RESULTS} matches. Refine your search to see fewer results.`
    : result.total === 0 ? "No matching names were found. Check the spelling and try again." : "";
  for (const record of result.results) {
    const item = document.createElement("li");
    item.className = "result-card";
    const details = document.createElement("div");
    const name = document.createElement("p");
    name.className = "result-name";
    name.textContent = record.name;
    details.append(name);
    if (record.rating !== null || record.region !== null) {
      const extra = document.createElement("p");
      extra.className = "result-detail";
      extra.textContent = [
        record.rating === null ? "" : `Rating: ${record.rating}`,
        record.region === null ? "" : `Region: ${record.region}`,
      ].filter(Boolean).join(" · ");
      details.append(extra);
    }
    const sequence = document.createElement("span");
    sequence.className = "sequence";
    sequence.textContent = `Sequence ${record.sequence_number}`;
    item.append(details, sequence);
    elements.resultsList.append(item);
  }
  elements.resultsSection.hidden = false;
}

elements.authority.addEventListener("change", updateExams);
elements.exam.addEventListener("change", updateYears);
elements.year.addEventListener("change", () => {
  elements.button.disabled = !getSelectedEntry();
  selectedDataset = null;
});

elements.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  elements.button.disabled = true;
  elements.resultsSection.hidden = true;
  let errorContext = "search";
  try {
    const query = elements.name.value.trim();
    if (query.length < 2) throw new Error("Enter at least two characters to search.");
    errorContext = "dataset";
    const dataset = await ensureDataset();
    errorContext = "search";
    setMessage("Searching this device…");
    const result = await search(query, dataset.rows);
    renderResults(result);
    setMessage("Search complete. No search query was sent to a server.", "success");
  } catch (error) {
    showSafeError(errorContext, error);
  } finally {
    elements.button.disabled = !getSelectedEntry();
  }
});

try {
  await loadStatus();
  if (!elements.searchView.hidden) await loadCatalog();
} catch (error) {
  showSafeError("startup", error);
}

elements.retryButton.addEventListener("click", () => window.location.reload());

window.addEventListener("error", (event) => {
  showSafeError("unexpected", event.error);
});

window.addEventListener("unhandledrejection", (event) => {
  showSafeError("unexpected", event.reason);
});


// Owner authentication is isolated from the public examination search workflow.
// Firebase configuration is public web-app configuration; no Admin credential is used here.
const OWNER_DASHBOARD_URL = "https://ph-exam-results-owner.pages.dev";
const OWNER_FIREBASE_CONFIG = {
  apiKey: "AIzaSyDN3QQyk6ueanwjLVtU4YcEGBxgDaF4U0w",
  authDomain: "ph-exam-results-dd94a.firebaseapp.com",
  projectId: "ph-exam-results-dd94a",
  storageBucket: "ph-exam-results-dd94a.firebasestorage.app",
  messagingSenderId: "722578122359",
  appId: "1:722578122359:web:8180388de4bbee11d40872",
};
let ownerFirebaseAuthPromise;
const ownerLogin = {
  dialog: document.querySelector("#owner-login-dialog"),
  open: document.querySelector("#owner-login-open"),
  close: document.querySelector("#owner-login-close"),
  form: document.querySelector("#owner-login-form"),
  email: document.querySelector("#owner-email"),
  password: document.querySelector("#owner-password"),
  submit: document.querySelector("#owner-login-submit"),
  message: document.querySelector("#owner-login-message"),
};
function showOwnerLogin() {
  if (ownerLogin.dialog && !ownerLogin.dialog.open) ownerLogin.dialog.showModal();
}
ownerLogin.open?.addEventListener("click", showOwnerLogin);
ownerLogin.close?.addEventListener("click", () => ownerLogin.dialog.close());
ownerLogin.dialog?.addEventListener("click", (event) => {
  if (event.target === ownerLogin.dialog) ownerLogin.dialog.close();
});
const ownerQuery = new URLSearchParams(location.search);
const ownerLoginEnabled = siteStatus?.owner_login_enabled === true;
if (ownerLogin.open) ownerLogin.open.hidden = !ownerLoginEnabled;
if (ownerQuery.get("owner") === "login" && ownerLoginEnabled) showOwnerLogin();
if (ownerQuery.get("owner_reason")) {
  const reason = ownerQuery.get("owner_reason");
  if (reason === "github_denied") ownerLogin.message.textContent = "GitHub Owner verification failed. / فشل التحقق من حساب المالك في GitHub.";
  else if (reason === "github_failed") ownerLogin.message.textContent = "GitHub sign-in could not be completed. Please try again. / تعذّر إكمال تسجيل الدخول عبر GitHub. حاول مرة أخرى.";
  else if (reason === "firebase_required") ownerLogin.message.textContent = "Please verify your Firebase Owner account first. / يرجى التحقق من حساب Firebase الخاص بالمالك أولاً.";
}
ownerLogin.form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  ownerLogin.submit.disabled = true;
  ownerLogin.message.textContent = "Verifying Firebase Owner account… / جارٍ التحقق من حساب مالك Firebase…";
  let authContext = null;
  try {
    if (!ownerFirebaseAuthPromise) {
      ownerFirebaseAuthPromise = Promise.all([
        import("https://www.gstatic.com/firebasejs/11.10.0/firebase-app.js"),
        import("https://www.gstatic.com/firebasejs/11.10.0/firebase-auth.js"),
      ]).then(([firebaseApp, firebaseAuth]) => {
        const app = firebaseApp.getApps().find(item => item.name === "ph-exam-results-owner-login")
          || firebaseApp.initializeApp(OWNER_FIREBASE_CONFIG, "ph-exam-results-owner-login");
        return {
          auth: firebaseAuth.initializeAuth(app, { persistence: firebaseAuth.inMemoryPersistence }),
          ...firebaseAuth,
        };
      });
    }
    authContext = await ownerFirebaseAuthPromise;
    const credential = await authContext.signInWithEmailAndPassword(
      authContext.auth, ownerLogin.email.value.trim(), ownerLogin.password.value
    );
    const idToken = await authContext.getIdToken(credential.user, true);
    const response = await fetch(OWNER_DASHBOARD_URL + "/auth/firebase", {
      method: "POST",
      mode: "cors",
      credentials: "omit",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idToken }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok || result.authenticated !== true || typeof result.proof !== "string") {
      throw new Error(result.error || "Firebase Owner access was denied. / تم رفض صلاحية مالك Firebase.");
    }
    await authContext.signOut(authContext.auth);
    ownerLogin.password.value = "";
    ownerLogin.message.textContent = "Firebase Owner verified. Continue with GitHub verification… / تم التحقق من مالك Firebase. أكمل التحقق عبر GitHub…";
    location.assign(OWNER_DASHBOARD_URL + "/continue.html#proof=" + encodeURIComponent(result.proof));
  } catch (error) {
    if (authContext?.auth) {
      try { await authContext.signOut(authContext.auth); } catch { /* clear in-memory auth best-effort */ }
    }
    ownerLogin.password.value = "";
    const raw = error instanceof Error ? error.message : "";
    ownerLogin.message.textContent = raw.includes("auth/")
      ? "Sign-in failed. Check your email and password. / تعذّر تسجيل الدخول. تحقق من البريد الإلكتروني وكلمة المرور."
      : (raw || "Owner sign-in failed. / فشل تسجيل دخول المالك.");
    ownerLogin.submit.disabled = false;
  }
});
