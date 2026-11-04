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


## Cross-document communication protocol

The three project records are connected by references, not synchronized copies. Their authority is deliberately separate:

| Record | Owns | Does not replace |
|---|---|---|
| `PROGRESS_TRACKER.md` | Operational task checklist, checkbox completion, and first unchecked task | Acceptance evidence or the full Owner decision history |
| Part 16 — this roadmap | Phase-level delivery context and the authoritative Owner decision register | Individual task checkbox status or detailed test evidence |
| Part 17 — `LIVE_ACCEPTANCE_TEST_REGISTER.md` | Acceptance conditions, test outcomes, and supporting evidence | Implementation task completion or Owner decision history |

**Communication rules**
1. Use the exact task wording in `PROGRESS_TRACKER.md` when identifying implementation work. Part 16 summarizes its effect on the phase; it does not independently declare a checklist task complete.
2. Link relevant Part 17 test IDs to the implementation task(s) they verify. A task may have several tests, and a test may verify behavior implemented by more than one task.
3. Record explicit Owner approvals, rejections, skips, deferrals, and direction changes in the Owner decision register below. Part 17 references the decision ID; the tracker is changed only if the decision changes the actual task scope or completion state.
4. A completed implementation task does not imply acceptance PASS. Likewise, a passing test does not automatically complete an implementation task unless that task's own completion condition is met.
5. If a discrepancy appears, do not force statuses to match. Resolve it using the record that owns the information: tracker for task status, Part 16 for Owner decisions and phase summary, Part 17 for acceptance outcomes and evidence.
6. Keep links and decision/test references current when records change. Never modify the Master Technical Blueprint without explicit Owner authorization.

## Phase roadmap

### Phase 1 — The Watcher (Cloudflare Worker)

Build and verify the Cloudflare Worker that monitors approved official PRC/CSC sources, handles Peak Week mode, performs only compliant preemptive checks, and dispatches qualifying events to GitHub Actions.

**Current delivery status:** Implementation checklist completed and Owner reports personally testing the phase. Genuine production acceptance remains open: a real official result-release detection and dispatch has not yet been demonstrated, and production preemptive URL templates remain unverified. CSC Region V remains paused after an HTTP 403 security-verification response; no access-control bypass is permitted.

---

### Phase 2 — The Extractor & Greenlight (Python and GitOps)

Build the Python processing pipeline to acquire official result contents, extract passer names with their exact official sequence numbers, validate the records through Greenlight, generate Array-of-Arrays datasets, and open/merge GitOps pull requests only when all required checks pass. PDF acquisition is optional; the required output is the accurate name/sequence pair.

**Current delivery status:** Core extractor, Greenlight validation, dataset builder/sharding, GitOps integration, reviewed normalization, and bounded same-origin acquisition are implemented. PRs #58 and #59 integrated hash-bound official public-preview capture into the Python Engine; PR #60 optimized JSON shard sizing from quadratic to linear time. Main-branch CI passed with 116 Python tests. The March 2026 LEPT Elementary full batch (18,376 records) has passed Greenlight 100/100 and generated a hash-verified 862,332-byte dataset shard.

A reusable public-preview page-capture component and callable GitHub Actions workflow are now on main. It supports 1–16 bounded parallel shards, ordinary visible-UI capture, exact page-range merge checks, per-page and archive SHA-256 validation, and a no-retry stop on access challenges. Ten regression tests now cover the reusable page-shard component, including in-place page retry and immediate access-challenge stop. Live PRC preview acceptance run #41851646784 completed 16/16 shards, captured 901/901 pages, verified exact coverage and SHA-256 evidence, and measured a 64.427-second capture span. This was approximately 17% faster than the earlier exam-specific 77.45-second capture-span baseline; treat the comparison as an observed run, not a controlled benchmark. This page-capture sharding is distinct from the existing 10 MiB JSON dataset sharding. The live run captured viewer text only: the generic page-snapshot manifest still needs a separate bridge into the Python Engine's hash-bound JSONL/provenance/extraction manifest contract before full record extraction can consume it. The DRAFT-watermarked Secondary candidate remains unpublished pending the deferred human visual review.

