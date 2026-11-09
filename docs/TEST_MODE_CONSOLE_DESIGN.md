# PH-EXAM-RESULTS — Owner Test Mode Console Design

- **Status:** Revised design proposal — awaiting Owner approval before implementation
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
6. A visible environment banner on every screen and report. Staging and Production Read-only must require an explicit mode selection; Simulation is the default.
7. A confirmation step before any staging action that creates a branch, pull request, or deployment preview. Simulation actions need no repeated confirmation.

Suggested stage-card content:

| # | Stage | Primary evidence |
|---|---|---|
| 1 | Release Detection | Fixture ID, detector decision, event fingerprint, timestamp |
| 2 | Webhook Dispatch | Test workflow name, dispatch response, Actions run ID |
| 3 | Event Verification | Accepted/rejected case matrix and validation reasons |
| 4 | Content Acquisition | Fixture/source identifier, retrieval mode, HTTP metadata if applicable, SHA-256 |
| 5 | Data Extraction | Extractor version, expected/actual record counts, synthetic fixture comparison |
| 6 | Data Normalization | Exact name/sequence preservation assertions, Unicode and whitespace cases |
| 7 | Greenlight Validation | Score, individual checks, issue codes, publication gate decision |
| 8 | Dataset & GitOps PR | Test-only manifest/shard hashes, branch, PR URL/number |
| 9 | CI Verification & Merge | Exact tested commit SHA, required check results, test-branch merge result |
| 10 | Website Deployment | Staging deployment URL, synthetic search verification, production isolation assertions |

Use the exact status vocabulary:

- `PASS`: defined assertions passed and evidence was saved.
- `FAIL`: test executed and one or more assertions failed.
- `BLOCKED`: a dependency, permission, configuration, or unavailable external service prevented a valid test.
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
2. The test workflow must require a validated test-run ID, explicit environment, fixture identifier, and allowed test branch. Reject `main`, production deployment environments, unknown fixture IDs, and any payload requesting publication or broadcasting.
3. The Owner browser must call same-origin protected Pages Functions endpoints. Every mutating request requires a valid Owner session, exact same-origin Origin check, and CSRF token. Authentication and CSRF must be checked again server-side for every action; hiding buttons is not security.
4. GitHub credentials stay server-side. Prefer a narrowly scoped GitHub App installation token or an equivalently restricted credential that can dispatch only the test workflow and manage only the dedicated test branch/PR scope. Never expose a credential to JavaScript, HTML, reports, or browser responses.
5. Use distinct Test Mode configuration and least-privilege credentials where feasible. Where real production integrations or credentials are required to verify the actual production path, expose them only to the server/workflow, scope them to the exact permitted action, and require explicit Owner approval. Missing required configuration returns BLOCKED; never silently fall back to a different environment.
6. Use a separate test D1 database for `test_runs` and `test_run_steps`. Do not create or write test tables in production D1 as a convenience. Production read-only checks may record their sanitized test evidence in the test D1 store.
7. Use unique run IDs, per-stage attempt IDs, idempotency keys, and a server-side state machine. Duplicate requests return the existing operation/result or a safe conflict; they must not start duplicate Actions runs or PRs.
8. Enforce server-side allowlists for mode, stage, fixture, branch, workflow, and deployment target. Reject arbitrary URLs, arbitrary Git refs, arbitrary workflow names, and caller-supplied commands.
9. Set explicit least-privilege workflow permissions per job. Test workflows must have no production deploy credentials, no social credentials, and no ability to change production data.
10. Preserve a durable audit trail with redacted errors. Never log Owner cookies, CSRF tokens, Firebase proofs, GitHub tokens, or examinee names.

**Fail-closed rule:** If the system cannot prove the environment boundary, the action does not run and is recorded as BLOCKED.

## 4. Proposed backend contract and persistence

Suggested same-origin endpoints (final names may be adjusted to match repository conventions):

- `GET /api/test-mode/config` — return allowed modes, stages, and safe readiness flags; Owner session required.
- `GET /api/test-runs?limit=...` — list the Owner's recent test runs from the test D1 database.
- `POST /api/test-runs` — create a run with explicit mode and requested stage(s); Owner session + CSRF required.
- `GET /api/test-runs/:runId` — return run summary and step evidence; Owner session required.
- `POST /api/test-runs/:runId/stages/:stageId` — start/retry one allowlisted stage; Owner session + CSRF required.
- `POST /api/test-runs/:runId/run-all` — start the ordered pipeline; Owner session + CSRF required.
- `GET /api/test-runs/:runId/report` — return the sanitized report; Owner session required.
- `GET /api/test-runs/:runId/report/download` — download the same report as JSON; Owner session required.

Proposed isolated test D1 tables:

- `test_runs`: `run_id`, `environment`, `status`, `requested_by_owner_uid` (opaque UID only), `started_at`, `completed_at`, `duration_ms`, `fixture_id`, `workflow_run_id`, `test_branch`, `staging_url`, `report_sha256`, `created_at`, `updated_at`.
- `test_run_steps`: `step_id`, `run_id`, `stage_number`, `attempt`, `status`, `started_at`, `completed_at`, `duration_ms`, `expected_summary`, `actual_summary`, `evidence_json`, `failure_code`, `failure_message_redacted`, `idempotency_key`.

Use a unique constraint on `run_id` and on `(run_id, stage_number, attempt)`; add indexes for recent runs and run-step ordering. Keep evidence compact and sanitized. Synthetic record content may exist only in dedicated test fixtures/artifacts; operational metadata should contain counts and hashes, not names.

## 5. Definition of the ten tests

### 1 — Release Detection

- Feed a saved synthetic PRC article/HTML fixture into the actual Watcher release-event builder/detection logic.
- Positive cases: supported PRC exam, unambiguous year and level, approved official-host URL, supported result-content link.
- Negative cases: missing/ambiguous exam, ambiguous year, wrong host, unsupported URL, no linked content.
- PASS only when the fixture's expected detection/review decision matches the actual result and the event is marked test-only. Record fixture ID, detector version, decision, event fingerprint, and timestamp.
- Do not mutate the live Watcher schedule/KV or create a production release event.

### 2 — Webhook Dispatch

- Dispatch the dedicated test workflow from an allowlisted test branch using the server-held test credential.
- Verify GitHub accepted the dispatch and correlate the created Actions run ID to the test-run ID (the dispatch API response itself may not return a run ID; poll the workflow-run list using a bounded correlation window and unique run ID).
- PASS only after the exact test workflow run is found and its test-run ID/mode/branch match. No production repository-dispatch event.

### 3 — Event Verification

- Exercise the existing validation rules where reusable, plus the test-only envelope validator, against valid, malformed, unauthorized, duplicate, expired/stale, and mismatched events.
- Assert that valid test envelopes are accepted only for the test workflow; production event types, unknown schemas, mismatched run IDs, unknown fixtures, and disallowed branches are rejected.
- Preserve sanitized case outcomes and rejection codes. Never include credentials or raw sensitive payloads in evidence.

### 4 — Content Acquisition

- Default to a saved fixture, loaded from a test-only fixture directory with a known SHA-256.
- Acquire the actual official PRC release content using the same approved source and retrieval method as the real pipeline. Record source URL, retrieval method, response metadata, retrieval timestamp, and content hash. Respect source access rules and existing acquisition limits.
- Record fixture/source ID, retrieval method, response classification, retrieval timestamp, and content hash. Treat external source unavailability as BLOCKED, not PASS.

### 5 — Data Extraction

- Run the real extraction/parser path against a synthetic PDF/HTML/image fixture selected for that test.
- Compare output with expected synthetic records, including count, sequence values, and a deterministic records hash.
- Keep extraction output in temporary test storage. A fixture mismatch is FAIL; unavailable optional parser dependencies are BLOCKED.

### 6 — Data Normalization

- Exercise the actual `normalize_extracted_tables` and relevant normalization path.
- Assert preservation of exact source names and sequence strings (including leading zeroes), Unicode letters/marks, punctuation, unusual whitespace, and duplicate rows for downstream detection; normalization must not silently repair, renumber, fuzzy-match, or discard source values.
- Record assertion results and hashes, not record names.

### 7 — Greenlight Validation

- Exercise the actual `validate_records` implementation and existing regression suite. Do not duplicate the missing-sequence regression already present in `python-engine/tests/test_pipeline.py` and `test_greenlight.py`; expose its existing test result as evidence.
- Include clean 100/100 positive data and deliberate negative fixtures for missing sequence numbers, duplicate names, duplicate sequence numbers, blank names, incorrect announced counts, anomalies/unexpected characters, and low-confidence OCR.
- Verify only a complete 100/100 report with all required checks true can be publication-eligible. In Test Mode, publication remains disabled even after 100/100.
- Record score, check booleans, issue codes, record count, and records hash only.

### 8 — Dataset & GitOps PR

- Generate the actual JSON shards, manifest, and hashes with the production dataset builder for the real release. Create a clearly labelled Test Mode branch and a real PR targeting the normal publication branch. The PR must identify the exact real source release and Test Mode run.
- Verify expected files, manifest integrity, shard hashes, catalog references, and PR metadata.
- Do not merge or publish until the Owner clicks the corresponding Publication button after reviewing the exact diff, source release, Greenlight report, and target branch.

### 9 — CI Verification & Merge

