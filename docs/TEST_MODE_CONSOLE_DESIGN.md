# PH-EXAM-RESULTS — Owner Test Mode Console Design

- **Status:** Owner-approved design (2026-11-09); Steps 3A and 3B merged; Step 3C real PRC event ingestion in implementation
- **Scope:** PRC only; CSC testing remains excluded under Owner decision D-003
- **Owner UI:** Existing same-origin Owner Dashboard at `/owner/`
- **Baseline:** PR #160 merged at `9687aec521667f87c23a09d3d0dead1bf3624f0f`; current Owner live-acceptance items P4-15–P4-18 remain as recorded in `LIVE_ACCEPTANCE_TEST_REGISTER.md`
- **Operating principle:** Test Mode uses 100% real-world PRC source material and real integrations. It must not use synthetic fixtures, mocked service responses, or simulated success as evidence of a real-world test.
- **Publication control:** Test Mode pauses at each production-publication boundary and requires the Owner to click the relevant explicit Publication button(s). This manual approval behavior applies only to Test Mode. The normal automated production pipeline retains its existing independent behavior and is not changed by this design.

## 1. Product design

Add a new **Automation Test Console** section inside the authenticated Owner Dashboard. Do not create another dashboard, public route, or second login system.

The page should present:

1. A clear **OWNER ONLY · TEST ENVIRONMENT** label.
2. A clearly marked **Real-world Test Mode**. It uses live official PRC source material and actual integrations; there is no Simulation / Fixtures mode.
3. Overall progress, such as `0 / 10`, calculated from the selected run only.
4. Ten ordered stage cards, each with a stage number, concise purpose, latest status, last-run time/duration, **Test** action, and a detail/report expander.
5. **Run All Tests**, **View Test Report**, and a run-history list.
6. A visible **REAL-WORLD TEST MODE** banner on every screen and report, including the exact source release and run ID.
7. Explicit Owner confirmation at each publication boundary: one Publication button before merge/publication, and a separate Publication button before production deployment.

Suggested stage-card content:

| # | Stage | Primary evidence |
|---|---|---|
| 1 | Release Detection | Official source/release identity, detector decision, event fingerprint, timestamp |
| 2 | Webhook Dispatch | Test workflow name, dispatch response, Actions run ID |
| 3 | Event Verification | Accepted/rejected case matrix and validation reasons |
| 4 | Content Acquisition | Official source URL, retrieval method, HTTP metadata, retrieved-content SHA-256 |
| 5 | Data Extraction | Extractor version, real source record counts, source/output hashes and reconciliation |
| 6 | Data Normalization | Exact name/sequence preservation assertions, Unicode and whitespace cases |
| 7 | Greenlight Validation | Score, individual checks, issue codes, publication gate decision |
| 8 | Dataset & GitOps PR | Real-release manifest/shard hashes, branch, PR URL/number |
| 9 | CI Verification & Merge | Exact tested commit SHA, required check results, test-branch merge result |
| 10 | Website Deployment | Owner-approved production deployment ID/URL, live search verification and deployed commit SHA |

Use the exact status vocabulary:

- `PASS`: defined assertions passed and evidence was saved.
- `FAIL`: test executed and one or more assertions failed.
- `BLOCKED`: a dependency, permission, configuration, or unavailable real release/external service prevented a valid test.
- `NOT RUN`: no test result exists.
- `SKIPPED`: an upstream dependency failed or was blocked in a sequential run.

A missing report, unverified external action, or incomplete assertion must never be interpreted as PASS. A retry creates a new attempt under the same run lineage; it does not erase earlier evidence.

## 2. Environment boundaries

### One mode — Real-world Test Mode

- Use actual official PRC source pages, real release notices, real result files, and real source content. Do not substitute synthetic fixtures or fabricated records for any stage's real-world evidence.
- Exercise the actual Watcher detection and event creation, the dedicated Test Mode dispatch, real event verification, actual bounded source acquisition, the real extraction and normalization pipeline, the real Greenlight validator, actual dataset generation, the real GitHub PR and CI checks, and the real publication/deployment path.
- Test Mode must be visibly and technically tagged throughout the run so that its events, logs, branches, PRs, and audit records can be distinguished from ordinary automated production runs.
- Use a dedicated Test Mode workflow and separate test-run audit metadata. Real source content and production integration behavior must not be replaced with mocks. Any temporary storage must be access-controlled and must follow the repository's data-retention and privacy requirements.
- Test Mode must pause before every irreversible production publication action. The Owner must click the specific Publication button for that action. A click authorizes only the named action for the displayed run and exact commit/artifact; it is not blanket approval for later actions.
- Do not send Facebook/Telegram notifications from Test Mode unless the Owner explicitly authorizes a separately presented notification action. Normal automated production behavior remains independent and unchanged.
- If a real official release or required external service is unavailable, mark the relevant stage BLOCKED. Never manufacture a PASS using fixtures or mocks.

