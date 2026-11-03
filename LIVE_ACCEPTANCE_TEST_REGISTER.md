# LIVE ACCEPTANCE TEST REGISTER
## PH-EXAM-RESULTS

**Purpose:** A single, phase-by-phase register of live acceptance tests derived from `Master_Technical_Blueprint.md` (Parts 1–21), with the implementation roadmap in Part 16 and the three expressly named acceptance criteria in Part 17 kept distinguishable.

**Important:** This document separates historical automated evidence, production/live verification, and formal acceptance. A successful unit test or synthetic event is not automatically a live acceptance PASS. A completed implementation checkbox in `PROGRESS_TRACKER.md` is not, by itself, proof of live acceptance.

---

## 1. Acceptance rules that apply to every phase

- **Official first:** Attempt the official PRC/CSC announcement and its linked result destination before any third-party fallback (Part 20).
- **Content first:** The required result is each passer's exact name paired with the official sequence number. A downloadable PDF is optional; an accessible official webpage, portal response, embedded dataset, CSV, or other readable official format is acceptable (Part 21).
- **No access circumvention:** Never bypass authentication, CAPTCHA/Turnstile, MFA, permissions, robots.txt, rate limits, or other access restrictions. Stop automation and use an authorized manual handoff/review route when required (Parts 18, 20, 21).
- **Greenlight is fail-closed:** No unverified batch may be published or auto-merged. A failed validation must preserve the last known-good public dataset (Parts 5, 12, 20).
- **Free-only architecture:** Tests must not introduce paid services, paid APIs, or a server that violates the $0/static-first architecture (Parts 1, 14, 19).
- **Evidence:** Record the test ID, date/time, environment, input/source, observed result, logs or run/commit/PR URL, and PASS/FAIL/BLOCKED. Do not record secrets, cookies, or unnecessary personal data.

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

**Blueprint basis:** Parts 2, 9, 11, 16, and 17.

| ID | Live acceptance test | Pass condition | Evidence to retain | Status |
|---|---|---|---|---|
| P1-01 | Scheduled monitoring | The Watcher runs on the configured one-minute cron schedule. | Production cron `* * * * *`; successful scheduled Worker event at 2026-11-03 22:51:14 UTC; see Phase 1 audit §12. | PASS |
| P1-02 | Standard mode | Outside Peak Week, one normal source fetch is performed and the invocation terminates. | PR #18 production tail recorded cron outcome `ok`, no exceptions, standard mode; see PR #18 and Phase 1 audit §1. | PASS |
| P1-03 | Peak Week activation | Peak Week starts exactly seven days before the historically predicted D1 release date, or when manually activated by the Owner. | Prediction/activation record and KV value. | NOT RUN |
| P1-04 | Peak Week KV flag | The Watcher reads the `PEAK_WEEK` flag from Cloudflare KV and selects the correct mode. | Production KV diagnostics observed `PEAK_WEEK=true`; subsequent PR #32 live event performed two Peak Week scans. KV-read/branch selection has live evidence; retain raw invocation record for full audit. | PARTIAL |
| P1-05 | Peak Week 30-second loop | In Peak Week, the Watcher performs its first check, waits 30 seconds, and performs the second check. | PR #18 automated Peak Week simulation passed the 30-second wait/two-scan behavior. PR #32 production event reported two scans, but retained audit does not show exact inter-scan timestamps. | PARTIAL |
| P1-06 | Preemptive HEAD test | The Watcher identifies a candidate result resource through a lightweight HEAD request before the official HTML announcement page updates. This is the explicit Part 17 Preemptive Test. | Synthetic fixture HEAD tests verify code behavior; production `preemptive_url_templates` remain empty. No genuine official result resource was detected before its announcement changed. | BLOCKED |
| P1-07 | Change detection | A relevant change at an approved monitored official source is detected. | PRC homepage baseline and scheduled unchanged checks were verified live; no newly released official result article/change was observed during the audit window. | PARTIAL |
| P1-08 | Webhook dispatch | On a qualifying detection, the Watcher sends the configured `repository_dispatch` event to GitHub Actions. | PR #18: two synthetic diagnostic `source-detected` events reached the production receiver and generated validation-only runs. No genuine scheduled production source detection dispatch has been observed. | PARTIAL |
| P1-09 | Official-source priority | Monitoring and acquisition handoff begin with the official PRC/CSC source and its linked result destination. | PRC homepage is enabled as official baseline/discovery source; CSC Region V remains safely disabled after HTTP 403. Complete PRC/CSC coverage and result-content acquisition remain outstanding; see Phase 1 audit §12. | PARTIAL |
| P1-10 | Compliant retrieval behavior | Requests are bounded and low-impact, respect robots.txt/rate limits/access controls, and do not attempt authentication or CAPTCHA circumvention. | PRC `robots.txt` returned HTTP 200 and public result article paths were not disallowed; CSC HTTP 403 security verification caused automated polling to be disabled rather than bypassed. See Phase 1 audit §12. | PASS |

