import { validateReviewBundle } from "./review-logic.mjs";

const MAX_BUNDLE_BYTES = 50 * 1024 * 1024;
const MAX_RENDERED_RECORDS = 100;
const elements = {
  file: document.querySelector("#bundle-file"),
  status: document.querySelector("#review-status"),
  workspace: document.querySelector("#review-workspace"),
  title: document.querySelector("#candidate-title"),
  summary: document.querySelector("#candidate-summary"),
  links: document.querySelector("#source-links"),
  query: document.querySelector("#record-query"),
  recordCount: document.querySelector("#record-count"),
  records: document.querySelector("#review-records"),
  evidenceCount: document.querySelector("#evidence-count"),
  evidence: document.querySelector("#review-evidence"),
  form: document.querySelector("#review-form"),
  reviewer: document.querySelector("#reviewer-name"),
  evidenceReviewed: document.querySelector("#evidence-reviewed"),
  recordsReviewed: document.querySelector("#records-reviewed"),
  decision: document.querySelector("#review-decision"),
  notes: document.querySelector("#review-notes"),
};
let bundle = null;

function setStatus(message, kind = "info") {
  elements.status.textContent = message;
  elements.status.dataset.kind = kind;
}

function renderSources() {
  elements.links.replaceChildren();
  for (const [label, url] of [
    ["Official announcement", bundle.official_article_url],
    ["Official content", bundle.official_content_url],
    ["Public preview", bundle.public_preview_url],
  ]) {
    const link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = label;
    elements.links.append(link);
  }
}

function renderRecords() {
  const query = elements.query.value.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase().trim();
  const matches = bundle.records.filter((record) => {
    const name = record.name.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
    return name.includes(query) || record.sequence_number.includes(query);
  });
  elements.records.replaceChildren();
  for (const record of matches.slice(0, MAX_RENDERED_RECORDS)) {
    const item = document.createElement("li");
    item.className = "result-card";
    const name = document.createElement("span");
    name.className = "result-name";
    name.textContent = record.name;
    const sequence = document.createElement("span");
    sequence.className = "sequence";
    sequence.textContent = `Sequence ${record.sequence_number}`;
    item.append(name, sequence);
    elements.records.append(item);
  }
  elements.recordCount.textContent = `${matches.length.toLocaleString()} matching records; showing at most ${MAX_RENDERED_RECORDS}. Search by name or sequence.`;
}

function renderEvidence() {
  elements.evidence.replaceChildren();
  for (const item of bundle.evidence) {
    const row = document.createElement("li");
    const heading = document.createElement("p");
    const sequences = item.sequence_numbers ?? [item.sequence_number];
    const page = Number.isInteger(item.viewer_page) ? `Page ${item.viewer_page} · ` : "";
    heading.textContent = `${page}Sequences ${sequences[0]}–${sequences.at(-1)}:\n${item.expected_visible_text}`;
    const image = document.createElement("img");
    image.src = item.image_data;
    image.alt = `Captured public-preview evidence for viewer page ${item.viewer_page ?? "with"} sequence ${sequences[0]}`;
    image.loading = "lazy";
    row.append(heading, image);
    elements.evidence.append(row);
  }
  elements.evidenceCount.textContent = `${bundle.evidence.length.toLocaleString()} hash-verified screenshot(s), covering all ${bundle.records.length.toLocaleString()} candidate records. Confirm each record against the linked official preview.`;
}

function downloadReceipt(receipt) {
  const blob = new Blob([`${JSON.stringify(receipt, null, 2)}\n`], { type: "application/json" });
  const link = document.createElement("a");
  const url = URL.createObjectURL(blob);
  link.href = url;
  link.download = `owner-review-${bundle.authority}-${bundle.exam}-${bundle.year}.json`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

elements.file.addEventListener("change", async () => {
  elements.workspace.hidden = true;
  bundle = null;
  const file = elements.file.files?.[0];
  if (!file) return;
  if (file.size > MAX_BUNDLE_BYTES) {
    setStatus("Review bundle exceeds the 50 MiB local limit.", "error");
    return;
  }
  try {
    bundle = await validateReviewBundle(JSON.parse(await file.text()));
    elements.title.textContent = `${bundle.authority} · ${bundle.exam} · ${bundle.year}`;
    elements.summary.textContent = `${bundle.record_count.toLocaleString()} records; candidate SHA-256 ${bundle.candidate_sha256}; capture manifest SHA-256 ${bundle.capture_manifest_sha256}.`;
    renderSources();
    renderRecords();
    renderEvidence();
    elements.workspace.hidden = false;
    setStatus("Bundle validated locally. Review the source and records before recording an outcome.", "success");
  } catch (error) {
    bundle = null;
    setStatus(error instanceof Error ? error.message : "Review bundle could not be validated.", "error");
  }
});

elements.query.addEventListener("input", renderRecords);

elements.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!bundle || !elements.form.reportValidity()) return;
  const receipt = {
    schema_version: 1,
    authority: bundle.authority,
    exam: bundle.exam,
    year: bundle.year,
    announced_count: bundle.announced_count,
    record_count: bundle.record_count,
    candidate_sha256: bundle.candidate_sha256,
    capture_manifest_sha256: bundle.capture_manifest_sha256,
    reviewer: elements.reviewer.value.trim(),
    source_evidence_reviewed: elements.evidenceReviewed.checked,
    records_reviewed: elements.recordsReviewed.checked,
    decision: elements.decision.value,
    notes: elements.notes.value.trim(),
    reviewed_at: new Date().toISOString(),
  };
  if (!receipt.reviewer) {
    setStatus("Enter the reviewer name before downloading the receipt.", "error");
    return;
  }
  downloadReceipt(receipt);
  setStatus("Receipt downloaded. It is not authoritative until committed and approved through the authorized GitHub review process.", "success");
});
