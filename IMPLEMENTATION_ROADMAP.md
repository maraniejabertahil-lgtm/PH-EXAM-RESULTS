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

**Current delivery status:** Core extractor, Greenlight validation, dataset builder/sharding, GitOps integration, reviewed normalization, and bounded same-origin acquisition are implemented. PRs #58 and #59 integrated hash-bound official public-preview capture into the Python Engine; PR #60 optimized JSON shard sizing from quadratic to linear time. Main-branch CI passed with 116 Python tests. The earlier March 2026 LEPT Elementary batch run (18,376 records) has a recorded Greenlight 100/100 result and generated a hash-verified 862,332-byte dataset shard. This must not be conflated with the later Unicode parser prototype report supplied on 2026-11-05: that prototype also recovered all 18,376 sequence numbers but retained two unresolved name anomalies (sequences 10,710 and 15,066), so that prototype did **not** achieve Greenlight and was not published. The latest report is evidence of parser progress, not approval to publish.

A reusable public-preview page-capture component and callable GitHub Actions workflow are now on main. It supports 1–16 bounded parallel shards, ordinary visible-UI capture, exact page-range merge checks, per-page and archive SHA-256 validation, and a no-retry stop on access challenges. Eight local regression tests pass; the reusable workflow itself has not yet had a live invocation. This page-capture sharding is distinct from the existing 10 MiB JSON dataset sharding. Secondary trial run #36 independently demonstrated the 16-shard method against 901 pages, but that run used the earlier exam-specific script.

**Phase 2 implementation position and final-acceptance deferral:** The reusable extraction, normalization, validation, dataset, and GitOps components are implemented. The real public-release-to-merge run is deliberately deferred to Phase 5 under Owner decision D-005, so no real result batch will be pushed through the publication path during the remaining phase implementation. The following remain explicit final-acceptance gates: (1) resolve the two Unicode prototype anomalies against the official visible source without guessing; (2) verify the repository setting `Allow GitHub Actions to create and approve pull requests` because a previous GitHub Actions PR-creation attempt returned HTTP 403; (3) ensure the source used for publication satisfies the Owner review gate, including the DRAFT watermark concern; and (4) run the approved PRC batch through the complete pipeline. The PRC LEPT Secondary candidate (45,001 announced passers) remains unpublished until the future Owner-facing review experience required by D-004 is implemented and the Owner review gate is satisfied. CSC-specific testing remains excluded by D-003.

---

### Phase 3 — Automated Broadcasting

Build and verify the Python broadcaster integrations for Facebook Graph API and Telegram Bot API. Broadcasts must occur only after a validated result dataset has merged and deployment has succeeded.

**Current delivery status:** Initial implementation is on branch `implementation/phase3-broadcasting-20261105`, not yet merged. It adds the Python Facebook/Telegram adapters, post-deployment-only workflow trigger, and a durable GitHub-branch delivery ledger. Eleven focused offline unit tests are included. GitHub CI and PR review are still pending. Real provider connectivity is deferred until final Live Acceptance because the required Owner credentials are not yet configured.

---

### Phase 4 — Frontend Web Worker Search

Build the static HTML/CSS frontend, IndexedDB dataset caching, JavaScript Web Worker search, and Cloudflare Pages deployment. Search must remain browser-side and must return the passer name with its corresponding sequence number.

**Current delivery status:** Not started; tasks remain unchecked in `PROGRESS_TRACKER.md`. Per Owner decision D-004, this phase also includes a future Owner-facing review experience for source evidence and extracted records; the public search route must remain read-only. The Pages workflow must be named `Deploy Cloudflare Pages` to activate the Phase 3 post-deployment broadcaster.

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
| D-005 | 2026-11-05 | All phases — implementation order and final acceptance | Implement all five phases before conducting the comprehensive Live Acceptance Test. Defer the real PRC publication batch and live Facebook/Telegram provider delivery to the final acceptance stage. | Continue offline unit tests, static checks, and GitHub CI during implementation, but do not claim live acceptance or publish a new result batch until Phases 1–5 implementation is complete. The deferred real PRC batch is moved from the Phase 2 implementation checklist to Phase 5 final acceptance. This Owner approval authorizes work through all five phases; it does not waive the Greenlight, source-review, security, or publication gates. | Active |

---

## Delivery governance

- Do not mark a task complete without evidence that the task's actual acceptance condition has been met.
- An automated test pass does not automatically establish live production acceptance.
- Do not begin a later phase until the Owner approves the phase transition, as required by `AI_BLUEPRINT.md`. Owner decision D-005 grants approval to implement Phases 1–5 in sequence while reserving comprehensive Live Acceptance for the end.
- Preserve the last known-good published dataset whenever acquisition, extraction, validation, or publication fails.
- Keep this document aligned with `PROGRESS_TRACKER.md`; do not use this summary as a substitute for the tracker.

---

**Related register:** [Part 17 — Live Acceptance Test Register](LIVE_ACCEPTANCE_TEST_REGISTER.md) · **Operational checklist:** [Progress Tracker](PROGRESS_TRACKER.md)
