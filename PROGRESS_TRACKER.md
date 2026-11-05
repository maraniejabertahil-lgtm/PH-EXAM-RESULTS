# Project Progress & Phase Tracker

> **Active Phase:** Phase 4  
> **Status:** In Progress  

---

## Connected project records

These documents are connected by references, not synchronized copies. Each has a separate responsibility:

- **This file — operational task checklist:** authoritative checkbox status and the active implementation task.
- **[Part 16 — Implementation Roadmap](IMPLEMENTATION_ROADMAP.md):** phase-level delivery context and the authoritative Owner decision register.
- **[Part 17 — Live Acceptance Test Register](LIVE_ACCEPTANCE_TEST_REGISTER.md):** acceptance conditions, observed test outcomes, and evidence.

**How the records communicate**
1. When an implementation task changes, update its checkbox here. Update Part 16 only when the phase-level delivery summary or an Owner decision is affected.
2. When acceptance evidence changes, update the relevant Part 17 test record. Do not mark an implementation checkbox complete solely because an automated test passed.
3. Use Part 16 decision IDs (for example, `D-001`) in relevant Part 17 test records. Keep the full decision wording only in Part 16.
4. Where a tracker task and acceptance test concern the same feature, cross-reference the exact task wording and test ID; do not copy one status into the other.
5. If records disagree, preserve each record's own meaning and reconcile against its authority: task completion from this tracker, Owner decisions from Part 16, and test outcomes from Part 17. Do not silently overwrite evidence or infer a PASS.
6. Keep the Master Technical Blueprint and AI Blueprint governing. This connection protocol does not authorize changing either blueprint.

## Phase 1: The Watcher (Cloudflare Worker)
- [x] Initialize `watcher-bot/` directory and `wrangler.toml` config
- [x] Implement standard 1-minute cron check against approved official PRC/CSC sources (PRC monitored; CSC safely paused pending compliant access)
- [x] Implement Peak Week Mode (Cloudflare KV check, 30-sec loop)
- [x] Add Preemptive Strike logic (template-based HEAD requests; production URL templates remain empty until officially verified)
- [x] Configure `repository_dispatch` Webhook to wake GitHub Actions (receiver validation workflow configured; genuine production dispatch acceptance still pending)
- [x] Owner-approved phase transition: defer genuine PRC production acceptance until the official result release is available; live production acceptance remains unverified and must be revisited during final acceptance.

