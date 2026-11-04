# PART 17 — LIVE ACCEPTANCE TEST REGISTER

## PH-EXAM-RESULTS

> **Document role:** Phase-by-phase acceptance criteria, observed results, and supporting evidence.
>
> **Companion documents:** Part 16, `IMPLEMENTATION_ROADMAP.md`, summarizes delivery status. `PROGRESS_TRACKER.md` is the operational task checklist.
>
> **Reading guide:** Each test is presented as a compact record with its pass condition, evidence to retain, and current status. The Master Technical Blueprint remains the governing architecture.

---

## Contents

1. [Acceptance rules that apply to every phase](#1-acceptance-rules-that-apply-to-every-phase)
2. [Phase 1 — The Watcher](#2-phase-1--the-watcher-cloudflare-worker)
3. [Phase 2 — The Extractor & Greenlight](#3-phase-2--the-extractor--greenlight-python-and-gitops)
4. [Phase 3 — Automated Broadcasting](#4-phase-3--automated-broadcasting)
5. [Phase 4 — Frontend Web Worker Search](#5-phase-4--frontend-web-worker-search)
6. [Phase 5 — End-to-End Simulation & Security](#6-phase-5--end-to-end-simulation--security)
7. [The three required acceptance criteria](#7-part-17--the-three-required-acceptance-criteria)
8. [Live test record template](#8-live-test-record-template)

---

**Purpose:** The Part 17 companion document: a phase-by-phase register of current acceptance-test criteria, results, and evidence. The core architecture is in `Master_Technical_Blueprint.md`; implementation roadmap and delivery status are in `IMPLEMENTATION_ROADMAP.md` (Part 16).

**Important:** This document records the current strongest evidence and acceptance status. A successful unit test or synthetic event is not automatically a live acceptance PASS. A completed implementation checkbox in `PROGRESS_TRACKER.md` is not, by itself, proof of live acceptance.

---


## Cross-document references and communication

This register is connected to, but is not a duplicate of, the implementation checklist and roadmap:

- **Implementation task status:** [`PROGRESS_TRACKER.md`](PROGRESS_TRACKER.md) owns the task checkboxes and identifies the next unchecked task.
- **Phase context and Owner decisions:** [Part 16 — `IMPLEMENTATION_ROADMAP.md`](IMPLEMENTATION_ROADMAP.md) owns the phase-level delivery summary and full Owner decision register.
- **Acceptance evidence:** This Part 17 register owns test pass conditions, actual outcomes, and evidence.

**Linking rules**
1. Each test ID (such as `P2-03`) identifies an acceptance check. Where useful, its record should name the related tracker task by its exact checklist wording.
2. Add the relevant Part 16 Owner decision ID(s) to affected test records. Do not duplicate or redefine the full decision in this file.
3. Keep test status based on the stated pass condition and recorded evidence. A tracker checkbox marked complete is not proof of acceptance; an automated PASS is not automatically live acceptance.
4. When evidence changes, update the affected test record here and communicate the resulting implementation impact to the tracker/Part 16 only where their own records need to change.
5. Do not make statuses identical merely for consistency. A task can be implemented while its live acceptance test remains BLOCKED or PARTIAL.
6. If a pass condition appears to conflict with an Owner decision, consult the authoritative decision in Part 16. Do not silently change acceptance criteria; record any new Owner direction as a new decision there.

## 1. Acceptance rules that apply to every phase

- **Official first:** For the current Phase 2 acquisition and validation work, attempt PRC official announcements and their linked result destinations before any third-party fallback (Part 20). CSC-specific testing is excluded by Owner decision D-003; this does not delete CSC support from the architecture.
- **Content first:** The required result is each passer's exact name paired with the official sequence number. A downloadable PDF is optional; an accessible official webpage, portal response, embedded dataset, CSV, or other readable official format is acceptable (Part 21).
- **No access circumvention:** Never bypass authentication, CAPTCHA/Turnstile, MFA, permissions, robots.txt, rate limits, or other access restrictions. Stop automation and use an authorized manual handoff/review route when required (Parts 18, 20, 21).
- **Greenlight is fail-closed:** No unverified batch may be published or auto-merged. A failed validation must preserve the last known-good public dataset (Parts 5, 12, 20).
- **Free-only architecture:** Tests must not introduce paid services, paid APIs, or a server that violates the $0/static-first architecture (Parts 1, 14, 19).
- **Evidence:** Record the test ID, date/time, environment, input/source, observed result, logs or run/commit/PR URL, and PASS/FAIL/BLOCKED. Do not record secrets, cookies, or unnecessary personal data.

### Owner decisions linked to acceptance tests

Owner decisions that affect a task, source, test scope, or pass condition are recorded in the **Owner decision register in Part 16**. That register is the single authoritative record, so full decision wording is not duplicated here.

For each affected test or test execution:
- Include the relevant decision ID (for example, `D-001`) in the test record.
- Apply the decision only within its stated scope. A decision to skip one source path must not be interpreted as excluding an entire authority or all of its sources.
- Do not treat a decision to defer or skip a source as a test PASS. Keep the test status based on its actual pass condition and evidence.
- If an Owner decision changes an acceptance condition, record the new decision in Part 16 first; do not silently rewrite the test's pass condition or the Master Technical Blueprint.

**Currently applicable decisions**
- `D-001` — Phase 2 content-first requirement: capture exact passer-name/sequence-number pairs; PDF download is optional.
- `D-002` — Earlier Phase 2 CSC source-path decision; superseded for testing scope by D-003.
- `D-003` — Exclude all CSC-specific testing; current Phase 2 source validation is PRC-only.

### Status legend

- `NOT RUN` — no relevant test evidence has been recorded.
- `AUTOMATED PASS` — automated/unit/regression test passed; live acceptance is not implied.
- `PARTIAL` — some required behavior was verified, but the complete pass condition was not demonstrated.
- `PASS` — the complete stated acceptance condition was demonstrated in the required environment.
- `FAIL` — test ran and did not meet its pass condition.
- `BLOCKED` — a required live test cannot currently be completed because an external prerequisite or authorized source is unavailable.
- `N/A` — only where the test genuinely does not apply; explain why.

---

## 2. Phase 1 — The Watcher (Cloudflare Worker)

**Blueprint basis:** Parts 2, 9, and 11; see also `IMPLEMENTATION_ROADMAP.md` (Part 16).

#### P1-01 — Scheduled monitoring

- **Pass condition:** The Watcher runs on the configured one-minute cron schedule.
- **Evidence to retain:** Production cron `* * * * *`; successful scheduled Worker event at 2026-11-03 22:51:14 UTC; see Phase 1 audit §12.
- **Status:** `PASS`

#### P1-02 — Standard mode

- **Pass condition:** Outside Peak Week, one normal source fetch is performed and the invocation terminates.
- **Evidence to retain:** PR #18 production tail recorded cron outcome `ok`, no exceptions, standard mode; see PR #18 and Phase 1 audit §1.
- **Status:** `PASS`

#### P1-03 — Peak Week activation

- **Pass condition:** Peak Week starts exactly seven days before the historically predicted D1 release date, or when manually activated by the Owner.
- **Evidence to retain:** Prediction/activation record and KV value.
- **Status:** `NOT RUN`

#### P1-04 — Peak Week KV flag

- **Pass condition:** The Watcher reads the `PEAK_WEEK` flag from Cloudflare KV and selects the correct mode.
- **Evidence to retain:** Production KV diagnostics observed `PEAK_WEEK=true`; subsequent PR #32 live event performed two Peak Week scans. KV-read/branch selection has live evidence; retain raw invocation record for full audit.
- **Status:** `PARTIAL`

#### P1-05 — Peak Week 30-second loop

- **Pass condition:** In Peak Week, the Watcher performs its first check, waits 30 seconds, and performs the second check.
- **Evidence to retain:** PR #18 automated Peak Week simulation passed the 30-second wait/two-scan behavior. PR #32 production event reported two scans, but retained audit does not show exact inter-scan timestamps.
- **Status:** `PARTIAL`

#### P1-06 — Preemptive HEAD test

- **Pass condition:** The Watcher identifies a candidate result resource through a lightweight HEAD request before the official HTML announcement page updates. This is the Part 17 Preemptive Test.
- **Evidence to retain:** Synthetic fixture HEAD tests verify code behavior; production `preemptive_url_templates` remain empty. No genuine official result resource was detected before its announcement changed.
- **Status:** `BLOCKED`

#### P1-07 — Change detection

- **Pass condition:** A relevant change at an approved monitored official source is detected.
- **Evidence to retain:** PRC homepage baseline and scheduled unchanged checks were verified live; no newly released official result article/change was observed during the audit window.
- **Status:** `PARTIAL`

#### P1-08 — Webhook dispatch

- **Pass condition:** On a qualifying detection, the Watcher sends the configured `repository_dispatch` event to GitHub Actions.
- **Evidence to retain:** PR #18: two synthetic diagnostic `source-detected` events reached the production receiver and generated validation-only runs. No genuine scheduled production source detection dispatch has been observed.
- **Status:** `PARTIAL`

#### P1-09 — Official-source priority

- **Pass condition:** Monitoring and acquisition handoff begin with the official PRC/CSC source and its linked result destination.
- **Evidence to retain:** PRC homepage is enabled as official baseline/discovery source; CSC Region V remains safely disabled after HTTP 403. Complete PRC/CSC coverage and result-content acquisition remain outstanding; see Phase 1 audit §12.
- **Status:** `PARTIAL`

#### P1-10 — Compliant retrieval behavior

- **Pass condition:** Requests are bounded and low-impact, respect robots.txt/rate limits/access controls, and do not attempt authentication or CAPTCHA circumvention.
- **Evidence to retain:** PRC `robots.txt` returned HTTP 200 and public result article paths were not disallowed; CSC HTTP 403 security verification caused automated polling to be disabled rather than bypassed. See Phase 1 audit §12.
- **Status:** `PASS`

**Phase 1 acceptance note:** The Part 16 roadmap calls for the 30-second loop, Peak Week KV check, preemptive HEAD requests, and webhook dispatch. Part 17 separately requires proof that the preemptive HEAD detection happens before the HTML page updates.

---

## 3. Phase 2 — The Extractor & Greenlight (Python and GitOps)

### Full released-batch evidence — PRC March 2026 LEPT Elementary (2026-11-03)

- **Workflow:** [PRC Official LEPT Elementary Extraction Trial #41663204288](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/actions/runs/41663204288), completed successfully on the isolated integration branch.
- **Artifact:** `prc-official-lept-elementary-2026-evidence`, artifact ID `13244340242` (2,101,465 bytes).
- **Official content:** PRC result article and its linked Google Drive public-preview UI; 368/368 viewer pages navigated. No PDF download, sign-in, CAPTCHA, or access-control bypass.
- **Extraction:** 18,376 exact sequence/name records; announced count 18,376; sequences 1–18,376 complete; zero missing, conflicting, duplicate sequence, duplicate name, out-of-range, blank, or unresolved target records.
- **Independent artifact inspection:** JSONL has 18,376 parseable lines; every sequence is unique and contiguous; all 18,376 sequence/name pairs match the generated Array-of-Arrays shard by sequence key.
- **Greenlight:** 100/100, status `GREENLIGHT`; all five checks true (count, blanks, duplicates, anomalies, sequence coverage). Report explicitly states validation only; it does not publish, merge, or deploy.
- **Dataset:** one shard, 862,332 bytes (below 10 MiB); 18,376 records. Shard SHA-256: `fb3b7086c1de0848977a5ce8601ab5401b15c6df3a0700bb2d30bb86c0d756de`. Canonical records SHA-256: `37cd69173dc25d2792c0602daaa1ff5bcd4e3f87569e2fe4598b14300c01e21e`. Manifest shard hash independently matches the file.
- **Visual evidence:** sequences 10,710 and 15,066 are visible on printed pages 216 and 303; screenshot hashes match across both reports and capture manifest. OCR remains advisory; the first page's OCR did not reproduce the expected name.
- **Publication caution:** the rendered source pages visibly carry a large `DRAFT` watermark. The PRC announcement links this file, but the watermark is a source-quality caveat requiring Owner review before a public dataset PR is merged. Machine report correctly retains `visual_human_review_status: PENDING`; automation does not claim a human review.
- **GitOps attempt:** [run #41665288366](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/actions/runs/41665288366) regenerated the Greenlight-approved dataset and staged it on `data/greenlight-37cd69173dc2` (commit `7c44df77b94f494d6e74bdc46ad547017272cbf1`). PR creation then failed with GitHub API HTTP 403: `GitHub Actions is not permitted to create or approve pull requests.` The repository's Actions setting must be enabled by the Owner. No data PR was opened, no dataset was merged into `main`, and no deployment/publication occurred. The source file's DRAFT watermark also remains an Owner-review caveat before public merge. P2-24 and P2-25 therefore remain `PARTIAL`.


**Blueprint basis:** Parts 3–7, 10, 12, 20, and 21; see also `IMPLEMENTATION_ROADMAP.md` (Part 16).

#### P2-01 — Workflow trigger

- **Pass condition:** GitHub Actions starts the processing workflow from a valid Watcher `repository_dispatch` event or an authorized `manual-drop/` push.
- **Evidence to retain:** PR #18 synthetic production `repository_dispatch` receiver events started successful validation-only runs. `manual-drop/` currently acknowledges only; no real Watcher-originated result event or manual processing run is proven.
- **Status:** `PARTIAL`

#### P2-02 — Official-first acquisition

- **Pass condition:** The pipeline attempts the official announcement and its linked result destination before considering third-party sources.
- **Evidence:** Official-first policy and bounded retrieval are implemented (PRs #48–#52). Run #41663204288 acquired the contents from the PRC article's linked Google Drive ordinary public-preview UI after navigating all 368 viewer pages. No sign-in, CAPTCHA, private endpoint, PDF download, or access-control bypass was used. The separate CSC source remains excluded by Owner decision D-003.
- **Status:** `PASS`

#### P2-03 — Result-content acquisition

- **Pass condition:** The pipeline obtains the actual passer names and their corresponding official sequence numbers from an authorized source.
- **Evidence:** Run #41663204288 captured the official linked public preview and the Python Engine ingested all 18,376 passer-name/sequence-number pairs. The artifact contains 18,376 parseable JSONL records and exact pair preservation through the generated dataset. The ordinary public preview was used without bypassing access controls. CSC source access and testing are excluded by D-003.
- **Status:** `PASS`

#### P2-04 — Content-format flexibility

- **Pass condition:** A readable official webpage, portal response, embedded/public dataset, CSV, or other compliant format can be used; PDF possession is not required.
- **Evidence:** The integrated capture uses the ordinary publicly accessible, JavaScript-rendered Google Drive preview linked by the official PRC article. It traverses 368 viewer pages and captures the cumulative rendered text; no PDF download is required. The full batch passed Python Engine validation. CSC content-format investigation and testing are excluded by D-003.
- **Status:** `PASS`

#### P2-05 — PDF parsing when applicable

- **Pass condition:** When PDF is the practical authorized source, the parser extracts the required records from a representative PDF.
- **Evidence:** The successful run uses the public-preview rendered text path rather than PDF bytes. Unicode extraction produced 18,376 records; Tesseract OCR was advisory only. Screenshot evidence is hash-bound. This validates the selected content-first path, not pdfplumber extraction from original PDF bytes.
- **Status:** `PARTIAL`

#### P2-06 — Text cleaning / OCR handling

- **Pass condition:** Where the chosen input requires cleaning or OCR, the pipeline either produces reviewable records or fails safely; it must not silently invent uncertain values.
- **Evidence to retain:** Sanitized extraction output and warnings/failure report.
- **Evidence:** Run #41663204288 completed public-preview extraction, screenshot capture, hash reconciliation, Python Engine ingestion, and Greenlight. Tesseract remains advisory: it did not reproduce the expected name on the first flagged page. The extraction did not guess or rewrite the two flagged strings; both are visible in the captured rendered screenshots. Human visual-review status remains PENDING.
- **Status:** `PASS`

#### P2-07 — Normalization integrity

- **Pass condition:** Name normalization does not change a person's identity or merge distinct records.
- **Evidence:** The full output preserves every source name and sequence pair exactly. Independent artifact inspection compared all 18,376 records by sequence key between source JSONL and generated Array-of-Arrays output; there were zero pair mismatches. No name rewriting or sequence renumbering occurred.
- **Status:** `PASS`

#### P2-08 — Sequence preservation

- **Pass condition:** Every output record retains its exact source sequence value; no inferred or silently renumbered sequence is accepted.
- **Evidence to retain:** PR #56 / merged test `test_prc_page_sample.py` compares all 50 normalized output pairs to the source-page transcription; sequence strings 1–50 are preserved exactly and Greenlight confirms complete sample coverage.
- **Status:** `PASS`

#### P2-09 — Announced count match

- **Pass condition:** Extracted record count equals the authority-announced passer count.
- **Evidence to retain:** Announced count and computed count in validation report.
- **Evidence:** Integrated validation report from run #41663204288: 18,376 extracted / 18,376 announced; `count_match=true`; Greenlight 100/100.
- **Status:** `PASS`

#### P2-10 — Zero blank names

- **Pass condition:** No record has an empty passer-name field.
- **Evidence:** Full-batch validation report: 18,376 records, `blank_record_count=0`, `zero_blanks=true`; independent JSONL inspection also found zero blank names.
- **Status:** `PASS`

#### P2-11 — Zero duplicates

- **Pass condition:** No exact duplicate passer names or sequence numbers remain.
- **Evidence:** Full-batch validation report: zero duplicate names and duplicate sequence numbers; independent inspection found 18,376 unique sequence values and 18,376 unique names.
- **Status:** `PASS`

#### P2-12 — Zero unresolved anomalies

- **Pass condition:** No unexpected/unparseable characters or unresolved parsing anomalies remain in a batch proposed for automatic publication.
- **Evidence:** Full-batch validation report: `anomaly_record_count=0`, `zero_anomalies=true`, and `unresolved_target_record_count=0`. The two unusual strings are preserved exactly and visible in hash-matched screenshots. Note the source pages carry a DRAFT watermark; this is a separate publication-quality caveat, not a parser anomaly.
- **Status:** `PASS`

#### P2-13 — Complete sequence coverage

- **Pass condition:** The required official sequence range is complete, with no gaps or extras.
- **Evidence:** Integrated full-batch validation report: `complete_sequence_coverage=true`; 18,376 unique sequences span 1–18,376 with zero missing and zero unexpected values.
- **Status:** `PASS`

#### P2-14 — Fallback pair agreement

- **Pass condition:** Only after the official-first gate is documented as unavailable, two independent owner-approved public sources agree 100% on every exact sequence-number/name pair.
- **Evidence to retain:** Both source references and pair-by-pair comparison report.
- **Status:** `NOT RUN`

#### P2-15 — Official failure evidence

- **Pass condition:** Before fallback, the system records source/article URLs, timestamps, methods, HTTP status, content type, final URL, PDF/signature outcome where relevant, and concise failure reason/classification.
- **Evidence to retain:** Persisted official-attempt evidence record.
- **Status:** `NOT RUN`

#### P2-16 — Provenance

- **Pass condition:** Every import and published dataset is labelled `official_direct` or `third_party_fallback`; fallback is never described as official PDF extraction.
- **Evidence to retain:** Batch metadata, validation report, and dataset provenance.
- **Status:** `PASS`

#### P2-17 — Clean-batch Greenlight

- **Pass condition:** A clean representative batch meeting every Greenlight and applicable Part 20 validation condition receives 100% and is eligible for the automated GitOps path.
- **Evidence:** Runs #41663204288 and #41664546615 each produced the complete 18,376-record batch with Greenlight 100/100 and all five required checks true. Run #41664546615 used the linear-time shard builder; the Python Engine validation/dataset step completed in 5 seconds versus 73 seconds in the prior run, with identical canonical records hash. The later GitOps attempt #41665288366 was blocked at PR creation by repository Actions permissions.
- **Status:** `PASS`

#### P2-18 — Missing-sequence safety test

- **Pass condition:** A test input with missing sequence numbers fails Greenlight and automatic publication/merge is aborted. This is the Part 17 Extraction Safety criterion.
- **Evidence to retain:** **Automated PASS:** PR #55 merged; deterministic extracted-table fixture omits sequence 002; `publish_batch` raises `PipelineError`, GitOps client is not initialized, no manifest is produced, missing sequence is reported. PR CI #41594622630 and main CI #41594733732 passed (112 Python tests). This is not a live official-PDF test.
- **Status:** `AUTOMATED PASS`

#### P2-19 — Messy-data safety

- **Pass condition:** A batch with unresolved anomalies or uncertain records is not auto-published and is routed for Owner review.
- **Evidence to retain:** Validation report and open PR/manual-review evidence.
- **Status:** `NOT RUN`

#### P2-20 — Array-of-Arrays dataset

- **Pass condition:** Valid records are generated in the approved compact JSON structure, including the name and sequence fields and the defined dataset columns.
- **Evidence:** Artifact dataset has columns `name, rating, region, seq`, 18,376 rows, and exact name/sequence pair agreement with source JSONL.
- **Status:** `PASS`

#### P2-21 — Dataset sharding

- **Pass condition:** A dataset exceeding 10 MB is split into the required alphabetic shards; each generated data shard remains strictly below 10 MiB as implemented.
- **Evidence:** This 18,376-record dataset fits in one 862,332-byte shard, strictly below 10 MiB. The partitioner regression suite also exercises multi-shard partitioning and exact byte limits.
- **Status:** `PASS`

#### P2-22 — Manifest and hashes

- **Pass condition:** `manifest.json` routes to the correct datasets/shards and includes cache-busting hashes matching the generated files.
- **Evidence:** Independent SHA-256 of the generated shard matches the manifest: `fb3b7086c1de0848977a5ce8601ab5401b15c6df3a0700bb2d30bb86c0d756de`. Canonical records hash is `37cd69173dc25d2792c0602daaa1ff5bcd4e3f87569e2fe4598b14300c01e21e`.
- **Status:** `PASS`

#### P2-23 — D1 metadata handling

- **Pass condition:** Operational metadata is written through the Cloudflare D1 REST API; no direct SQL driver or public frontend database query is introduced.
- **Evidence to retain:** Sanitized API/workflow evidence and architecture check.
- **Status:** `NOT RUN`

#### P2-24 — GitOps PR creation

- **Pass condition:** Python creates a PR containing the generated dataset and its validation/provenance information.
- **Evidence:** The real dataset branch `data/greenlight-37cd69173dc2` was created and contains the generated shard and manifest. The GitHub Actions job then received HTTP 403 from `POST /pulls`: `GitHub Actions is not permitted to create or approve pull requests.` No PR exists yet. Owner action required: enable the repository setting allowing GitHub Actions to create and approve pull requests.
- **Status:** `PARTIAL`

#### P2-25 — Conditional auto-merge

- **Pass condition:** Only a 100% Greenlight batch can enter auto-merge, and merge occurs only after all required GitHub checks pass.
- **Evidence:** The 100/100 report passed `GitOps.validate_greenlight`, and the data branch was staged. The PR creation permission error stopped execution before PR CI dispatch, exact-commit checks, or merge. The existing exact-commit CI/merge logic remains covered by unit tests but has not yet run against this real dataset PR.
- **Status:** `PARTIAL`

#### P2-26 — Below-100% handling

- **Pass condition:** A score below 100% aborts auto-merge, leaves the PR for manual review, and triggers the configured Owner alert.
- **Evidence to retain:** PR state, score, and sanitized alert evidence.
- **Status:** `NOT RUN`

#### P2-27 — Last-known-good preservation

- **Pass condition:** Acquisition, extraction, comparison, or validation failure leaves the currently published dataset unchanged.
- **Evidence to retain:** Before/after deployed dataset version/hash.
- **Status:** `NOT RUN`

#### P2-28 — Reusable parallel public-preview page capture

- **Pass condition:** A configured set of parallel shards captures contiguous viewer-page ranges; merge verifies every expected page exactly once and rejects gaps, overlaps, missing shards, blank snapshots, or hash mismatches. Access challenges stop automation without retry or bypass.
- **Evidence:** Final live PRC-linked public-preview acceptance run [#41854972189](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/actions/runs/41854972189), sourced from the official PRC March 2026 LEPT Secondary results article, completed 16/16 shards and captured 901/901 pages. The merge verified contiguous exact coverage, nonblank snapshots, per-page SHA-256 values, shard archive hashes, and the merged evidence artifact hash. Capture span was 61.228 seconds (individual shard loops 13.8–30.8 seconds); three bounded in-place page retries occurred and no whole-shard restart was required. The configurable per-page deadline defaults to 15 seconds. This was approximately 21% faster than the earlier exam-specific 77.45-second capture-span baseline, subject to normal GitHub runner scheduling variation. Regression suite [#41854448985](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/actions/runs/41854448985) passed all 10 tests, including fake-viewer tests proving a stuck page is retried in place and an access challenge raises immediately without retry. No PDF was downloaded, no access control was bypassed, no passer records were extracted, and no publication occurred. Human visual review of the DRAFT-watermarked Secondary source remains pending. A separate Python Engine ingestion bridge from the generic page-snapshot manifest to the hash-bound record manifest remains outstanding.
- **Status:** `PASS` for reusable live page capture and merge verification; scoped hardening merged into Winner-Candidate by PR #68. Main remains unchanged. Full Python Engine record-ingestion integration remains a separate open task.

**Related Owner decisions:** `D-001`, `D-002`, `D-003`, and `D-004` in Part 16. D-003 excludes CSC-specific testing; these Phase 2 acceptance checks apply to PRC only. D-004 defers manual visual review of the Secondary candidate to a future website review experience; it does not authorize publication.

**Phase 2 acceptance note:** The active project task is to find and validate a compliant PRC-only official-content access path yielding exact passer-name/sequence-number pairs. A downloadable PDF is not a pass condition. Representative PRC content mapping validation and a real PRC released batch are separate acceptance milestones. CSC-specific tests are excluded by D-003. Manual visual review of the March 2026 LEPT Secondary candidate is deferred under D-004 and remains pending until the future website review experience is implemented and completed; the candidate remains unpublished.

---

## 4. Phase 3 — Automated Broadcasting

**Blueprint basis:** Parts 3, 4, and 19; see also `IMPLEMENTATION_ROADMAP.md` (Part 16).

#### P3-01 — Facebook Graph API connection

- **Pass condition:** The Python broadcaster can use the configured authorized Facebook integration successfully.
- **Evidence to retain:** Sanitized test result; never include tokens.
- **Status:** `NOT RUN`

#### P3-02 — Facebook publication

- **Pass condition:** A test announcement is published successfully to the configured Facebook destination.
- **Evidence to retain:** Published post URL and workflow log.
- **Status:** `NOT RUN`

#### P3-03 — Telegram Bot API connection

- **Pass condition:** The Python broadcaster can use the configured authorized Telegram Bot API integration successfully.
- **Evidence to retain:** Sanitized test result; never include bot tokens.
- **Status:** `NOT RUN`

#### P3-04 — Telegram publication

- **Pass condition:** A test announcement is delivered successfully to the configured Telegram destination.
- **Evidence to retain:** Message/channel reference and workflow log.
- **Status:** `NOT RUN`

#### P3-05 — Publication trigger gate

- **Pass condition:** Public-result broadcasts occur only after the validated dataset PR has merged and the website deployment has succeeded.
- **Evidence to retain:** Merge/deployment timestamps and broadcast event order.
- **Status:** `NOT RUN`

#### P3-06 — Announcement content

- **Pass condition:** The announcement accurately identifies the authority/examination/year and links visitors to the results website.
- **Evidence to retain:** Published test announcement content and URL.
- **Status:** `NOT RUN`

---

## 5. Phase 4 — Frontend Web Worker Search

**Blueprint basis:** Parts 1–3, 7–8, 9, 13, and 15; see also `IMPLEMENTATION_ROADMAP.md` (Part 16).

#### P4-01 — Cloudflare Pages deployment

- **Pass condition:** The static site and its assets deploy successfully from the approved repository workflow.
- **Evidence to retain:** Pages deployment URL and build result.
- **Status:** `NOT RUN`

#### P4-02 — Searching page

- **Pass condition:** The public Searching page loads and preserves the approved design.
- **Evidence to retain:** Live URL and desktop/mobile visual check.
- **Status:** `NOT RUN`

#### P4-03 — Preparing page and status

- **Pass condition:** The site reads generated `status.json` and displays the approved Preparing Mode when the status requires it.
- **Evidence to retain:** Status file and live page evidence.
- **Status:** `NOT RUN`

#### P4-04 — Dataset loading

- **Pass condition:** The frontend loads the appropriate dataset using the manifest for the selected authority, examination, and year.
- **Evidence to retain:** Browser network trace and selected manifest entry.
- **Status:** `NOT RUN`

#### P4-05 — Search fields and result identity

- **Pass condition:** Visitors can search by authority, examination, year, and name; a result shows the passer name with its corresponding sequence number.
- **Evidence to retain:** Live search examples and expected-record comparison.
- **Status:** `NOT RUN`

#### P4-06 — Array-of-Arrays compatibility

- **Pass condition:** The browser correctly reads the approved compact JSON array-of-arrays dataset.
- **Evidence to retain:** Dataset fixture and browser result.
- **Status:** `NOT RUN`

#### P4-07 — Manifest and shard routing

- **Pass condition:** The frontend follows manifest routes and loads the required shard(s) correctly.
- **Evidence to retain:** Manifest, network trace, and search results across shard boundaries.
- **Status:** `NOT RUN`

#### P4-08 — IndexedDB caching

- **Pass condition:** A downloaded dataset is stored in IndexedDB and can be reused on a subsequent search/session as designed.
- **Evidence to retain:** Browser storage inspection and repeat-load evidence.
- **Status:** `NOT RUN`

#### P4-09 — Local cached search

- **Pass condition:** A subsequent search can use the locally cached dataset without requesting the dataset again when cache is valid.
- **Evidence to retain:** Browser network trace and search result.
- **Status:** `NOT RUN`

#### P4-10 — Web Worker offloading

- **Pass condition:** Large search/filter work executes in the browser Web Worker rather than blocking the UI thread.
- **Evidence to retain:** Runtime inspection/performance trace.
- **Status:** `NOT RUN`

#### P4-11 — 50,000-record performance

- **Pass condition:** A 50,000-record dataset is searchable in the browser without dropping UI frames. This is the Part 17 Performance criterion.
- **Evidence to retain:** Reproducible device/browser, dataset, performance trace, and observed UI responsiveness.
- **Status:** `NOT RUN`

#### P4-12 — Zero backend search queries

- **Pass condition:** Searching/filtering does not send search requests to a backend or query D1; data is served as static assets and searched locally.
- **Evidence to retain:** Browser network trace during multiple searches.
- **Status:** `NOT RUN`

#### P4-13 — Public-site read-only security

- **Pass condition:** The public Pages application has no mechanism or exposed credential that can write to internal data or repositories.
- **Evidence to retain:** Source/configuration review and browser inspection.
- **Status:** `NOT RUN`

#### P4-14 — Owner-facing source and record review

- **Pass condition:** An Owner-facing website review experience lets the Owner inspect official preview evidence alongside extracted name/sequence records and record a review outcome before publication. The public search route remains read-only and exposes no write credentials or internal controls.
- **Evidence to retain:** Review-interface walkthrough, source/evidence references, review outcome and audit record, plus a test proving publication remains blocked until the required review gate is satisfied.
- **Status:** `NOT RUN`

---

## 6. Phase 5 — End-to-End Simulation & Security

**Blueprint basis:** Parts 1–3, 5, 9–13, 16–19, and 20–21.

#### P5-01 — End-to-end dummy result detection

- **Pass condition:** A controlled dummy result resource is detected by the Watcher in under 30 seconds in the specified simulation.
- **Evidence to retain:** Timestamped target availability and Worker detection log.
- **Status:** `NOT RUN`

#### P5-02 — End-to-end webhook handoff

- **Pass condition:** The detected event wakes the GitHub Actions processing workflow.
- **Evidence to retain:** Dispatch event and Actions run URL.
- **Status:** `NOT RUN`

#### P5-03 — End-to-end Python processing

- **Pass condition:** Python acquires the authorized test content, extracts the exact name/sequence pairs, and validates the batch.
- **Evidence to retain:** Workflow log, generated records, and validation report.
- **Status:** `NOT RUN`

#### P5-04 — End-to-end clean Greenlight

- **Pass condition:** A clean dummy batch reaches 100% Greenlight.
- **Evidence to retain:** Full validation report.
- **Status:** `NOT RUN`

#### P5-05 — End-to-end GitOps merge

- **Pass condition:** The clean batch PR passes all required checks and auto-merges under the 100% rule.
- **Evidence to retain:** PR, checks, and merge commit.
- **Status:** `NOT RUN`

#### P5-06 — End-to-end broadcasting

- **Pass condition:** After merge/deployment, the configured Facebook and Telegram announcements are sent.
- **Evidence to retain:** Deployment and message/post references with timestamps.
- **Status:** `NOT RUN`

#### P5-07 — End-to-end deployment and search

- **Pass condition:** The dataset is deployed to Pages and a visitor can search for a test passer and see the correct sequence number.
- **Evidence to retain:** Pages deployment and live search evidence.
- **Status:** `NOT RUN`

#### P5-08 — Broken-input safety

- **Pass condition:** A broken test input missing sequence numbers fails Greenlight and does not auto-merge or replace the public dataset.
- **Evidence to retain:** Failed run, PR state, and unchanged public dataset hash.
- **Status:** `NOT RUN`

#### P5-09 — CAPTCHA / human-verification stop

- **Pass condition:** When an official source presents CAPTCHA or another human-verification barrier, automated retrieval stops; no bypass is attempted.
- **Evidence to retain:** PRC proxy/browser verification response was rejected as a source. No bypass attempted. PRC manual processing route remains incomplete. CSC-specific testing and evidence collection are excluded by Owner decision D-003.
- **Status:** `PARTIAL`

#### P5-10 — Manual-drop override

- **Pass condition:** An Owner-authorized manual content/file handoff in `/manual-drop/` triggers the processing workflow and still undergoes Greenlight validation.
- **Evidence to retain:** Commit/run URL and validation report.
- **Status:** `NOT RUN`

#### P5-11 — Secret protection

- **Pass condition:** No API tokens, credentials, or private operational identifiers are exposed in public source code or frontend assets.
- **Evidence to retain:** Secret scan and source/build inspection.
- **Status:** `NOT RUN`

#### P5-12 — Worker secret storage

- **Pass condition:** The Watcher's GitHub credential is stored as a Cloudflare Worker secret, not in source code.
- **Evidence to retain:** Sanitized configuration/deployment evidence.
- **Status:** `NOT RUN`

#### P5-13 — GitHub Actions secret storage

- **Pass condition:** Required deployment credentials are stored in GitHub Actions Secrets, not committed to the repository.
- **Evidence to retain:** Workflow configuration review and secret-scan evidence.
- **Status:** `NOT RUN`

#### P5-14 — Rollback

- **Pass condition:** Reverting a problematic published merge restores the previous working Pages dataset/site within the blueprint's three-minute target.
- **Evidence to retain:** Revert commit, Pages deployment timestamps, and restored dataset check.
- **Status:** `NOT RUN`

#### P5-15 — Logging and recovery

- **Pass condition:** Important acquisition, processing, validation, publication, and failure paths produce sufficient logs and recover without corrupting the last known-good result.
- **Evidence to retain:** Run logs and controlled failure/recovery evidence.
- **Status:** `NOT RUN`

#### P5-16 — Free-only operation

- **Pass condition:** The end-to-end design operates within the approved free-service architecture and introduces no paid dependency.
- **Evidence to retain:** Service configuration and usage evidence.
- **Status:** `NOT RUN`

---

## 7. Part 17 — The three required acceptance criteria

These are the three required acceptance criteria for this Part 17 register. The other phase checks above are derived from the Part 16 roadmap and the governing requirements in the other blueprint parts.

1. **Extraction Safety — P2-18 / P5-08:** Greenlight fails on a test input missing sequence numbers; automatic publication/merge aborts.
2. **Performance — P4-11:** A 50,000-record dataset is searchable in the browser without dropping UI frames.
3. **Preemptive Test — P1-06:** The Watcher identifies a result PDF/resource through HEAD before the official HTML page updates. The project’s content-first rule means PDF downloadability itself is not required; this test checks the blueprint's preemptive HEAD behavior, not a requirement to possess a PDF.

---

## 8. Live test record template

Copy this block for each test execution:

```text
Related Owner decision ID(s):
Related Progress Tracker task(s):
Test ID:
Date/time (include timezone):
Environment:
Source/input:
Steps performed:
Expected result:
Actual result:
Status: PASS / FAIL / BLOCKED / N/A
Evidence URL(s) (Actions run, Worker logs, PR, commit, Pages URL, or test report):
Failure reason / notes:
Verified by:
```

---

**Related roadmap:** [Part 16 — Implementation Roadmap & Delivery Status](IMPLEMENTATION_ROADMAP.md) · **Operational checklist:** [Progress Tracker](PROGRESS_TRACKER.md)
