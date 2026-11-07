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

**Visual extraction status:** The reusable capture extracts visible DOM text and retains screenshots as evidence. The D-007 Tier 3 static PNG + Tesseract OCR engine is now implemented and merged in PRs #108 and #109. It requires documented Tier 1 and Tier 2 unavailability, the exact allowlisted official Drive preview, stable lossless PNG evidence, an Owner-reviewed source/exam mapping, and separate Owner-reviewed access-directives and reuse-terms records. It records screenshot and OCR TSV SHA-256 hashes plus per-token confidence; any token below 95% is held for human review. Only a complete announced-count match, exact sequence coverage, zero duplicate sequence numbers/names, and a successful existing Greenlight validation can proceed toward GitOps. Eight isolated synthetic OCR tests, the in-scope Python suite, and all-branch compatibility checks passed. The production mapping registry remains intentionally empty: no source-specific terms/access review or OCR mapping has been recorded, no source is enabled, and P2-29 remains NOT RUN. Tesseract is installed only for an explicitly selected manual Tier 3 batch. Video/frame OCR is excluded from production.

**CPALE public-preview timing trial (2026-11-05):** The PRC-linked ordinary Google Drive preview rendered without sign-in or human-verification barriers. A single-browser capture traversed all 80 viewer pages in 62.4 seconds; the extracted 3,988 records matched the PRC-announced count, covered sequences 1–3,988 without gaps or repeated sequences, and contained no duplicate names. A round-trip CSV check passed. This validates current Tier 2 access and local extraction only; it is not a Watcher-to-GitOps-to-Cloudflare publication run and is not an end-to-end publishing time measurement. See P2-03 and P2-30 in the Live Acceptance Test Register.

**Candidate integration status:** The isolated candidate routes the specifically allowlisted CPALE Drive file through PRC article-link/robots verification, ordinary public-preview UI capture, per-page PNG/text/hash evidence, a reviewed sequence/name mapping, and Greenlight. A live local candidate run completed all 80 viewer pages in four sequential browser shards, extracted 3,988 records matching the saved CPALE CSV exactly, and passed local Greenlight at 100/100 before generating one local dataset shard. A first single-browser attempt crashed on page 76; sequential sharding resolved the observed stability issue, and browser errors now stop safely for review. The normal PDF fetcher is not used for this route; no sign-in, challenge, or access-control bypass is attempted. Browser installation remains conditional in the PRC workflow. No GitOps, PR, merge, or deployment was invoked; visual review remains `PENDING`, and end-to-end publication timing is not established.

**Owner-review experience added in the candidate:** `python-engine/create_review_bundle.py` builds a hash-bound review bundle from a captured candidate; the CPALE bundle contains all 3,988 records and 43 page screenshots. The review page validates candidate and screenshot hashes, requires explicit source-evidence and records confirmations, and creates a receipt bound to both candidate and capture-manifest hashes. This remains available for follow-up when verification is inconclusive. The prior unconditional receipt requirement for LEPT Secondary is superseded by D-009: candidates publish without a receipt only when their configured official source/mapping and every automated validation pass; unsupported or failed candidates remain held. The 146 in-scope Python and 10 frontend tests passed at candidate stage; no end-to-end live publication had occurred then.

**Post-merge production status (2026-11-06):** PR #98 is squash-merged. Cloudflare Pages and the production Watcher deployed successfully, merge-commit CI passed, and the public Pages URL returned HTTP 200. PR #99 (`756a600`) and PR #101 (`631b25f`) are merged and their main-branch CI passed. The source-wide PRC auto-publication policy is active in `process-import.yml`; no Pages or Worker deployment was needed for these GitHub Actions/Python policy changes. The live catalog still contains only PRC LEPT Elementary 2026 (18,376 records). No PRC event after policy activation has completed detection-to-publication, so real end-to-end acceptance remains pending.

