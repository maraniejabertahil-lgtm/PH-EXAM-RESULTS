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

**Visual extraction status:** The reusable capture currently extracts visible DOM text and retains screenshots as evidence; Tesseract remains advisory. Owner decision D-007 approves static viewport screenshot + OCR as a Tier 3 fallback only after direct file text and rendered DOM extraction are unavailable. Tier 3 must use lossless PNG captures after the rendered page stabilizes, retain image/OCR hashes and per-token confidence, hold low-confidence records for human review, and pass exact count, sequence coverage, duplicate, and Greenlight checks. It is not enabled for any source until terms/access review and an exam/source-specific OCR mapping are recorded. Video/frame OCR is excluded from production.

**CPALE public-preview timing trial (2026-11-05):** The PRC-linked ordinary Google Drive preview rendered without sign-in or human-verification barriers. A single-browser capture traversed all 80 viewer pages in 62.4 seconds; the extracted 3,988 records matched the PRC-announced count, covered sequences 1–3,988 without gaps or repeated sequences, and contained no duplicate names. A round-trip CSV check passed. This validates current Tier 2 access and local extraction only; it is not a Watcher-to-GitOps-to-Cloudflare publication run and is not an end-to-end publishing time measurement. See P2-03 and P2-30 in the Live Acceptance Test Register.

**Candidate integration status:** The isolated candidate routes the specifically allowlisted CPALE Drive file through PRC article-link/robots verification, ordinary public-preview UI capture, per-page PNG/text/hash evidence, a reviewed sequence/name mapping, and Greenlight. A live local candidate run completed all 80 viewer pages in four sequential browser shards, extracted 3,988 records matching the saved CPALE CSV exactly, and passed local Greenlight at 100/100 before generating one local dataset shard. A first single-browser attempt crashed on page 76; sequential sharding resolved the observed stability issue, and browser errors now stop safely for review. The normal PDF fetcher is not used for this route; no sign-in, challenge, or access-control bypass is attempted. Browser installation remains conditional in the PRC workflow. No GitOps, PR, merge, or deployment was invoked; visual review remains `PENDING`, and end-to-end publication timing is not established.

**Owner-review gate added in the candidate:** `python-engine/create_review_bundle.py` builds a hash-bound, local review bundle from the validated capture; the CPALE bundle contains all 3,988 records and 43 page screenshots covering every record. The review page validates the candidate and screenshot hashes, requires explicit source-evidence and records confirmations, and downloads a receipt bound to both candidate and capture-manifest hashes. Public-preview event runs now retain the bundle as an Actions artifact instead of calling GitOps. Publication requires an owner-dispatched workflow from `main`, the exact capture run ID, and an approved matching receipt; the published manifest and validation report retain the audit attestation. The 146 in-scope Python and 10 frontend tests passed, with CSC-specific suites and stale acceptance tests excluded per the existing scope. A mocked 3,988-record pipeline run passed. No human owner review, GitHub publication, merge, or deployment has occurred.

**Post-merge website status (2026-11-06):** PR #98 is squash-merged. Cloudflare Pages deployed successfully, the production Watcher deployed successfully, all merge-commit CI checks passed, and the public Pages URL returned HTTP 200. The live catalog currently contains only the PRC LEPT Elementary 2026 dataset (18,376 records). The release-to-publication automation change is being prepared separately and is not active in production until merged and deployed.

**Automated release-to-publication policy (current change):** PRC detection events already reach the processing workflow. This change lets an explicitly allowlisted exam/year (`auto_publish_exams`) continue automatically through official public-preview capture, exact Greenlight, GitOps PR creation, exact-head CI, conditional merge, Pages deployment, and post-deployment broadcasting. The source registry currently allowlists CPALE-2026 for this path. LEPT-SECONDARY remains Owner-review-required under D-004; absent/invalid source policy, unsupported mappings, access challenges, incomplete counts, Greenlight failures, and uncertain CI/merge outcomes stop without publication. New examinations require their source, terms, and extraction mapping to be reviewed and configured before entering the auto-publish allowlist. This is automated publication only for explicitly pre-approved inputs, not blanket publication of arbitrary detected files.

**Local frontend acceptance evidence:** Chromium 156 loaded the candidate site at desktop and 390-pixel mobile widths without horizontal overflow or browser errors; Preparing Mode, an expected name/sequence search, and repeat-session IndexedDB shard reuse were verified. Five 50,000-record worker searches had a 57.4 ms p95 round trip, a 16.8 ms maximum observed animation-frame gap, and no gaps above 50 ms. Search requests stayed local; only static assets, status/catalog, manifest, and the initial data shard were requested. These are local candidate checks, not a deployed-site acceptance. Reloading the site while fully offline is not supported; cached shard reuse was verified on an online reload.

**Phase 2 implementation position and remaining acceptance:** The reusable extraction, normalization, validation, dataset, and GitOps components are implemented. The Owner's 2026-11-06 request for a one-month real-world trial supersedes D-005's deferral of all real publication activity for the explicitly allowlisted automated path; it does not waive source, Greenlight, security, or publication gates. The Unicode parser prototype's two name anomalies must still be resolved against official visible evidence without guessing before that prototype is used. The existing LEPT Elementary data remains published with its documented source-quality caveat. The LEPT Secondary candidate (45,001 announced passers) remains unpublished until Owner review under D-004. CSC-specific testing remains excluded by D-003.