**Remaining Phase 2 tasks:**
- Completed: a compliant PRC owner-reviewed manual-content handoff yielded 50 name/sequence pairs from page 2 of the March 2026 LEPT Elementary roll; PR #56 validates the mapping. The full Elementary batch subsequently passed official public-preview extraction, exact sequence coverage, Greenlight, and dataset generation.
- Blocked: GitOps staged the Elementary dataset on `data/greenlight-37cd69173dc2`, but GitHub Actions received HTTP 403 because the repository does not permit Actions to create pull requests. The Owner must enable the repository setting `Allow GitHub Actions to create and approve pull requests`. The source preview also carries a DRAFT watermark; Owner review is required before merge.
- Remaining after the Elementary publication gate: process the official PRC LEPT Secondary list (45,001 announced passers) through the same public-preview, Greenlight, dataset, and GitOps path. CSC-specific testing remains excluded by D-003.

---

### Phase 3 — Automated Broadcasting

Build and verify the Python broadcaster integrations for Facebook Graph API and Telegram Bot API. Broadcasts must occur only after a validated result dataset has merged and deployment has succeeded.

**Current delivery status:** Not started; tasks remain unchecked in `PROGRESS_TRACKER.md`.

---

### Phase 4 — Frontend Web Worker Search

Build the static HTML/CSS frontend, IndexedDB dataset caching, JavaScript Web Worker search, and Cloudflare Pages deployment. Search must remain browser-side and must return the passer name with its corresponding sequence number.

**Current delivery status:** Not started; tasks remain unchecked in `PROGRESS_TRACKER.md`. Per Owner decision D-004, this phase also includes a future Owner-facing review experience for source evidence and extracted records; the public search route must remain read-only.

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
| D-002 | 2026-11-03 | Phase 2 — CSC-side release/source assessment | Skip the specific CSC-side PDF-release path because passer details are provided through a portal rather than a passer-list PDF; assess the portal as the relevant content source instead. | This was the earlier source/path direction; it is superseded in testing scope by D-003. | Superseded |
| D-003 | 2026-11-03 | All phases — CSC testing scope | Skip all CSC-related testing. Continue current result-content acquisition and validation work using PRC sources only. | Do not run CSC portal, source-access, acquisition, extraction, PDF, Watcher-source, or CSC-specific acceptance tests. Preserve existing CSC code and architecture; this decision excludes testing, not future CSC support or deletion of implementation. No CSC tests are required for the current Phase 2 path. | Active |
| D-004 | 2026-11-04 | Phase 2 Secondary candidate review / Phase 4 website | Defer the current manual visual review of the March 2026 LEPT Secondary candidate; implement an Owner-facing website review experience in a later website update. | Do not treat automated extraction or Greenlight as human visual approval. Keep the Secondary candidate unpublished until the future review process is implemented and completed and the Owner's publication gate is satisfied. Preserve the public search route as read-only; do not bypass source access controls. | Active |

---

## Delivery governance

- Do not mark a task complete without evidence that the task's actual acceptance condition has been met.
- An automated test pass does not automatically establish live production acceptance.
- Do not begin a later phase until the Owner approves the phase transition, as required by `AI_BLUEPRINT.md`.
- Preserve the last known-good published dataset whenever acquisition, extraction, validation, or publication fails.
- Keep this document aligned with `PROGRESS_TRACKER.md`; do not use this summary as a substitute for the tracker.

---

**Related register:** [Part 17 — Live Acceptance Test Register](LIVE_ACCEPTANCE_TEST_REGISTER.md) · **Operational checklist:** [Progress Tracker](PROGRESS_TRACKER.md)
