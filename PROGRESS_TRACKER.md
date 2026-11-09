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
- [x] Implement official PRC future-release schedule discovery in the Watcher (official schedule-index discovery, runtime robots.txt compliance, bounded HTML extraction, nearest upcoming target-date calculation using the Manila calendar, six-hour KV cache, and read-only JSON endpoint; PR #146–#148 merged and production Worker deployed as version `6e376b6a-115c-43eb-b5d0-6992cc985981`; Owner supplied post-deployment live API response dated 2026-11-07T22:46:14.830Z showing `ok:true`, fresh `access_policy.outcome:"allowed"`, 22 upcoming exact exam-name/date pairs after deduplication, `unparsed_count:0`, and nearest target date Veterinarians (CBLE) on 2026-11-10; P1-11 technical live verification satisfied. Robots.txt allowance is recorded, but is not formal legal authorization or a substitute for any PRC terms/reuse permission that may apply.)
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
- [x] Integrate the GitOps Manager with the processing workflow so a 100/100 Greenlight batch opens a PR and auto-merges only after all GitHub checks pass (reviewed-batch workflow and Python entry point merged in PRs #48 and #50; exact-commit CI dispatch and fail-closed merge; the Owner's D-008 one-month trial authorizes real publication only for explicitly pre-approved auto-publish exams)
- [x] Add explicit, reviewed PDF table-to-record normalization and connect it to Greenlight (PR #51 merged; 98 Python tests passed; mapping-driven, preserves sequence strings, never guesses or renumbers; real official PDF layout validation remains pending)
- [x] Integrate bounded same-origin official PDF acquisition into the Python pipeline with robots.txt checks, article-link verification, PDF signature checks, and persisted HEAD/GET evidence (PR #52 merged; 104 Python tests passed; external Drive links remain manual-drop until public access policy is verified)
- [x] Identify and validate a compliant **PRC-only** official-content access path that yields passer names and their exact sequence numbers; PDF download is not required. CSC-specific source discovery, portal access, acquisition, extraction, and testing are excluded by Owner decision D-003. PRC owner-reviewed manual handoff is implemented (PR #53 merged; PR #54 merged to preserve each actual exam identifier when using the general PRC homepage source). Owner supplied a readable image of official PRC March 2026 LEPT Elementary page 2/369; 50 passer names and exact sequence numbers (1–50) were extracted and visually checked. This validates the content-first manual handoff route for a representative official page sample; it does not establish complete-release acquisition.
- [x] Validate the extraction/normalization mapping against a representative **PRC** official result-content sample (page, portal data, embedded dataset, CSV, or PDF) and prove exact passer-name/sequence-number pairs; PDF is optional. Regression test `python-engine/tests/test_prc_page_sample.py` validates all 50 page-2 pairs through the explicit sequence/name column mapping and Greenlight (100/100, zero missing sequences); PR #56 merged after CI run #119 passed. This is a representative-page mapping test, not full PDF/OCR parser or full-release validation. CSC-specific validation is excluded by D-003.
- [x] Integrate the reusable public-preview capture into the PRC acquisition and Greenlight pipeline for configured official PRC source/exam mappings (ordinary visible-UI capture, per-page PNG/text/hash evidence, reviewed mappings, exact count/sequence/duplicate validation, and conditional Playwright/Chromium setup; CPALE 2026 passed local capture, Greenlight, and dataset generation).
- [x] Enable D-009 source-wide automatic publication for every configured PRC source/exam mapping that passes Greenlight and exact-head CI; hold mismatches, unsupported/unreviewed mappings, access failures, and uncertain results (PR #101 merged; main-branch CI passed; no post-activation live release has completed yet).
- [ ] Implement D-007 Tier 3 static PNG + OCR fallback under D-013: enable it PRC-wide for every official examination result whose content is publicly viewable (downloadable or not), and disable it only when content is neither publicly viewable nor downloadable. Extract only passer names and official sequence numbers. Retain reviewed source/exam extraction mappings, 95% minimum token confidence, screenshot/OCR SHA-256 evidence, exact announced-count/sequence coverage, zero duplicate checks, and Greenlight 100%; respect applicable law, published access policies, robots directives, rate limits, and access controls, and do not implement video/frame OCR in production. (Core fail-closed engine merged in PRs #108/#109 and synthetic CI passed; remains incomplete because no OCR mapping is configured and P2-29 is NOT RUN.)

**D-008/D-009 automated trial (2026-11-06 through 2026-12-06):** PR #101 is merged and source-wide auto-publication is active for configured, authorized PRC mappings that pass every automated check. D-005's blanket deferral and D-008's CPALE-only restriction are superseded for this trial. Source authorization, terms/access, reviewed mapping, count/sequence/name validation, Greenlight, and exact-head CI remain mandatory. Unsupported or failed candidates must be held without publication. LEPT Secondary still needs configured source/mapping before it is eligible. Record real detection-to-publication outcomes and downtime; the full post-merge path has not yet been observed.

## Phase 3: Automated Broadcasting
- [x] Implement `broadcaster.py` with Facebook Graph API and Telegram Bot API adapters, credential validation, and safe error handling (PR #96 merged; 11 focused tests included; full GitHub CI passed with 147 Python tests)
- [x] Implement post-deployment trigger: announcements only after successful Cloudflare Pages deployment and only when a result manifest changed (PR #96 and Pages workflow in PR #98 merged; live provider delivery still requires Owner credentials and destination approval)
- [x] Implement durable broadcast idempotency ledger and fail-closed handling for uncertain delivery outcomes (PR #96 merged; ledger stored on a separate automation branch)
- [ ] Configure Facebook and Telegram credentials and verify real provider delivery during final Live Acceptance (no credentials or live provider calls during implementation)

## Phase 4: Frontend Web Worker Search
- [x] Build static HTML/CSS UI (including Peak Week "Preparing Mode" UI) (deployed through PR #98; public URL and routes return HTTP 200)
- [x] Implement `storage.js` for IndexedDB dataset caching (repeat-session cache reuse verified; full offline reload is not supported)
- [x] Implement `search.js` (Web Worker) to search 50,000+ array records without freezing UI (five Chromium worker searches completed with zero observed >50 ms frame gaps)
- [x] Configure Cloudflare Pages deployment via `.github/workflows/deploy-pages.yml` (PR #98 merged; production Pages deployment succeeded)
- [x] Build an Owner-facing website review experience for official preview evidence and extracted name/sequence records, while keeping the public search route read-only (local-only, exact-hash receipt; D-009 makes this supplemental for batches passing all automated checks)
- [ ] Complete production acceptance of the single-domain Owner Activity Dashboard at `/owner/` on the public Cloudflare Pages origin under Owner decision D-012 (P4-15–P4-18; implementation merged in PR #160 at `9687aec521667f87c23a09d3d0dead1bf3624f0f`; a subsequent main-branch Pages deployment succeeded in workflow run [#42510141003](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/actions/runs/42510141003), including production-variable/secret-type preflight, deployment, same-origin auth readiness, and unauthenticated `/owner/` protection smoke check; automated CI tests passed. This does not complete live acceptance: real Owner sign-in and Firestore authorization, authenticated D1 activity/analytics reads, CSRF logout/replay rejection, signed-out public-search walkthrough, desktop/mobile walkthrough, and rollback acceptance remain outstanding. Keep the private Pages project available as rollback until acceptance passes; do not delete/disconnect it without further Owner approval.)

## Phase 5: Final Live Acceptance & Security
- [ ] Run an eligible PRC release through Watcher detection, capture, Greenlight, GitOps PR, exact-head CI/merge, and Pages deployment under the D-008/D-009 one-month trial (configured sources only; CSC excluded by D-003)
- [ ] Complete the Owner's one-month real-world website and automation trial; record search accuracy, release-to-publication behavior, failures, and downtime
- [ ] Verify real Facebook Graph API and Telegram Bot API delivery using Owner-configured credentials
- [ ] Run Dummy Test: Drop PDF, verify Watcher detects in <30s and wakes Worker
- [ ] Run Safety Test: Feed a broken PDF (missing sequence numbers) to verify Greenlight Protocol aborts auto-merge
- [ ] Verify no secrets are exposed in public code or frontend
- [ ] Test the `/manual-drop/` GitHub override workflow
- [ ] Conduct comprehensive cross-phase Live Acceptance covering monitoring, extraction, Greenlight, GitOps, Pages deployment, search, broadcasting, failure handling, and rollback