## 3. Non-negotiable safety architecture

The current `.github/workflows/process-import.yml` contains a `repository_dispatch` handler for `prc-release-detected` that can acquire official PRC content, run Greenlight, and call the publication pipeline. **Never reuse that event for Test Mode.**

Implement the following boundaries before enabling any test action:

1. Create a separate `.github/workflows/test-mode.yml` with a dedicated Test Mode trigger and an explicit test-run ID. It must not impersonate an ordinary automated production run. It may call shared production processing code through a deliberately designed, audited interface, but must not silently trigger the normal production workflow or bypass Test Mode's Owner publication gates.
2. The Test Mode workflow must require a validated test-run ID, official PRC release identity, approved source URL, and permitted branch. Reject unknown sources, arbitrary URLs/refs/workflows, and any payload that bypasses the Owner publication gates.
3. The Owner browser must call same-origin protected Pages Functions endpoints. Every mutating request requires a valid Owner session, exact same-origin Origin check, and CSRF token. Authentication and CSRF must be checked again server-side for every action; hiding buttons is not security.
4. GitHub credentials stay server-side. Prefer a narrowly scoped GitHub App installation token or an equivalently restricted credential that can dispatch the Test Mode workflow and manage only the required PR/branch operations. Never expose a credential to JavaScript, HTML, reports, or browser responses.
5. Use distinct Test Mode configuration and least-privilege credentials where feasible. Where real production integrations or credentials are required to verify the actual production path, expose them only to the server/workflow, scope them to the exact permitted action, and require explicit Owner approval. Missing required configuration returns BLOCKED; never silently fall back to a different environment.
6. Use a separate test D1 database for `test_runs` and `test_run_steps` audit metadata where feasible. The real publication dataset and normal production data stores remain the actual targets of the approved production pipeline; do not redirect or shadow them to claim a real-world publication test.
7. Use unique run IDs, per-stage attempt IDs, idempotency keys, and a server-side state machine. Duplicate requests return the existing operation/result or a safe conflict; they must not start duplicate Actions runs or PRs.
8. Enforce server-side allowlists for stage, official source, branch, workflow, and deployment target. Reject arbitrary URLs, arbitrary Git refs, arbitrary workflow names, and caller-supplied commands.
9. Set explicit least-privilege workflow permissions per job. Production publication/deployment credentials must be unavailable until the corresponding Owner approval is validated server-side. Social credentials remain unavailable to Test Mode.
10. Preserve a durable audit trail with redacted errors. Never log Owner cookies, CSRF tokens, Firebase proofs, GitHub tokens, or unnecessary examinee names.

**Fail-closed rule:** If the system cannot prove the run identity, source identity, exact approved commit/artifact, Owner authorization, or deployment target, the action does not run and is recorded as BLOCKED.

## 4. Proposed backend contract and persistence

Suggested same-origin endpoints (final names may be adjusted to match repository conventions):

- `GET /api/test-mode/config` — return Test Mode availability, stages, publication-gate state, and safe readiness flags; Owner session required.
- `GET /api/test-runs?limit=...` — list the Owner's recent Test Mode runs from the test audit database.
- `POST /api/test-runs` — create a real-world Test Mode run bound to a specific official release; Owner session + CSRF required.
- `GET /api/test-runs/:runId` — return run summary and step evidence; Owner session required.
- Run creation accepts only a server-verified Watcher event ID; the browser cannot submit source URLs, release metadata, Git refs, or workflow names.
- Each run requires an `Idempotency-Key` header. The server binds the key to the authenticated Owner UID and returns the existing run on a replay.
- A new run stores the verified event reference and creates exactly ten stage rows in `NOT RUN` state, attempt 1. Run creation does not dispatch a workflow or start stage execution.
- Run history and detail reads are scoped to the authenticated Owner UID. Missing Test Mode configuration, missing verified events, invalid source metadata, and storage errors fail closed.
- `POST /api/test-runs/:runId/stages/:stageId` — start/retry one allowlisted stage; Owner session + CSRF required.
- `POST /api/test-runs/:runId/run-all` — start/resume the ordered pipeline up to the next publication gate; Owner session + CSRF required.
- `GET /api/test-runs/:runId/report` — return the sanitized report; Owner session required.
- `GET /api/test-runs/:runId/report/download` — download the same report as JSON; Owner session required.
- `POST /api/test-runs/:runId/publication-approvals/:action` — authorize one exact merge or deployment action; Owner session + CSRF required; server revalidates run state, commit/artifact hash, CI, target, and approval scope.