**Phase 1 acceptance note:** Part 16 explicitly calls for the 30-second loop, Peak Week KV check, preemptive HEAD requests, and webhook dispatch. Part 17 separately requires proof that the preemptive HEAD detection happens before the HTML page updates.

---

## 3. Phase 2 — The Extractor & Greenlight (Python and GitOps)

**Blueprint basis:** Parts 3–7, 10, 12, 16, 17, 20, and 21.

| ID | Live acceptance test | Pass condition | Evidence to retain | Status |
|---|---|---|---|---|
| P2-01 | Workflow trigger | GitHub Actions starts the processing workflow from a valid Watcher `repository_dispatch` event or an authorized `manual-drop/` push. | PR #18 synthetic production `repository_dispatch` receiver events started successful validation-only runs. `manual-drop/` currently acknowledges only; no real Watcher-originated result event or manual processing run is proven. | PARTIAL |
| P2-02 | Official-first acquisition | The pipeline attempts the official announcement and its linked result destination before considering third-party sources. | Official-first policy and bounded official retrieval are implemented and covered by automated tests (PRs #48–#52); actual PRC/CSC linked result contents remain inaccessible/unverified in the inspected live path. | PARTIAL |
| P2-03 | Result-content acquisition | The pipeline obtains the actual passer names and their corresponding official sequence numbers from an authorized source. | No authorized official sample containing actual name/sequence pairs has been acquired; PRC Drive view showed loading/sign-in and CSC access returned HTTP 403. Manual handoff is implemented but awaits Owner-reviewed pairs. | BLOCKED |
| P2-04 | Content-format flexibility | A readable official webpage, portal response, embedded/public dataset, CSV, or other compliant format can be used; PDF possession is not required. | Content-first/manual-handoff architecture is implemented, but no representative official name/sequence content has yet passed through it. | BLOCKED |
| P2-05 | PDF parsing when applicable | When PDF is the practical authorized source, the parser extracts the required records from a representative PDF. | Parser and normalization code have automated fixture/staging coverage (including earlier staging extraction work and PR #51); no representative official PDF layout has been validated. | PARTIAL |
| P2-06 | Text cleaning / OCR handling | Where the chosen input requires cleaning or OCR, the pipeline either produces reviewable records or fails safely; it must not silently invent uncertain values. | Sanitized extraction output and warnings/failure report. | NOT RUN |
| P2-07 | Normalization integrity | Name normalization does not change a person's identity or merge distinct records. | Before/after mapping sample and tests. | NOT RUN |
| P2-08 | Sequence preservation | Every output record retains its exact source sequence value; no inferred or silently renumbered sequence is accepted. | Input/output pair comparison. | NOT RUN |
| P2-09 | Announced count match | Extracted record count equals the authority-announced passer count. | Announced count and computed count in validation report. | NOT RUN |
| P2-10 | Zero blank names | No record has an empty passer-name field. | Greenlight report and test output. | NOT RUN |
| P2-11 | Zero duplicates | No exact duplicate passer names or sequence numbers remain. | Duplicate validation report. | NOT RUN |
| P2-12 | Zero unresolved anomalies | No unexpected/unparseable characters or unresolved parsing anomalies remain in a batch proposed for automatic publication. | Anomaly report and sample review. | NOT RUN |
| P2-13 | Complete sequence coverage | The required official sequence range is complete, with no gaps or extras. | Sequence coverage report. | NOT RUN |
| P2-14 | Fallback pair agreement | Only after the official-first gate is documented as unavailable, two independent owner-approved public sources agree 100% on every exact sequence-number/name pair. | Both source references and pair-by-pair comparison report. | NOT RUN |
| P2-15 | Official failure evidence | Before fallback, the system records source/article URLs, timestamps, methods, HTTP status, content type, final URL, PDF/signature outcome where relevant, and concise failure reason/classification. | Persisted official-attempt evidence record. | NOT RUN |
| P2-16 | Provenance | Every import and published dataset is labelled `official_direct` or `third_party_fallback`; fallback is never described as official PDF extraction. | Batch metadata, validation report, and dataset provenance. | NOT RUN |
| P2-17 | Clean-batch Greenlight | A clean representative batch meeting every Greenlight and applicable Part 20 validation condition receives 100% and is eligible for the automated GitOps path. | Full validation report and test run. | NOT RUN |
| P2-18 | Missing-sequence safety test | A test input with missing sequence numbers fails Greenlight and automatic publication/merge is aborted. This is the explicit Part 17 Extraction Safety criterion. | **Automated PASS:** PR #55 merged; deterministic extracted-table fixture omits sequence 002; `publish_batch` raises `PipelineError`, GitOps client is not initialized, no manifest is produced, missing sequence is reported. PR CI #41594622630 and main CI #41594733732 passed (112 Python tests). This is not a live official-PDF test. | AUTOMATED PASS |
| P2-19 | Messy-data safety | A batch with unresolved anomalies or uncertain records is not auto-published and is routed for Owner review. | Validation report and open PR/manual-review evidence. | NOT RUN |
| P2-20 | Array-of-Arrays dataset | Valid records are generated in the approved compact JSON structure, including the name and sequence fields and the defined dataset columns. | Generated JSON and schema validation. | NOT RUN |
| P2-21 | Dataset sharding | A dataset exceeding 10 MB is split into the required alphabetic shards; each generated data shard remains strictly below 10 MiB as implemented. | File sizes, shard names, and record coverage check. | NOT RUN |
| P2-22 | Manifest and hashes | `manifest.json` routes to the correct datasets/shards and includes cache-busting hashes matching the generated files. | Manifest and independently computed hash comparison. | NOT RUN |
| P2-23 | D1 metadata handling | Operational metadata is written through the Cloudflare D1 REST API; no direct SQL driver or public frontend database query is introduced. | Sanitized API/workflow evidence and architecture check. | NOT RUN |
| P2-24 | GitOps PR creation | Python creates a PR containing the generated dataset and its validation/provenance information. | GitOps integration and PR-generation path are implemented and automated-tested in PRs #48 and #50; no real official-result dataset PR has been created. | PARTIAL |
| P2-25 | Conditional auto-merge | Only a 100% Greenlight batch can enter auto-merge, and merge occurs only after all required GitHub checks pass. | Exact-commit CI polling and fail-closed merge logic are implemented and automated-tested in PRs #48/#50; no real official-result batch has traversed this path. | PARTIAL |
| P2-26 | Below-100% handling | A score below 100% aborts auto-merge, leaves the PR for manual review, and triggers the configured Owner alert. | PR state, score, and sanitized alert evidence. | NOT RUN |
| P2-27 | Last-known-good preservation | Acquisition, extraction, comparison, or validation failure leaves the currently published dataset unchanged. | Before/after deployed dataset version/hash. | NOT RUN |

**Phase 2 acceptance note:** The active project task is to find and validate a compliant official-content access path yielding exact passer-name/sequence-number pairs. A downloadable PDF is not a pass condition. Representative official-content mapping validation and a real released batch are separate acceptance milestones.

---

## 4. Phase 3 — Automated Broadcasting

**Blueprint basis:** Parts 3, 4, 16, and 19.

| ID | Live acceptance test | Pass condition | Evidence to retain | Status |
|---|---|---|---|---|
| P3-01 | Facebook Graph API connection | The Python broadcaster can use the configured authorized Facebook integration successfully. | Sanitized test result; never include tokens. | NOT RUN |
| P3-02 | Facebook publication | A test announcement is published successfully to the configured Facebook destination. | Published post URL and workflow log. | NOT RUN |
| P3-03 | Telegram Bot API connection | The Python broadcaster can use the configured authorized Telegram Bot API integration successfully. | Sanitized test result; never include bot tokens. | NOT RUN |
| P3-04 | Telegram publication | A test announcement is delivered successfully to the configured Telegram destination. | Message/channel reference and workflow log. | NOT RUN |
| P3-05 | Publication trigger gate | Public-result broadcasts occur only after the validated dataset PR has merged and the website deployment has succeeded. | Merge/deployment timestamps and broadcast event order. | NOT RUN |
| P3-06 | Announcement content | The announcement accurately identifies the authority/examination/year and links visitors to the results website. | Published test announcement content and URL. | NOT RUN |

---

## 5. Phase 4 — Frontend Web Worker Search

**Blueprint basis:** Parts 1–3, 7–8, 9, 13, 15, 16, and 17.

| ID | Live acceptance test | Pass condition | Evidence to retain | Status |
|---|---|---|---|---|
| P4-01 | Cloudflare Pages deployment | The static site and its assets deploy successfully from the approved repository workflow. | Pages deployment URL and build result. | NOT RUN |
| P4-02 | Searching page | The public Searching page loads and preserves the approved design. | Live URL and desktop/mobile visual check. | NOT RUN |
| P4-03 | Preparing page and status | The site reads generated `status.json` and displays the approved Preparing Mode when the status requires it. | Status file and live page evidence. | NOT RUN |
| P4-04 | Dataset loading | The frontend loads the appropriate dataset using the manifest for the selected authority, examination, and year. | Browser network trace and selected manifest entry. | NOT RUN |
| P4-05 | Search fields and result identity | Visitors can search by authority, examination, year, and name; a result shows the passer name with its corresponding sequence number. | Live search examples and expected-record comparison. | NOT RUN |
| P4-06 | Array-of-Arrays compatibility | The browser correctly reads the approved compact JSON array-of-arrays dataset. | Dataset fixture and browser result. | NOT RUN |
| P4-07 | Manifest and shard routing | The frontend follows manifest routes and loads the required shard(s) correctly. | Manifest, network trace, and search results across shard boundaries. | NOT RUN |
| P4-08 | IndexedDB caching | A downloaded dataset is stored in IndexedDB and can be reused on a subsequent search/session as designed. | Browser storage inspection and repeat-load evidence. | NOT RUN |
| P4-09 | Local cached search | A subsequent search can use the locally cached dataset without requesting the dataset again when cache is valid. | Browser network trace and search result. | NOT RUN |
| P4-10 | Web Worker offloading | Large search/filter work executes in the browser Web Worker rather than blocking the UI thread. | Runtime inspection/performance trace. | NOT RUN |
| P4-11 | 50,000-record performance | A 50,000-record dataset is searchable in the browser without dropping UI frames. This is the explicit Part 17 Performance criterion. | Reproducible device/browser, dataset, performance trace, and observed UI responsiveness. | NOT RUN |
| P4-12 | Zero backend search queries | Searching/filtering does not send search requests to a backend or query D1; data is served as static assets and searched locally. | Browser network trace during multiple searches. | NOT RUN |
| P4-13 | Public-site read-only security | The public Pages application has no mechanism or exposed credential that can write to internal data or repositories. | Source/configuration review and browser inspection. | NOT RUN |

---

## 6. Phase 5 — End-to-End Simulation & Security

**Blueprint basis:** Parts 1–3, 5, 9–13, 16–19, and 20–21.

| ID | Live acceptance test | Pass condition | Evidence to retain | Status |
|---|---|---|---|---|
| P5-01 | End-to-end dummy result detection | A controlled dummy result resource is detected by the Watcher in under 30 seconds in the specified simulation. | Timestamped target availability and Worker detection log. | NOT RUN |
| P5-02 | End-to-end webhook handoff | The detected event wakes the GitHub Actions processing workflow. | Dispatch event and Actions run URL. | NOT RUN |
| P5-03 | End-to-end Python processing | Python acquires the authorized test content, extracts the exact name/sequence pairs, and validates the batch. | Workflow log, generated records, and validation report. | NOT RUN |
| P5-04 | End-to-end clean Greenlight | A clean dummy batch reaches 100% Greenlight. | Full validation report. | NOT RUN |
| P5-05 | End-to-end GitOps merge | The clean batch PR passes all required checks and auto-merges under the 100% rule. | PR, checks, and merge commit. | NOT RUN |
| P5-06 | End-to-end broadcasting | After merge/deployment, the configured Facebook and Telegram announcements are sent. | Deployment and message/post references with timestamps. | NOT RUN |
| P5-07 | End-to-end deployment and search | The dataset is deployed to Pages and a visitor can search for a test passer and see the correct sequence number. | Pages deployment and live search evidence. | NOT RUN |
| P5-08 | Broken-input safety | A broken test input missing sequence numbers fails Greenlight and does not auto-merge or replace the public dataset. | Failed run, PR state, and unchanged public dataset hash. | NOT RUN |
| P5-09 | CAPTCHA / human-verification stop | When an official source presents CAPTCHA or another human-verification barrier, automated retrieval stops; no bypass is attempted. | Live CSC Region V HTTP 403 security-verification barrier led to source disablement/manual handling; PRC proxy/browser verification response was rejected as a source. No bypass attempted. Manual processing route remains incomplete. | PARTIAL |
| P5-10 | Manual-drop override | An Owner-authorized manual content/file handoff in `/manual-drop/` triggers the processing workflow and still undergoes Greenlight validation. | Commit/run URL and validation report. | NOT RUN |
| P5-11 | Secret protection | No API tokens, credentials, or private operational identifiers are exposed in public source code or frontend assets. | Secret scan and source/build inspection. | NOT RUN |
| P5-12 | Worker secret storage | The Watcher's GitHub credential is stored as a Cloudflare Worker secret, not in source code. | Sanitized configuration/deployment evidence. | NOT RUN |
| P5-13 | GitHub Actions secret storage | Required deployment credentials are stored in GitHub Actions Secrets, not committed to the repository. | Workflow configuration review and secret-scan evidence. | NOT RUN |
| P5-14 | Rollback | Reverting a problematic published merge restores the previous working Pages dataset/site within the blueprint's three-minute target. | Revert commit, Pages deployment timestamps, and restored dataset check. | NOT RUN |
| P5-15 | Logging and recovery | Important acquisition, processing, validation, publication, and failure paths produce sufficient logs and recover without corrupting the last known-good result. | Run logs and controlled failure/recovery evidence. | NOT RUN |
| P5-16 | Free-only operation | The end-to-end design operates within the approved free-service architecture and introduces no paid dependency. | Service configuration and usage evidence. | NOT RUN |

---

## 7. The three acceptance criteria explicitly named in Blueprint Part 17

These are the blueprint's expressly stated required testing criteria. The other phase checks above are derived from the Part 16 roadmap and the governing requirements in the other blueprint parts.

1. **Extraction Safety — P2-18 / P5-08:** Greenlight fails on a test input missing sequence numbers; automatic publication/merge aborts.
2. **Performance — P4-11:** A 50,000-record dataset is searchable in the browser without dropping UI frames.
3. **Preemptive Test — P1-06:** The Watcher identifies a result PDF/resource through HEAD before the official HTML page updates. The project’s content-first rule means PDF downloadability itself is not required; this test checks the blueprint's preemptive HEAD behavior, not a requirement to possess a PDF.

---

## 8. Live test record template

Copy this block for each test execution:

```text
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

## 9. Historical testing and verification transferred — 2026-11-03

This section records prior evidence so earlier tests are not repeated merely because this register was created later. Statuses above distinguish automated evidence from live acceptance.

### Confirmed historical evidence

- **Phase 1 automated Watcher:** PR #18 records 21 Watcher tests passed and 9 approved-Drive retrieval tests passed. The read-only diagnostics workflow completed successfully.
- **Phase 1 production diagnostics:** production cron and Worker runtime were observed; standard-mode execution had no exceptions; production KV was inspected; two synthetic receiver events succeeded but performed metadata validation only (`pdf_acquired=false`, `extraction_performed=false`, `published=false`).
- **Peak Week:** automated simulation verified the 30-second wait and two-scan behavior. A later production event observed `PEAK_WEEK=true` and two scans, but the retained record does not establish exact 30-second timestamps for that live invocation.
- **Official-source compliance:** PRC robots.txt was checked (HTTP 200) and public result article paths were not disallowed. CSC Region V returned HTTP 403 security verification and automated polling was paused. The system did not attempt to bypass either barrier.
- **Python/GitOps CI progression:** PR #48/#50 recorded 90 Python tests; PR #51 recorded 98; PR #52 recorded 104; PR #55 and its merged main-branch run recorded 112 Python tests passing. These are automated tests, not proof of a real result batch publication.
- **Extraction Safety:** PR #55 is the specific end-to-end pipeline regression test for a missing sequence. It passes with a deterministic extracted-table fixture and proves fail-closed publication behavior.
- **Owner verification:** The Owner explicitly confirmed personally testing Phase 1. This is retained as owner-reported verification in Blueprint Part 16; it does not replace independently retained logs for each acceptance test.

### Historical evidence that must not be overstated

- Synthetic HEAD fixtures do not satisfy the genuine Part 17 preemptive test.
- Synthetic receiver events do not prove a genuine official source detection dispatched the receiver.
- Staging parser tests do not prove extraction from a representative official result layout.
- An earlier 50,000-record Node/GitHub-runner search timing (66.69 ms) is not a browser UI-frame benchmark and does not satisfy P4-11.
- No complete real released-result batch has passed official acquisition, exact name/sequence validation, Greenlight, dataset generation, GitOps merge, and deployment.
- No Facebook/Telegram publication, production Pages search, or complete end-to-end result release acceptance is evidenced by the records reviewed.

### Evidence links

- [Phase 1 live acceptance audit](docs/PHASE_1_ACCEPTANCE_AUDIT_2026-11-03.md)
- [PR #18 — read-only Cloudflare production diagnostics](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/pull/18)
- [PR #48 — Python/GitOps integration](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/pull/48)
- [PR #51 — explicit PDF normalization](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/pull/51)
- [PR #52 — bounded official PDF acquisition](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/pull/52)
- [PR #55 — extraction safety regression test](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/pull/55)
- [PR #55 CI](https://github.com/github/actions/runs/41594622630)
- [Merged main CI](https://github.com/github/actions/runs/41594733732)

## 10. Current project position (reference only)

At the time this register was created, `PROGRESS_TRACKER.md` identifies **Phase 2 — The Extractor & Greenlight** as the active phase. The first unchecked task is to identify and validate a compliant official-content access path that provides passer names with their exact sequence numbers. The tracker also lists representative official-content mapping validation and a real released-result batch as remaining Phase 2 tasks.

This register does not change the progress tracker or mark implementation tasks complete. Each row now reflects the strongest evidence currently recorded: automated passes remain distinct from partial/live evidence and formal acceptance.
