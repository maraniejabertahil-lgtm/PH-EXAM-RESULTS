# PART 16 — IMPLEMENTATION ROADMAP & DELIVERY STATUS

> **Document role:** Implementation roadmap and current delivery position.
>
> **Companion documents:** `PROGRESS_TRACKER.md` is the operational task checklist. Part 17, `LIVE_ACCEPTANCE_TEST_REGISTER.md`, contains the detailed acceptance tests and evidence.
>
> **Governance:** The Master Technical Blueprint remains the governing architecture. This document does not replace it or the task tracker.

---

## Contents

1. [Purpose](#purpose)
2. [Phase roadmap](#phase-roadmap)
   - [Phase 1 — The Watcher](#phase-1--the-watcher-cloudflare-worker)
   - [Phase 2 — The Extractor & Greenlight](#phase-2--the-extractor--greenlight-python-and-gitops)
   - [Phase 3 — Automated Broadcasting](#phase-3--automated-broadcasting)
   - [Phase 4 — Frontend Web Worker Search](#phase-4--frontend-web-worker-search)
   - [Phase 5 — End-to-End Simulation & Security](#phase-5--end-to-end-simulation--security)
3. [Delivery governance](#delivery-governance)

---

## Purpose

This document contains the implementation roadmap and current delivery position for PH-EXAM-RESULTS. The task checklist in `PROGRESS_TRACKER.md` is the operational source of truth for completed and remaining tasks. This document summarizes the phase objectives and current delivery state; it is not a historical activity log.

## Phase roadmap

### Phase 1 — The Watcher (Cloudflare Worker)

Build and verify the Cloudflare Worker that monitors approved official PRC/CSC sources, handles Peak Week mode, performs only compliant preemptive checks, and dispatches qualifying events to GitHub Actions.

**Current delivery status:** Implementation checklist completed and Owner reports personally testing the phase. Genuine production acceptance remains open: a real official result-release detection and dispatch has not yet been demonstrated, and production preemptive URL templates remain unverified. CSC Region V remains paused after an HTTP 403 security-verification response; no access-control bypass is permitted.

---

### Phase 2 — The Extractor & Greenlight (Python and GitOps)

Build the Python processing pipeline to acquire official result contents, extract passer names with their exact official sequence numbers, validate the records through Greenlight, generate Array-of-Arrays datasets, and open/merge GitOps pull requests only when all required checks pass. PDF acquisition is optional; the required output is the accurate name/sequence pair.

**Current delivery status:** Core extractor, Greenlight validation, dataset builder/sharding, GitOps integration, reviewed normalization, and bounded same-origin acquisition are implemented. PR #55 added a missing-sequence publication-abort regression test; the PR and main-branch CI passed with 112 Python tests.

**Remaining Phase 2 tasks:**
- Identify and validate a compliant official-content access path that provides passer names and exact sequence numbers. A downloadable PDF is not required. The PRC-linked Drive view inspected so far did not expose the records; owner-reviewed manual handoff is available.
- Validate the extraction/normalization mapping against a representative official content sample and prove exact name/sequence pairs.
- Process one real, publicly released result batch through acquisition, extraction, Greenlight, dataset generation, GitOps PR, CI, and merge.

---

### Phase 3 — Automated Broadcasting

Build and verify the Python broadcaster integrations for Facebook Graph API and Telegram Bot API. Broadcasts must occur only after a validated result dataset has merged and deployment has succeeded.

**Current delivery status:** Not started; tasks remain unchecked in `PROGRESS_TRACKER.md`.

---

### Phase 4 — Frontend Web Worker Search

Build the static HTML/CSS frontend, IndexedDB dataset caching, JavaScript Web Worker search, and Cloudflare Pages deployment. Search must remain browser-side and must return the passer name with its corresponding sequence number.

**Current delivery status:** Not started; tasks remain unchecked in `PROGRESS_TRACKER.md`.

---

### Phase 5 — End-to-End Simulation & Security

Run end-to-end dummy and safety tests, verify secrets are not exposed, and validate the authorized manual-drop workflow.

**Current delivery status:** Not started; tasks remain unchecked in `PROGRESS_TRACKER.md`.

---

## Owner decision register

This register records explicit decisions made by the Owner that affect a phase, task, source, implementation approach, or acceptance condition. It is a decision record, not a general conversation history.

**Recording rules**
- Add a decision when the Owner explicitly approves, rejects, skips, defers, or changes the direction of a task or phase.
- Record the decision under the affected phase/task and assign a stable ID (`D-001`, `D-002`, ...).
- State the exact scope. Do not turn a decision about one source or release into a blanket rule for an entire authority or phase.
- Record the reason and practical effect, including any acceptance-condition change. Do not silently change the Master Technical Blueprint.
- Part 16 is the authoritative decision register. Part 17 records the related decision ID beside affected acceptance tests; it does not duplicate the full decision history.
- A later change must be added as a new decision entry that supersedes the earlier one; do not erase the earlier record.

| Decision ID | Date | Phase / task | Owner decision | Reason / effect | Status |
|---|---|---|---|---|---|
| D-001 | 2026-11-03 | Phase 2 — official result-content acquisition | The required result is the passer's name paired with its official sequence number. Downloading or storing a PDF is not required. | Pursue compliant official content in any available format, including an official portal/page or structured data. PDF acquisition is optional and only used when it is a practical authorized way to obtain the contents. | Active |
| D-002 | 2026-11-03 | Phase 2 — CSC-side release/source assessment | Skip the specific CSC-side PDF-release path because passer details are provided through a portal rather than a passer-list PDF; assess the portal as the relevant content source instead. | This is a source/path decision only. It does not mean all CSC sources or portal access are permanently excluded. Continue only through compliant, publicly accessible access; never bypass authentication or human verification. | Active |

---

## Delivery governance

- Do not mark a task complete without evidence that the task's actual acceptance condition has been met.
- An automated test pass does not automatically establish live production acceptance.
- Do not begin a later phase until the Owner approves the phase transition, as required by `AI_BLUEPRINT.md`.
- Preserve the last known-good published dataset whenever acquisition, extraction, validation, or publication fails.
- Keep this document aligned with `PROGRESS_TRACKER.md`; do not use this summary as a substitute for the tracker.

---

**Related register:** [Part 17 — Live Acceptance Test Register](LIVE_ACCEPTANCE_TEST_REGISTER.md) · **Operational checklist:** [Progress Tracker](PROGRESS_TRACKER.md)