Proposed isolated test D1 tables:

- `test_runs`: `run_id`, `mode`, `status`, `requested_by_owner_uid` (opaque UID only), `source_release_id`, `source_url`, `started_at`, `completed_at`, `duration_ms`, `workflow_run_id`, `pull_request_number`, `head_sha`, `merge_sha`, `deployment_id`, `deployment_url`, `report_sha256`, `created_at`, `updated_at`.
- `test_run_steps`: `step_id`, `run_id`, `stage_number`, `attempt`, `status`, `started_at`, `completed_at`, `duration_ms`, `expected_summary`, `actual_summary`, `evidence_json`, `failure_code`, `failure_message_redacted`, `idempotency_key`, `approval_state`, `approved_by_owner_uid`, `approved_at`, `approved_action_sha`.

Use a unique constraint on `run_id` and on `(run_id, stage_number, attempt)`; add indexes for recent runs and run-step ordering. Keep evidence compact and sanitized. Do not duplicate examinee names or raw result rows in the test audit database or reports; use counts, hashes, and restricted evidence references.

## 4A. Run lifecycle foundation (Step 3B)

The dedicated Test Mode database contains a verified release-event ledger. Only events marked `VERIFIED` and carrying a PRC source ID in the explicit Test Mode allowlist can be used to create a run. The event must have a stable fingerprint, payload hash, detection time, and verification time. The browser supplies only the event ID; all source and release fields are read from the ledger and revalidated on the server.

Run creation is atomic: one run row and ten ordered `NOT RUN` stage rows are inserted together. A unique Owner-scoped idempotency index prevents duplicate runs when a request is retried. Existing runs and stage history are retained. The run status `RUNNING` means the run record is open; it does not mean a stage or workflow has started.

This foundation deliberately does not create or populate verified Watcher events, dispatch a workflow, execute a stage, or authorize publication. Until a trusted Watcher-to-Test-Mode event writer is implemented and a real event is verified, run creation remains unavailable.

## 5. Definition of the ten tests

### 1 — Release Detection

- Observe an actual official PRC release notice through the real Watcher detection path.
- Verify the actual exam identity, year/level, official-host URL, linked result content, detector decision, and event fingerprint.
- PASS only when the real release is correctly detected and correlated to the Test Mode run without creating a duplicate or bypassing the normal release safeguards.
- Record source/release identity, detector version, decision, event fingerprint, and timestamp.

### 2 — Webhook Dispatch

- Dispatch the dedicated Test Mode workflow for the real release using the server-held credential and exact run/release correlation.
- Verify GitHub accepted the dispatch and correlate the created Actions run ID to the Test Mode run ID (the dispatch API response itself may not return a run ID; poll the workflow-run list using a bounded correlation window and unique run ID).
- PASS only after the exact Test Mode workflow run is found and its run ID, source release, and branch match. Do not create duplicate release events or bypass the normal production safeguards.

### 3 — Event Verification

- Verify the actual event generated for the detected PRC release against the production event contract and Test Mode run correlation.
- Confirm source identity, release identity, event schema, signature/authentication where applicable, freshness, and duplicate/idempotency handling.
- Run existing automated negative/security regression tests as supplemental evidence, but do not present their synthetic cases as the real-world run result.

### 4 — Content Acquisition

- Acquire the actual official PRC result content through the real acquisition path and approved source access method.
- Record source URL, retrieval method, response metadata, retrieval timestamp, and content hash. Respect source access rules and existing acquisition limits. Treat source unavailability as BLOCKED, not PASS.

### 5 — Data Extraction

- Run the actual extraction/parser path against the acquired official PRC result file.
- Reconcile extracted record counts and source structure against the real document and record parser version, confidence/quality indicators, and deterministic output hashes.
- Any mismatch or unresolved OCR uncertainty must be reported for review and must not be silently repaired.

### 6 — Data Normalization

- Run the actual `normalize_extracted_tables` and relevant production normalization path on the records extracted from the real PRC result.
- Reconcile normalized output against the extracted source values, preserving exact names and sequence strings (including leading zeroes), Unicode, punctuation, and meaningful whitespace. Do not silently repair, renumber, fuzzy-match, or discard source values.
- Record aggregate assertion results and hashes; keep personal data out of routine logs and reports.