## Phase 2: The Extractor & Greenlight (Python & GitOps)
- [x] Build Python `extractor/` using `pdfplumber` and `pandas` (raw text/table extraction; explicit mapping-based normalization is tracked separately; OCR is not implemented)
- [x] Implement Part 20 Official-First Policy (persist official-attempt evidence before fallback; block fallback on authentication/CAPTCHA; same-origin PDF acquisition is available as an optional method; external Drive links remain manual pending access verification)
- [x] Build `processor/` & Greenlight Protocol (100/0 fail-closed score; count, blanks, duplicates, anomalies, sequence coverage, and two-source fallback agreement)
- [x] Implement Array-of-Arrays JSON builder and sharding logic (each data shard strictly below 10 MiB; Greenlight fingerprint required)
- [x] Integrate the GitOps Manager with the processing workflow so a 100/100 Greenlight batch opens a PR and auto-merges only after all GitHub checks pass (reviewed-batch workflow and Python entry point merged in PRs #48 and #50; exact-commit CI dispatch and fail-closed merge; live result publication remains for final acceptance)
- [x] Add explicit, reviewed PDF table-to-record normalization and connect it to Greenlight (PR #51 merged; 98 Python tests passed; mapping-driven, preserves sequence strings, never guesses or renumbers; real official PDF layout validation remains pending)
- [x] Integrate bounded same-origin official PDF acquisition into the Python pipeline with robots.txt checks, article-link verification, PDF signature checks, and persisted HEAD/GET evidence (PR #52 merged; 104 Python tests passed; external Drive links remain manual-drop until public access policy is verified)
- [x] Identify and validate a compliant **PRC-only** official-content access path that yields passer names and their exact sequence numbers; PDF download is not required. CSC-specific source discovery, portal access, acquisition, extraction, and testing are excluded by Owner decision D-003. PRC owner-reviewed manual handoff is implemented (PR #53 merged; PR #54 merged to preserve each actual exam identifier when using the general PRC homepage source). Owner supplied a readable image of official PRC March 2026 LEPT Elementary page 2/369; 50 passer names and exact sequence numbers (1–50) were extracted and visually checked. This validates the content-first manual handoff route for a representative official page sample; it does not establish complete-release acquisition.
- [x] Validate the extraction/normalization mapping against a representative **PRC** official result-content sample (page, portal data, embedded dataset, CSV, or PDF) and prove exact passer-name/sequence-number pairs; PDF is optional. Regression test `python-engine/tests/test_prc_page_sample.py` validates all 50 page-2 pairs through the explicit sequence/name column mapping and Greenlight (100/100, zero missing sequences); PR #56 merged after CI run #119 passed. This is a representative-page mapping test, not full PDF/OCR parser or full-release validation. CSC-specific validation is excluded by D-003.
- [x] Implement reusable bounded public-preview page-shard capture and merge verification (configurable 1–16 parallel shards, visible-UI-only capture, exact page coverage, SHA-256 checks, and immediate stop on access challenges; 8 local regression tests pass; first live run through the reusable workflow remains pending).

**Final acceptance work deferred by Owner decision D-005:** The real publicly released PRC batch must still complete acquisition, extraction, Greenlight, dataset generation, GitOps PR, CI, and merge. It is retained as a Phase 5 final Live Acceptance task rather than run during implementation.

## Phase 3: Automated Broadcasting
- [x] Implement `broadcaster.py` with Facebook Graph API and Telegram Bot API adapters, credential validation, and safe error handling (PR #96 merged; 11 focused tests included; full GitHub CI passed with 147 Python tests)
- [x] Implement post-deployment trigger: announcements only after successful Cloudflare Pages deployment and only when a result manifest changed (PR #96 merged; awaits Phase 4 workflow named `Deploy Cloudflare Pages`)
- [x] Implement durable broadcast idempotency ledger and fail-closed handling for uncertain delivery outcomes (PR #96 merged; ledger stored on a separate automation branch)
- [ ] Configure Facebook and Telegram credentials and verify real provider delivery during final Live Acceptance (no credentials or live provider calls during implementation)

## Phase 4: Frontend Web Worker Search
- [ ] Build static HTML/CSS UI (including Peak Week "Preparing Mode" UI)
- [ ] Implement `storage.js` for IndexedDB dataset caching
- [ ] Implement `search.js` (Web Worker) to search 50,000+ array records without freezing UI
- [ ] Configure Cloudflare Pages deployment via `.github/workflows/deploy-pages.yml`
- [ ] Build an Owner-facing website review experience for official preview evidence and extracted name/sequence records before publication, while keeping the public search route read-only (deferred by D-004).

## Phase 5: Final Live Acceptance & Security
- [ ] Run the deferred real, publicly released **PRC** result batch through acquisition, extraction, Greenlight, dataset generation, GitOps PR, CI, and merge (deferred from Phase 2 by D-005; CSC testing excluded by D-003)
- [ ] Verify real Facebook Graph API and Telegram Bot API delivery using Owner-configured credentials
- [ ] Run Dummy Test: Drop PDF, verify Watcher detects in <30s and wakes Worker
- [ ] Run Safety Test: Feed a broken PDF (missing sequence numbers) to verify Greenlight Protocol aborts auto-merge
- [ ] Verify no secrets are exposed in public code or frontend
- [ ] Test the `/manual-drop/` GitHub override workflow
- [ ] Conduct comprehensive cross-phase Live Acceptance covering monitoring, extraction, Greenlight, GitOps, Pages deployment, search, broadcasting, failure handling, and rollback
