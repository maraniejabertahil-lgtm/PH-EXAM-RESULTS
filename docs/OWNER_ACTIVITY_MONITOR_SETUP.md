# Private Owner Activity Dashboard — Setup

## What this adds

A separate Cloudflare Pages project hosts the owner-only activity timeline. It is not part of the public results website and does not change the public site's routes, headers, search code, or deployment.

The dashboard shows individual operational events with timestamps, component, operation, status, duration, execution ID, and available failure details. Related events share an execution ID.

## Privacy and security

- Deploy the dashboard to a **separate Pages project and hostname** (for example, a project named `ph-exam-owner-dashboard`).
- Protect the entire dashboard hostname with Cloudflare Access. The Allow policy must contain only the Owner's exact email address.
- The dashboard API independently verifies the Access JWT signature, issuer, audience, expiry, and exact `OWNER_EMAIL`.
- The API uses a separate D1 Read token. D1 Write credentials are used only by trusted server-side writers.
- Public search remains static-first and browser-local. No examinee names, result rows, or raw visitor search queries are written to D1.
- The public website's browser-side error messages were fixed separately and remain local to the visitor's browser. Anonymous browser error ingestion is not added because it would create a public write path.

## 1. Create the private Pages project

In Cloudflare, create a new Pages project dedicated to the owner dashboard. Do not reuse the public results Pages project or its hostname.

Choose a separate project name, such as `ph-exam-owner-dashboard`. Record the exact project name and its `*.pages.dev` hostname.

## 2. Protect the entire dashboard hostname

In **Zero Trust → Access → Applications**, create a Self-hosted application for the entire new dashboard hostname, for example:

`https://ph-exam-owner-dashboard.pages.dev/*`

Create an Allow policy containing only the Owner's exact sign-in email. Do not use Everyone or a whole email-domain rule.

The dashboard API also verifies the exact owner email. If Access settings or identity configuration are missing, the API fails closed and returns no activity data.

## 3. Create D1 and API tokens

1. In **Workers & Pages → D1 SQL Database**, create a database, for example `ph-exam-results-operations`. Record its database UUID.
2. Create a Cloudflare API token with **Account / D1 / Write** permission for trusted writers.
3. Create a separate Cloudflare API token with **Account / D1 / Read** permission for the private dashboard.
4. Create a Cloudflare Pages deployment token with permission to deploy Pages projects.

The schema and client use the Cloudflare D1 REST API. No direct SQL driver or public browser database query is introduced.

## 4. Configure GitHub Actions secrets

Add these repository secrets:

- `CF_D1_API_TOKEN` — D1 Write token
- `CF_ACCOUNT_ID` — Cloudflare account ID
- `CF_D1_DATABASE_ID` — D1 database UUID
- `CF_PAGES_API_TOKEN` — Cloudflare Pages deployment token
- `CF_OWNER_PAGES_PROJECT_NAME` — exact separate owner dashboard Pages project name

Add this repository variable only after the private Pages project and Access policy are ready:

- `CF_OWNER_DASHBOARD_ENABLED` = `true`

The dashboard deployment job remains disabled until that variable is enabled. You can also run **Deploy Private Owner Dashboard** manually from Actions on `main`.

## 5. Configure the production Watcher

Set these in the Cloudflare Watcher Worker:

- `CF_D1_API_TOKEN` — secret, D1 Write token
- `CF_ACCOUNT_ID` — variable
- `CF_D1_DATABASE_ID` — variable

The Watcher batches its activity records into one D1 REST request per scheduled invocation so monitoring does not consume one Worker subrequest per event.

## 6. Configure the private Pages project

In the separate owner dashboard Pages project, add these production environment variables/secrets:

- `CF_D1_READ_API_TOKEN` — secret, separate D1 Read token
- `CF_ACCOUNT_ID` — variable
- `CF_D1_DATABASE_ID` — variable
- `CF_ACCESS_TEAM_DOMAIN` — Zero Trust team domain, without `https://`
- `CF_ACCESS_AUD` — audience tag of the Access application
- `OWNER_EMAIL` — exact Owner email allowed by the Access policy

Do not add the D1 Read token until the Access application and its owner-only policy are active.

## 7. Run the D1 migration

After adding the GitHub D1 Write secrets, open **Actions → Migrate Private Activity Monitor D1 → Run workflow** on `main`.

The migration creates or upgrades these tables:

- `monitoring_logs` — per-operation activity timeline and diagnostics
- `import_batches` — acquisition and Greenlight batch history
- `release_predictions` — release prediction metadata

The migration is additive and checks existing table columns before adding missing fields. It is compatible with the earlier private-activity metadata schema and preserves existing records.

## 8. Deploy and verify

1. Confirm the private Pages project and its Access policy are configured.
2. Set `CF_OWNER_DASHBOARD_ENABLED=true`.
3. Run **Deploy Private Owner Dashboard** from Actions on `main`.
4. Open the separate `*.pages.dev` dashboard hostname while signed in as the Owner.
5. Run a Watcher scheduled check and a Python processing workflow.
6. Confirm each operation appears as an individual activity and related events share an execution ID.
7. Open the dashboard signed out or with another email; it must be blocked.
8. Confirm the public results website still opens without login and its search remains unchanged.

## Browser-side errors: current boundary

The public website now displays safe user-facing error messages and diagnostic references. Those browser errors are not centrally collected. Sending errors from anonymous visitors to D1 would require a separate, explicitly approved, rate-limited ingestion design. The current implementation does not create that public write endpoint.
