# PH-EXAM-RESULTS — Owner Test Mode Console Design

- **Status:** Design proposal — awaiting Owner approval before implementation
- **Scope:** PRC only; CSC testing remains excluded under Owner decision D-003
- **Owner UI:** Existing same-origin Owner Dashboard at `/owner/`
- **Baseline:** PR #160 merged at `9687aec521667f87c23a09d3d0dead1bf3624f0f`; current Owner live-acceptance items P4-15–P4-18 remain as recorded in `LIVE_ACCEPTANCE_TEST_REGISTER.md`
- **Safety rule:** Test Mode must never invoke the production `repository_dispatch: prc-release-detected` event, publish to `public/data/` on `main`, alter production D1 data, deploy the production Pages project, or send Facebook/Telegram notifications.

## 1. Product design

Add a new **Automation Test Console** section inside the authenticated Owner Dashboard. Do not create another dashboard, public route, or second login system.

The page should present:

1. A clear **OWNER ONLY · TEST ENVIRONMENT** label.
2. An environment selector with three explicit modes: Simulation / Fixtures (default), Staging, and Production Read-only.
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

### Mode A — Simulation / Fixtures (default)

- Use committed synthetic fixtures and deterministic expected outputs.
- Exercise the real Watcher event builder, Python extraction/normalization/Greenlight functions, dataset builder, and validation code wherever practical.
- External network access, production D1, GitHub write operations, Pages deployment, and social notifications are disabled.
- Use temporary directories and test-only artifacts. Do not write into `public/data/`, `manual-drop/`, or production artifact paths.
- A simulation PASS proves the tested code path against the named fixture and version only; it does not prove a live PRC release was detected.

### Mode B — Staging

- Use a dedicated test-only GitHub Actions workflow and an allowlisted branch namespace such as `test-mode/run-<run-id>` plus a protected `test-mode/integration` branch.
- Use a dedicated non-production Pages project/environment and a dedicated test D1 database. Do not point staging writes at the production D1 database.
- Use synthetic records only. Never copy live examinee records into test fixtures, reports, logs, or artifacts.
- External services must be limited to the GitHub Actions and staging deployment functions explicitly required by the test. Facebook and Telegram are always disabled.
- Staging deployment and test-branch merge must be distinguishable from production merge/deployment in UI, logs, and reports.

### Mode C — Production Read-only

- Only run named health checks that are explicitly allowlisted: production Owner-auth readiness, unauthenticated route protection, public search availability, approved PRC source reachability/robots policy metadata, and read-only service status.
- No fake release event, repository dispatch, acquisition pipeline, D1 write, branch/PR, merge, production deploy, or notification is permitted.
- Any check requiring a production write or synthetic production event is unavailable in this mode and must return BLOCKED with a clear reason.
- Production read-only PASS is not equivalent to live Owner acceptance P4-15–P4-18 unless the corresponding acceptance procedure and evidence are explicitly completed.

## 3. Non-negotiable safety architecture

The current `.github/workflows/process-import.yml` contains a `repository_dispatch` handler for `prc-release-detected` that can acquire official PRC content, run Greenlight, and call the publication pipeline. **Never reuse that event for Test Mode.**

Implement the following boundaries before enabling any test action:

1. Create a separate `.github/workflows/test-mode.yml`; its only accepted trigger should be a dedicated test-only `workflow_dispatch` (or another separately named test event with equivalent strict isolation). It must not invoke `process-import.yml` or dispatch `prc-release-detected`.
2. The test workflow must require a validated test-run ID, explicit environment, fixture identifier, and allowed test branch. Reject `main`, production deployment environments, unknown fixture IDs, and any payload requesting publication or broadcasting.
3. The Owner browser must call same-origin protected Pages Functions endpoints. Every mutating request requires a valid Owner session, exact same-origin Origin check, and CSRF token. Authentication and CSRF must be checked again server-side for every action; hiding buttons is not security.
4. GitHub credentials stay server-side. Prefer a narrowly scoped GitHub App installation token or an equivalently restricted credential that can dispatch only the test workflow and manage only the dedicated test branch/PR scope. Never expose a credential to JavaScript, HTML, reports, or browser responses.
5. Use distinct `TEST_*` secrets and configuration. No test action may fall back to production secrets when test configuration is missing; missing configuration returns BLOCKED.
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
- Optional staging/production read-only check may make an explicitly authorized bounded GET to an approved official PRC URL; it must not download result files unless the source/method is separately approved, and must not write to production storage.
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

