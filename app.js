/*
 * Public page configuration.
 * "search" is the normal homepage. Set to "preparing" only when the
 * examination preparation period is officially activated by the site owner.
 *
 * The sample progress below is illustrative only. Connect it to a verified
 * preparation-progress source before presenting it as live information.
 */
const SITE_MODE = "search";
const PREPARATION = {
  percentage: 75,
  examinationName: "PRC – LET Examination"
};

// Temporary UI catalog only. Replace with the verified published exam catalog.
const EXAMINATIONS = {
  PRC: ["Licensure Examination for Teachers (LET)", "Criminologists Licensure Examination", "Nurse Licensure Examination"],
  CSC: ["Career Service Professional Examination", "Career Service Subprofessional Examination"]
};
const YEARS = ["2026", "2025", "2024", "2023", "2022"];

const searchPage = document.getElementById("search-page");
const preparingPage = document.getElementById("preparing-page");
const progressArc = document.getElementById("progress-arc");
const progressValue = document.getElementById("progress-value");
const progressRing = document.querySelector(".progress-ring");
const examinationTitle = document.querySelector(".exam-title");
const searchForm = document.getElementById("search-form");
const examinationSelect = document.getElementById("examination");
const yearSelect = document.getElementById("exam-year");
const feedback = document.getElementById("search-feedback");
const menuButton = document.getElementById("menu-button");
const portalMenu = document.getElementById("portal-menu");

function showPage(page) {
  const showPreparing = page === "preparing";
  searchPage.hidden = showPreparing;
  preparingPage.hidden = !showPreparing;
  document.title = showPreparing ? "Results Preparation | Exam Results" : "Find Your Name | Exam Results";
}

function setProgress(value) {
  const percentage = Math.max(0, Math.min(100, Number(value) || 0));
  const circumference = 2 * Math.PI * 103;
  progressArc.style.strokeDasharray = String(circumference);
  progressArc.style.strokeDashoffset = String(circumference * (1 - percentage / 100));
  progressValue.textContent = percentage + "%";
  progressRing.setAttribute("aria-label", "Illustrative preparation progress: " + percentage + " percent");
}

function fillSelect(select, values, placeholder) {
  select.replaceChildren();
  const first = document.createElement("option");
  first.value = "";
  first.textContent = placeholder;
  first.disabled = true;
  first.selected = true;
  select.append(first);
  values.forEach(value => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.append(option);
  });
}

function setAuthority(authority) {
  document.querySelectorAll(".authority-tab").forEach(tab => {
    const active = tab.dataset.authority === authority;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  fillSelect(examinationSelect, EXAMINATIONS[authority], "Select exam");
  feedback.textContent = "";
}

document.querySelectorAll(".authority-tab").forEach(tab => {
  tab.addEventListener("click", () => setAuthority(tab.dataset.authority));
});

fillSelect(examinationSelect, EXAMINATIONS.PRC, "Select exam");
fillSelect(yearSelect, YEARS, "Year");
examinationTitle.textContent = PREPARATION.examinationName;
setProgress(PREPARATION.percentage);
showPage(SITE_MODE);

document.getElementById("open-search").addEventListener("click", () => showPage("search"));
document.querySelector(".preparing-brand").addEventListener("click", event => {
  event.preventDefault();
  showPage("search");
});
document.querySelector(".brand").addEventListener("click", event => {
  event.preventDefault();
  showPage("search");
});

menuButton.addEventListener("click", () => {
  const isExpanded = menuButton.getAttribute("aria-expanded") === "true";
  menuButton.setAttribute("aria-expanded", String(!isExpanded));
  portalMenu.hidden = isExpanded;
});
portalMenu.querySelector("a").addEventListener("click", () => {
  menuButton.setAttribute("aria-expanded", "false");
  portalMenu.hidden = true;
  document.getElementById("passer-name").focus();
});

searchForm.addEventListener("submit", event => {
  event.preventDefault();
  // No official results source is connected yet. Never imply that sample
  // options or this frontend are an authoritative examination database.
  feedback.textContent = "The official examination results database is not connected yet. No results have been searched.";
});