---

### Phase 3 — Automated Broadcasting

Build and verify the Python broadcaster integrations for Facebook Graph API and Telegram Bot API. Broadcasts must occur only after a validated result dataset has merged and deployment has succeeded.

**Current delivery status:** Implemented and merged to `main` in PR #96. The Python Facebook Pages and Telegram Bot API adapters, successful-Pages-deployment trigger, changed-result-manifest filter, and durable GitHub-branch delivery ledger are present. The PR's GitHub Actions CI passed with 147 Python tests, including 11 focused broadcaster tests. The Pages workflow is now merged and deployed. Real provider connectivity remains unverified until the Owner configures credentials and approves test destinations.

---

### Phase 4 — Frontend Web Worker Search

Build the static HTML/CSS frontend, IndexedDB dataset caching, JavaScript Web Worker search, and Cloudflare Pages deployment. Search must remain browser-side and must return the passer name with its corresponding sequence number.

**Current delivery status:** The static search site, Preparing Mode, manifest/shard loading, IndexedDB cache, Web Worker search, Pages workflow, and local-only Owner review experience are deployed. PR #98's checks and the main-branch Pages deployment succeeded; the live site returned HTTP 200 and currently serves the verified 18,376-record PRC LEPT Elementary dataset. The post-deployment broadcaster trigger is active for changed result manifests, but provider credentials and destinations remain unconfigured/unverified. Owner walkthrough and month-long real-world acceptance remain in progress/not yet evidenced.

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
| D-005 | 2026-11-05 | All phases — implementation order and final acceptance | Implement all five phases before conducting the comprehensive Live Acceptance Test. Defer the real PRC publication batch and live Facebook/Telegram provider delivery to the final acceptance stage. | Continue offline unit tests, static checks, and GitHub CI during implementation, but do not claim live acceptance or publish a new result batch until Phases 1–5 implementation is complete. The deferred real PRC batch is moved from the Phase 2 implementation checklist to Phase 5 final acceptance. This Owner approval authorizes work through all five phases; it does not waive the Greenlight, source-review, security, or publication gates. | Superseded for the staged trial by D-008; remaining gates preserved |
| D-006 | 2026-11-05 | Phase 2 — PRC official-unavailable fallback | After compliant public retrieval confirms the official result document requires sign-in, automatically try two independent, publicly accessible, terms-reviewed, Owner-approved/verified third-party sources. | This supersedes the manual-only routing for an authentication-required official result document, but does not permit using credentials, bypassing sign-in, CAPTCHA, MFA, robots policy, or other controls. Both third-party sources must provide exact sequence/name pairs and pass the existing 100% agreement, announced-count, completeness, and Greenlight checks. CAPTCHA/human-verification still stops automation. Source domains and extraction mappings require one-time review/approval before being enabled; an unverified or unavailable pair remains unpublished. | Active |
| D-007 | 2026-11-05 | Phase 2 — visual extraction fallback | Approve the four-tier acquisition hierarchy: direct file/PDF text, rendered DOM, static PNG screenshot + OCR, then video/frame OCR only as a deprecated experimental edge case. Tier 3 is a fallback, not a bypass or a new primary source path. | Screenshot OCR may run only for sources whose access directives and reuse terms have been reviewed and recorded, and only with a reviewed source/exam extraction mapping. Capture must wait for a stable rendered viewport and preserve lossless image evidence. Per-token confidence below 95% routes the record to human review; no low-confidence record may pass automatically. The complete result must match the announced count, have exact sequence coverage and zero duplicates, and pass Greenlight before any publication eligibility. Video/frame extraction is not part of production. | Active |
| D-008 | 2026-11-06 | All phases — one-month automated trial | Automate PRC release detection through capture, Greenlight, GitOps publication, Pages deployment, and eligible post-deployment broadcast for explicitly pre-approved exam/source mappings during the Owner's one-month real-world test. | Only exact exams listed in `auto_publish_exams` may publish without a visual receipt. D-004 LEPT-SECONDARY review remains mandatory. Missing or invalid policy, unreviewed sources/mappings, access barriers, low-confidence records, failed Greenlight, and failed/uncertain CI remain fail-closed. This supersedes D-005's blanket deferral of the initial approved automated trial, but does not waive its comprehensive acceptance, security, or source-quality requirements. | Active |

---

## Delivery governance

- Do not mark a task complete without evidence that the task's actual acceptance condition has been met.
- An automated test pass does not automatically establish live production acceptance.
- Do not begin a later phase until the Owner approves the phase transition, as required by `AI_BLUEPRINT.md`. Owner decision D-005 grants approval to implement Phases 1–5 in sequence while reserving comprehensive Live Acceptance for the end.
- Preserve the last known-good published dataset whenever acquisition, extraction, validation, or publication fails.
- Keep this document aligned with `PROGRESS_TRACKER.md`; do not use this summary as a substitute for the tracker.

---

**Related register:** [Part 17 — Live Acceptance Test Register](LIVE_ACCEPTANCE_TEST_REGISTER.md) · **Operational checklist:** [Progress Tracker](PROGRESS_TRACKER.md)