- Generate JSON shards, manifest, and hashes with the real dataset builder, writing only to a test workspace.
- Open a PR only from an ephemeral `test-mode/run-<run-id>` branch into a dedicated staging integration branch. PR content must be synthetic and test-only.
- Verify expected files, manifest integrity, shard hashes, catalog references, and PR metadata.
- Do not modify production `public/data/` on `main`, the production catalog, or production data.

### 9 — CI Verification & Merge

- Run CI against the exact head SHA from the test PR; record required checks and exact commit SHA.
- Test both successful and failing check outcomes. A deliberately failed required check must prevent merge.
- If branch protection/rulesets are configured for the test integration branch, verify the merge is blocked until required checks pass. If enforcement cannot be verified, mark BLOCKED rather than claiming protection.
- A successful simulated merge may target only `test-mode/integration`; never merge test content to `main`.
- Record merged commit SHA and checks. If test branch merge is not authorized/configured, leave the PR open and report BLOCKED.

### 10 — Website Deployment

- Deploy the test-only dataset to a dedicated staging Pages project/environment, never the production Pages project.
- Verify the staging URL loads and the synthetic dataset can be searched using the public site's real search UI.
- Assert the production site URL, production `main` SHA, production D1, and production dataset hashes are unchanged before and after the test.
- Production deployment is never an allowed target. Missing staging project credentials or target confirmation is BLOCKED.

## 6. Run All orchestration

Run stages in strict order: 1 through 10. Each stage must publish a terminal state and evidence before the next stage begins.

- Stop on the first FAIL or BLOCKED stage that is a required dependency.
- Mark later dependent stages SKIPPED, preserving all earlier evidence.
- A stage can be rerun independently after the cause is addressed; create a new attempt and preserve the prior attempt.
- Do not silently restart earlier PASS stages unless their input fixture/version changed or the Owner explicitly requests a full fresh run.
- Stage 8–10 require Staging mode. Simulation may run local equivalents for stages 8–10 (manifest generation, mocked PR/CI/deploy assertions) but must label them as simulated, not as actual GitHub or deployment integration.
- Production Read-only is a separate set of allowlisted health checks; it cannot execute the ten-stage publication path or Run All.

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
| Test stages 1–3 | Watcher/event contract checks | Genuine official PRC release detection in production |
| Test stages 4–7 | Acquisition/extraction/Greenlight regression | Correctness of a real release's source content or OCR review |
| Test stages 8–9 | GitOps/CI branch isolation | Production-main merge authorization or live publication |
| Test stage 10 | Staging deployment | Production Pages deployment |
| Owner dashboard sign-in/API/CSRF checks | P4-15, P4-16, P4-17 | These are still live Owner acceptance procedures and must be run separately |
| Staging isolation and deployment checks | P4-18 supporting evidence | Desktop/mobile walkthrough and rollback execution remain separate |

A synthetic/staging PASS must never automatically change P4-15, P4-16, P4-17, or P4-18 to PASS.

## 9. Implementation gates and acceptance criteria

Implement in this order:

1. **Foundation:** threat model, test-only workflow, test D1 database, server-side mode/branch/fixture allowlists, Owner + CSRF enforcement, idempotency, no-production-side-effects tests.
2. **Stages 1–3:** Watcher fixture detection, dedicated workflow dispatch, event verification matrix.
3. **Stages 4–7:** fixture acquisition, real extraction/normalization, Greenlight positive and negative matrix.
4. **Stages 8–9:** isolated dataset generation, test PR, exact-SHA CI and protected test-branch merge.
5. **Stage 10 and orchestration:** staging deployment, Run All, report view/download, run history, final isolation verification.

A phase is not accepted because its UI exists or its workflow starts. It must pass its own automated tests, demonstrate expected evidence, and prove the relevant production-isolation assertions.

### Explicit non-goals

- No CSC testing.
- No production release simulation.
- No production publication, merge, or deployment.
- No social notifications.
- No new public dashboard or authentication system.
- No automatic promotion of synthetic/staging results into the live acceptance register.

## 10. Decisions requested before implementation

The following design choices are recommended and require Owner confirmation:

1. Keep the console inside `/owner/` — recommended.
2. Use a separate test D1 database and dedicated staging Pages project — recommended; do not reuse production D1 or production Pages.
3. Use GitHub App installation credentials restricted to test workflow/branch operations — recommended over a broad personal access token.
4. Permit successful stage 9 merge only into `test-mode/integration`, never `main` — recommended.
5. Keep Mode C strictly read-only and separate from the ten-stage Run All sequence — required safety boundary.

**No application code, workflow, database, branch, deployment, or production configuration is changed by this design document. Implementation begins only after Owner approval of this design and the required environment/credential prerequisites.**