- Run CI against the exact head SHA from the test PR; record required checks and exact commit SHA.
- Test both successful and failing check outcomes. A deliberately failed required check must prevent merge.
- If branch protection/rulesets are configured for the test integration branch, verify the merge is blocked until required checks pass. If enforcement cannot be verified, mark BLOCKED rather than claiming protection.
- After required CI checks pass, pause and present an explicit **Approve Publication / Merge** button. The button must show the PR number, exact head SHA, target branch, dataset manifest hash, Greenlight result, and source release. Only the Owner's click may authorize merging that exact reviewed PR. Revalidate all values and required checks server-side at click time; if anything changed, invalidate the approval and require a fresh review.
- Record the merge commit SHA and checks. Do not merge automatically in Test Mode.

### 10 — Website Deployment

- After the approved merge, pause and present a separate **Approve Production Publication / Deploy** button before the production website deployment or other production publication action. Show the exact merge SHA, dataset/manifest hash, deployment target, and expected public effect. Only the Owner's click may authorize that specific deployment. Revalidate the merge SHA, CI status, and target server-side at click time; changed inputs invalidate approval.
- After approval, run the actual production deployment and verify the deployed site and real search behavior against the published release. Record deployment ID/URL, commit SHA, and post-deployment checks.
- If the Owner does not click, keep the run paused and do not publish or deploy.

## 6. Run All orchestration

Run stages in strict order: 1 through 10. Each stage must publish a terminal state and evidence before the next stage begins.

- Stop on the first FAIL or BLOCKED stage that is a required dependency.
- Mark later dependent stages SKIPPED, preserving all earlier evidence.
- A stage can be rerun independently after the cause is addressed; create a new attempt and preserve the prior attempt.
- Do not silently restart earlier PASS stages unless their input fixture/version changed or the Owner explicitly requests a full fresh run.
- Stages 8–10 use the real repository, CI, merge, and production deployment integrations. Test Mode pauses for explicit Owner Publication-button approval before merge/publication and again before production deployment. No simulated or mocked substitute counts as a real-world PASS.

## 7. Report format

Every run produces a downloadable JSON report and a readable dashboard view containing:

- Test Run ID and idempotency key (redacted/opaque)
- Environment and mode
- Started/completed timestamps and total duration
- Stage number/name, attempt, status, start/end, duration
- Fixture/source identifier and detector/parser/engine version where relevant
- Expected and actual sanitized summaries (counts, decisions, assertions)
- Evidence references: Actions run ID/URL, test branch/PR, commit SHA, artifact name/hash, staging URL
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
| Staging isolation and deployment checks | P4-18 supporting evidence | Desktop/mobile walkthrough and rollback execution remain separate |

A Test Mode PASS or Owner-clicked publication approval must never automatically change P4-15, P4-16, P4-17, or P4-18 to PASS.

## 9. Implementation gates and acceptance criteria

Implement in this order:

1. **Foundation:** threat model, dedicated Test Mode workflow, test-run audit store, server-side allowlists, Owner + CSRF enforcement, idempotency, publication approval state machine, and tests proving no publication occurs without the relevant Owner click.
2. **Stages 1–3:** Watcher fixture detection, dedicated workflow dispatch, event verification matrix.
3. **Stages 4–7:** fixture acquisition, real extraction/normalization, Greenlight positive and negative matrix.
4. **Stages 8–9:** isolated dataset generation, test PR, exact-SHA CI and protected test-branch merge.
5. **Stage 10 and orchestration:** staging deployment, Run All, report view/download, run history, final isolation verification.

A phase is not accepted because its UI exists or its workflow starts. It must pass its own automated tests, demonstrate expected evidence, and prove the relevant production-isolation assertions.

### Explicit non-goals

- No CSC testing.
- No synthetic or mocked data as evidence of real-world Test Mode execution.
- No production merge, publication, or deployment in Test Mode without the specific Owner-clicked Publication approval.
- No social notifications.
- No new public dashboard or authentication system.
- No automatic promotion of synthetic/staging results into the live acceptance register.

## 10. Decisions requested before implementation

The following design choices are recommended and require Owner confirmation:

1. Keep the console inside `/owner/` — recommended.
2. Use a separate test-run audit store where practical, while the tested release content, GitHub PR/CI, publication target, and deployment path are the real production resources. Never isolate the test by replacing real-world behavior with synthetic data.
3. Use server-held, least-privilege credentials and explicit per-action authorization; no credentials in the browser.
4. Test Mode may prepare a real PR targeting the normal publication branch, but must pause for the Owner's explicit Publication-button approval before merge/publication.
5. After merge, Test Mode must pause again for a separate Owner click before production deployment. These manual gates apply only to Test Mode; ordinary automated production processing keeps its existing behavior.
6. Preserve the existing Owner authentication, CSRF, audit, and production-isolation protections. Do not let Test Mode approval become a general authorization for unrelated runs or later changed commits.

**No application code, workflow, database, branch, deployment, or production configuration is changed by this design document. Implementation begins only after Owner approval of this design and the required environment/credential prerequisites.**