### 7 — Greenlight Validation

- Run the actual `validate_records` implementation on the real release dataset and preserve its full machine-readable validation evidence in access-controlled storage.
- Verify the announced count, extracted count, sequence integrity, duplicate checks, name checks, anomalies, OCR confidence, and all other required Greenlight criteria.
- A complete 100/100 result with every required check true is necessary but does not itself authorize publication. The Test Mode publication approval buttons remain mandatory.
- Run the existing automated regression suite separately as supplemental software-quality evidence; it does not replace the real release validation.

### 8 — Dataset & GitOps PR

- Generate the actual JSON shards, manifest, and hashes with the production dataset builder for the real release. Create a clearly labelled Test Mode branch and a real PR targeting the normal publication branch. The PR must identify the exact real source release and Test Mode run.
- Verify expected files, manifest integrity, shard hashes, catalog references, and PR metadata.
- Do not merge or publish until the Owner clicks the corresponding Publication button after reviewing the exact diff, source release, Greenlight report, and target branch.

### 9 — CI Verification & Merge

- Run CI against the exact head SHA from the test PR; record required checks and exact commit SHA.
- Verify the actual required CI checks for the real release PR. A failed or missing required check must prevent the Owner publication button from becoming available. Use separate automated regression tests for deliberately failing CI scenarios.
- Verify the normal publication branch's actual branch protection/ruleset and required checks. If enforcement cannot be verified, mark BLOCKED rather than claiming the merge is protected.
- After required CI checks pass, pause and present an explicit **Publication — Approve Merge** button. Show the PR number, exact head SHA, target branch, dataset manifest hash, Greenlight result, and official source release. Only the Owner's click may authorize merging that exact reviewed PR. Revalidate all values and required checks server-side at click time; if anything changed, invalidate the approval and require a fresh review.
- Record the merge commit SHA and checks. Do not merge automatically in Test Mode.

### 10 — Website Deployment

- After the merge, pause and present a separate **Publication — Approve Production Deployment** button before the production website deployment. Show the exact merge SHA, dataset/manifest hash, production deployment target, and expected public effect. Only the Owner's click may authorize that specific deployment. Revalidate the merge SHA, CI status, and target server-side at click time; changed inputs invalidate approval.
- After approval, run the actual production deployment and verify the deployed site and real search behavior against the published release. Record deployment ID/URL, commit SHA, and post-deployment checks.
- If the Owner does not click, keep the run paused and do not publish or deploy.

## 6. Run All orchestration

Run stages in strict order: 1 through 10. Each stage must publish a terminal state and evidence before the next stage begins.

- Stop on the first FAIL or BLOCKED stage that is a required dependency.
- Mark later dependent stages SKIPPED, preserving all earlier evidence.
- A stage can be rerun independently after the cause is addressed; create a new attempt and preserve the prior attempt. A new source release or changed artifact must invalidate downstream approvals.
- Do not silently restart earlier PASS stages unless the official source release, processing version, or input content changed, or the Owner explicitly requests a full fresh run.
- All ten stages use real-world source data and actual integrations. Test Mode pauses for explicit Owner Publication-button approval before merge/publication and again before production deployment. No simulated or mocked substitute counts as a real-world PASS.

## 7. Report format

Every run produces a downloadable JSON report and a readable dashboard view containing:

- Test Run ID and idempotency key (redacted/opaque)
- Environment and mode
- Started/completed timestamps and total duration
- Stage number/name, attempt, status, start/end, duration
- Official source/release identifier and detector/parser/engine version where relevant
- Expected and actual sanitized summaries (counts, decisions, assertions)
- Evidence references: Actions run ID/URL, branch/PR, commit SHA, artifact name/hash, production deployment ID/URL
- Failure code and redacted diagnostic message
- Report SHA-256 and report schema version
- Related acceptance test IDs, clearly labelled as references only

Reports must not contain examinee names, raw result rows, Owner credentials, Firebase tokens/proofs, session cookies, CSRF values, GitHub tokens, or production secret values. Test reports are separate from production acceptance records.

## 8. Mapping to production acceptance

Test Console outcomes and live acceptance remain independent:

