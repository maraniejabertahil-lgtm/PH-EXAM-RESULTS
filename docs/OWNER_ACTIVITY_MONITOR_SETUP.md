# Private Owner Activity Monitor — Setup

## Security and architecture

- Public search remains static-first and browser-local.
- No browser-side search query, examinee name, or anonymous client event is sent to D1. This preserves the Master Blueprint's rule that the public site has no write path.
- Trusted server-side components (Cloudflare Watcher, Python, and GitHub Actions) write sanitized operational events through the Cloudflare D1 REST API.
- The owner dashboard and API are protected by Cloudflare Access plus server-side JWT verification that allowlists the exact `OWNER_EMAIL`.
- D1 credentials never appear in public assets.

## Required Cloudflare resources

1. Open **Workers & Pages > D1 SQL Database** and create a database named `ph-exam-results-operations`. Record its database UUID.
2. In **My Profile > API Tokens**, create a custom token with **Account / D1 / Write** permission for trusted writers.
3. Create a second custom token with **Account / D1 / Read** permission for the Pages dashboard. Keep the read-only token separate.

## Required GitHub Actions secrets

- `CF_D1_API_TOKEN` — dedicated D1 Write token
- `CF_ACCOUNT_ID` — Cloudflare account ID
- `CF_D1_DATABASE_ID` — new D1 database UUID

## Required Cloudflare Worker variables/secrets

Set these in the production Watcher Worker:
- `CF_D1_API_TOKEN` — secret, D1 Write token
- `CF_ACCOUNT_ID` — variable
- `CF_D1_DATABASE_ID` — variable

## Required Cloudflare Pages production variables/secrets

- `CF_D1_READ_API_TOKEN` — secret, separate D1 Read token
- `CF_ACCOUNT_ID` — variable
- `CF_D1_DATABASE_ID` — variable
- `CF_ACCESS_TEAM_DOMAIN` — Zero Trust team domain without `https://`
- `CF_ACCESS_AUD` — Access application's audience tag
- `OWNER_EMAIL` — exact owner sign-in email

## Cloudflare Access

In **Zero Trust > Access > Applications**, create path-specific Self-hosted applications for the Pages hostname:

- `YOUR-PROJECT.pages.dev/owner-monitor`
- `YOUR-PROJECT.pages.dev/api/owner`

Give each application an Allow policy containing only the owner's exact email address. Do not use Everyone or an email-domain-wide rule.

**Do not protect the entire Pages hostname** if that would require public visitors to sign in. The public homepage and search routes must remain public. Use path-specific Access applications. If Cloudflare does not allow path-specific protection on the project's `pages.dev` hostname in your account, use a dedicated owner subdomain on a domain you control and leave the public Pages hostname unchanged.

The Pages Function middleware independently verifies the Access JWT signature, issuer, audience, expiry, and exact owner email. It fails closed if Access headers or configuration are missing.

## Apply the schema

After creating the database and adding the GitHub Actions secrets, open the repository's **Actions** tab, select **Migrate Private Activity Monitor D1**, and choose **Run workflow** on `main`.

Alternatively, from the repository root run:

```bash
python python-engine/database/d1_client.py migrate
```

The migration is idempotent. It creates `monitoring_logs`, `import_batches`, and `release_predictions` plus activity indexes.

## Browser-side errors

The public search UI now shows a safe user-facing diagnostic reference and a reload action, while keeping technical details in that browser's developer console. It does not transmit client-side errors to D1 because the approved public architecture has no anonymous write endpoint. Central collection of errors from anonymous visitors would require the Owner to explicitly approve a narrow, rate-limited diagnostic-ingestion exception to the Master Blueprint.

## First verification

1. Confirm the migration created all three tables.
2. Run a Watcher scheduled check and a GitHub processing workflow.
3. Open `/owner-monitor/` while signed in as the owner.
4. Confirm the timeline shows events and related events share an execution ID.
5. Open the same URL signed out and confirm it is inaccessible.
6. Confirm no D1 token, owner email, or Access audience appears in `public/`.
