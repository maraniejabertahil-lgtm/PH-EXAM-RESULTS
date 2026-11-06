# Private Owner Activity Monitor — Setup

## Security and architecture

- Public search remains static-first and browser-local.
- No browser-side search query, examinee name, or anonymous client event is sent to D1. This preserves the Master Blueprint's rule that the public site has no write path.
- Only trusted server-side components (Cloudflare Watcher, Python/GitHub Actions) write sanitized operational events through the Cloudflare D1 REST API.
- The owner dashboard and its API are protected by Cloudflare Access and a server-side Access JWT check that allowlists the exact OWNER_EMAIL.
- D1 credentials never appear in public assets.

## Required Cloudflare resources

Create one D1 database named \`ph-exam-results-operations\`. Record its database UUID.

Create a dedicated Cloudflare Account API token with Account / D1 / Edit permission for trusted writers. Create a second token with Account / D1 / Read permission for the Pages dashboard. Do not reuse the Pages deployment token or the read-only diagnostics token for writes.

## Required GitHub Actions secrets

- \`CF_D1_API_TOKEN\` — dedicated D1 Edit token
- \`CF_ACCOUNT_ID\` — existing Cloudflare account ID
- \`CF_D1_DATABASE_ID\` — new D1 database UUID

## Required Cloudflare Worker secrets

Set the same three names in the production Watcher Worker:
- \`CF_D1_API_TOKEN\`
- \`CF_ACCOUNT_ID\`
- \`CF_D1_DATABASE_ID\`

## Required Cloudflare Pages environment variables/secrets

Set these for the production Pages project:
- \`CF_D1_API_TOKEN\` (secret)
- \`CF_ACCOUNT_ID\`
- \`CF_D1_DATABASE_ID\`
- \`CF_ACCESS_TEAM_DOMAIN\` (your Zero Trust team domain without https://)
- \`CF_ACCESS_AUD\` (the Access application's audience tag)
- \`OWNER_EMAIL\` (the exact owner sign-in email)

## Cloudflare Access

Create a Self-hosted Access application for the Pages hostname and protect both paths:
- \`/owner-monitor/*\`
- \`/api/owner/*\`

Create an Allow policy that includes only the owner's exact email address. Do not use an Everyone policy or an email-domain-wide rule. Keep the public homepage outside this protected path.

If using the Pages \`pages.dev\` hostname, enable the Pages Access policy first, then configure the application hostname and path rules. If the project also has a custom domain, protect the custom domain separately.

## Apply the schema

After the D1 database and GitHub secrets exist, run:

\`\`\`bash
python python-engine/database/d1_client.py migrate
\`\`\`

The migration is idempotent. It creates \`monitoring_logs\`, \`import_batches\`, and \`release_predictions\` plus activity indexes.

## Browser-side errors

The public search UI reports a safe user-facing diagnostic reference and writes technical detail only to that browser's developer console. It does not transmit client-side errors to D1 because the approved public architecture has no anonymous write endpoint. To centrally collect anonymous visitor browser errors, the Owner must explicitly approve a narrow, rate-limited diagnostic-ingestion exception to the Master Blueprint.

## First verification

1. Confirm the migration created all three tables.
2. Run a Watcher scheduled check and a GitHub processing workflow.
3. Open \`/owner-monitor/\` while signed in as the owner.
4. Confirm the timeline shows events and events sharing an execution ID can be correlated.
5. Open the same URL signed out and confirm it is inaccessible.
6. Confirm no D1 token, owner email, or Access audience appears in \`public/\`.