| Test evidence | Related live acceptance | What it does not prove |
|---|---|---|
| Test stages 1–3 | Real Watcher detection and event processing | Normal unattended automated operation outside Test Mode |
| Test stages 4–7 | Actual acquisition/extraction/normalization/Greenlight on a real release | Normal unattended automated operation outside Test Mode |
| Test stages 8–9 | Real GitOps PR and CI, followed by Owner-clicked publication approval | Normal unattended automated merge behavior outside Test Mode |
| Test stage 10 | Owner-approved real production deployment and post-deployment verification | Normal unattended automated deployment behavior outside Test Mode |
| Owner dashboard sign-in/API/CSRF checks | P4-15, P4-16, P4-17 | These are still live Owner acceptance procedures and must be run separately |
| Test Mode publication/deployment evidence | P4-18 supporting evidence | Desktop/mobile walkthrough and rollback execution remain separate |

A Test Mode PASS or Owner-clicked publication approval must never automatically change P4-15, P4-16, P4-17, or P4-18 to PASS.

## 9. Implementation gates and acceptance criteria

Implement in this order:

1. **Foundation:** threat model, dedicated Test Mode workflow, test-run audit store, server-side allowlists, Owner + CSRF enforcement, idempotency, publication approval state machine, and tests proving no publication occurs without the relevant Owner click.
2. **Stages 1–3:** real Watcher detection, dedicated Test Mode workflow dispatch, and verification of the actual release event.
3. **Stages 4–7:** actual official-source acquisition, extraction, normalization, and Greenlight validation on the real release.
4. **Stages 8–9:** real dataset generation, real PR to the normal publication branch, exact-SHA CI, and Owner-approved merge.
5. **Stage 10 and orchestration:** Owner-approved production deployment, Run All pause/resume, report view/download, run history, and post-deployment verification.

A phase is not accepted because its UI exists or its workflow starts. It must pass its own automated tests, demonstrate expected evidence, and prove the relevant production-isolation assertions.

### Explicit non-goals

- No CSC testing.
- No synthetic or mocked data as evidence of real-world Test Mode execution.
- No production merge, publication, or deployment in Test Mode without the specific Owner-clicked Publication approval.
- No social notifications from Test Mode by default.
- No new public dashboard or authentication system.
- No automatic promotion of Test Mode results into the live acceptance register.

## 10. Owner-approved implementation decisions

The Owner approved the following decisions on 2026-11-09. Implementation remains phase-gated; this approval covers the safety foundation only.

1. Keep the console inside `/owner/` — recommended.
2. Use a separate test-run audit store where practical, while the tested release content, GitHub PR/CI, publication target, and deployment path are the real production resources. Never isolate the test by replacing real-world behavior with synthetic data.
3. Use server-held, least-privilege credentials and explicit per-action authorization; no credentials in the browser.
4. Test Mode may prepare a real PR targeting the normal publication branch, but must pause for the Owner's explicit Publication-button approval before merge/publication.
5. After merge, Test Mode must pause again for a separate Owner click before production deployment. These manual gates apply only to Test Mode; ordinary automated production processing keeps its existing behavior.
6. Preserve the existing Owner authentication, CSRF, audit, and production-isolation protections. Do not let Test Mode approval become a general authorization for unrelated runs or later changed commits.

**Step 3A boundary:** the approved first implementation slice adds an Owner-authenticated readiness endpoint, fail-closed PRC source validation, isolated Test Mode audit schema, focused security tests, and aligned project records. It does not enable run creation, workflow dispatch, production publication, deployment, social notifications, or any Test Mode action. No production workflow, normal PRC automation, production D1 binding, or production configuration is changed. The dedicated `TEST_MODE_DB` binding and explicit enable/source allowlist configuration are prerequisites; without them the endpoint reports `BLOCKED` and never falls back to production storage. The normal production pipeline retains its existing behavior.


### Step 3C — genuine PRC event ingestion

The Watcher may optionally forward metadata for a genuine official PRC release to `/api/test-mode/events`. This separate HTTPS request uses a dedicated shared token. The Pages endpoint checks Test Mode readiness, the PRC source allowlist, official PRC hostname, release metadata, and content hashes before inserting a VERIFIED event into the dedicated `TEST_MODE_DB`. Duplicate fingerprints are idempotent. The existing production `prc-release-detected` repository dispatch remains unchanged. The endpoint does not create a Test Mode run, dispatch a Test Mode workflow, merge code, or deploy anything.

Required runtime configuration is not committed: Pages must have its dedicated `TEST_MODE_DB`, `TEST_MODE_ENABLED=true`, `TEST_MODE_ALLOWED_SOURCE_IDS`, and the matching `TEST_MODE_EVENT_INGEST_TOKEN`; the Watcher must have `TEST_MODE_EVENT_INGEST_URL` and the same token stored as a Worker secret. Until configured, the handoff is inactive and cannot produce a real-world PASS.