**Automated release-to-publication policy (active since PR #101, 2026-11-06):** PRC detections with an authorized source and configured exam-specific source/mapping are eligible to publish automatically after capture/extraction and the full exact Greenlight pass, then proceed through GitOps PR creation, exact-head CI, conditional merge, Pages deployment, and eligible post-deployment broadcasting. The source-wide `auto_publish_after_greenlight` setting removes the prior CPALE-2026-only exam/year allowlist. An announced-count mismatch, missing/duplicate/out-of-range sequences, name anomalies, unsupported or unreviewed mappings, access barriers, invalid policy, failed checks, or uncertain CI/merge outcomes stop the run without publication; event reports/artifacts are retained for follow-up. No automatic bypass of PRC source authorization, source terms, robots/access controls, or review needed for unresolved records is permitted. LEPT Secondary is not yet configured with its official source and extraction mapping, so it remains held until that work is done. No post-merge event has completed the full path yet; the one-month trial window is 2026-11-06 through 2026-12-06.

**Local frontend acceptance evidence:** Chromium 156 loaded the candidate site at desktop and 390-pixel mobile widths without horizontal overflow or browser errors; Preparing Mode, an expected name/sequence search, and repeat-session IndexedDB shard reuse were verified. Five 50,000-record worker searches had a 57.4 ms p95 round trip, a 16.8 ms maximum observed animation-frame gap, and no gaps above 50 ms. Search requests stayed local; only static assets, status/catalog, manifest, and the initial data shard were requested. These are local candidate checks, not a deployed-site acceptance. Reloading the site while fully offline is not supported; cached shard reuse was verified on an online reload.

**Phase 2 implementation position and remaining acceptance:** The reusable extraction, normalization, validation, dataset, and GitOps components are implemented. The Owner's 2026-11-06 requests supersede D-005's deferral and D-004's unconditional LEPT Secondary review gate only for candidates that pass D-009's automated checks; source, Greenlight, access, security, and exact-head CI gates remain mandatory. The Unicode parser prototype's two name anomalies must be resolved against official visible evidence without guessing before that prototype can be used. The existing LEPT Elementary data remains published with its documented source-quality caveat. LEPT Secondary remains unpublished until its official source and extraction mapping are configured and the candidate passes all checks; no mapping is currently configured. CSC-specific testing remains excluded by D-003.

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
| D-004 | 2026-11-04 | Phase 2 Secondary candidate review / Phase 4 website | Defer the current manual visual review of the March 2026 LEPT Secondary candidate; implement an Owner-facing website review experience in a later website update. | Do not treat automated extraction or Greenlight as human visual approval. Keep the Secondary candidate unpublished until the future review process is implemented and completed and the Owner's publication gate is satisfied. Preserve the public search route as read-only; do not bypass source access controls. | Superseded for batches that pass D-009 automated verification; otherwise remains held |
| D-005 | 2026-11-05 | All phases — implementation order and final acceptance | Implement all five phases before conducting the comprehensive Live Acceptance Test. Defer the real PRC publication batch and live Facebook/Telegram provider delivery to the final acceptance stage. | Continue offline unit tests, static checks, and GitHub CI during implementation, but do not claim live acceptance or publish a new result batch until Phases 1–5 implementation is complete. The deferred real PRC batch is moved from the Phase 2 implementation checklist to Phase 5 final acceptance. This Owner approval authorizes work through all five phases; it does not waive the Greenlight, source-review, security, or publication gates. | Superseded for the staged trial by D-008; remaining gates preserved |
| D-006 | 2026-11-05 | Phase 2 — PRC official-unavailable fallback | After compliant public retrieval confirms the official result document requires sign-in, automatically try two independent, publicly accessible, terms-reviewed, Owner-approved/verified third-party sources. | This supersedes the manual-only routing for an authentication-required official result document, but does not permit using credentials, bypassing sign-in, CAPTCHA, MFA, robots policy, or other controls. Both third-party sources must provide exact sequence/name pairs and pass the existing 100% agreement, announced-count, completeness, and Greenlight checks. CAPTCHA/human-verification still stops automation. Source domains and extraction mappings require one-time review/approval before being enabled; an unverified or unavailable pair remains unpublished. | Active |
| D-007 | 2026-11-05 | Phase 2 — visual extraction fallback | Approve the four-tier acquisition hierarchy: direct file/PDF text, rendered DOM, static PNG screenshot + OCR, then video/frame OCR only as a deprecated experimental edge case. Tier 3 is a fallback, not a bypass or a new primary source path. | Screenshot OCR may run only for sources whose access directives and reuse terms have been reviewed and recorded, and only with a reviewed source/exam extraction mapping. Capture must wait for a stable rendered viewport and preserve lossless image evidence. Per-token confidence below 95% routes the record to human review; no low-confidence record may pass automatically. The complete result must match the announced count, have exact sequence coverage and zero duplicates, and pass Greenlight before any publication eligibility. Video/frame extraction is not part of production. | Active |
| D-008 | 2026-11-06 | All phases — one-month automated trial | Automate PRC release detection through capture, Greenlight, GitOps publication, Pages deployment, and eligible post-deployment broadcast during the Owner's one-month real-world test. | Initially restricted publication to exact exams listed in `auto_publish_exams`. D-009 supersedes that per-exam publication restriction for configured, authorized sources whose candidates pass automated checks; source, access, accuracy, and CI gates remain fail-closed. This supersedes D-005's blanket deferral of the scoped trial, but not comprehensive acceptance requirements. | Superseded by D-009; other trial terms active |
| D-009 | 2026-11-06 | All phases — automated publication after verification | Publish a detected PRC result automatically as soon as it passes all configured system verification, without an additional Owner visual-review receipt solely because of its exam identity. | Enable source-wide auto-publication after Greenlight for configured PRC source/exam mappings. Require exact announced-count match, complete unique sequence coverage, valid names/records, official source authorization, approved access, reviewed extraction configuration, and successful exact-head CI before merge. Any mismatch, missing/unsupported mapping, access challenge, low-confidence/unresolved record, policy error, failed check, or uncertain merge is held and not published. This supersedes D-004's blanket LEPT Secondary human-review gate and D-008's CPALE-only allowlist; it does not authorize guessing, bypassing access controls, or publishing a batch that fails or cannot complete verification. | Active (PR #101 merged; main CI passed) |
| D-010 | 2026-11-07 | Phase 4 — Private Owner Dashboard authentication | Use Firebase Authentication email/password as the sole Owner login proof, with exact verified email matching `OWNER_EMAIL` and Firestore `users/{uid}` requiring `email`, `role: "owner"`, and `active: true`. Do not require an email code, OTP, or GitHub OAuth second sign-in. | The Owner wants to use the existing Firebase password without a second provider code. Preserve server-side Firebase token signature/claim verification, optional exact UID pin, Firestore role checks, short-lived signed handoff, eight-hour HttpOnly session, CSRF-protected logout, and private route/D1 authorization. This supersedes the previous dual-proof login requirement for Owner access only; it does not weaken public search or result-publishing gates. | Active (PR #143 merged; Firebase-only CI and production deployment workflow #158 passed; real Owner browser acceptance remains open) |

---

## Delivery governance

- Do not mark a task complete without evidence that the task's actual acceptance condition has been met.
- An automated test pass does not automatically establish live production acceptance.
- Do not begin a later phase until the Owner approves the phase transition, as required by `AI_BLUEPRINT.md`. Owner decision D-005 grants approval to implement Phases 1–5 in sequence while reserving comprehensive Live Acceptance for the end.
- Preserve the last known-good published dataset whenever acquisition, extraction, validation, or publication fails.
- Keep this document aligned with `PROGRESS_TRACKER.md`; do not use this summary as a substitute for the tracker.

---

**Related register:** [Part 17 — Live Acceptance Test Register](LIVE_ACCEPTANCE_TEST_REGISTER.md) · **Operational checklist:** [Progress Tracker](PROGRESS_TRACKER.md)
