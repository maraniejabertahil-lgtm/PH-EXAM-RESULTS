# Private operational metadata

This package writes operational metadata to Cloudflare D1 using the Cloudflare REST API only. It does not use a SQL driver. Never store examinee names, search terms, result rows, passwords, tokens, or raw exception details.

## Separate private Pages project

The owner dashboard is deployed as a separate Cloudflare Pages project from the public search website. The dedicated project contains only the private dashboard, so enabling Cloudflare Access for that entire project does not restrict the public results website.

- Recommended project name: ph-exam-results-owner
- Static output directory: owner-dashboard/public
- Pages Functions directory: owner-dashboard/functions
- Dashboard route: /
- API route: /api/activity

Create the dedicated Pages project in Cloudflare, then enable its Pages Access policy under Workers & Pages > the private project > Settings. The Access policy must allow only the Owner identity. Protect the project's pages.dev hostname and its preview deployments. Do not enable Access on the existing public search Pages project.

The Pages Function independently verifies the Cloudflare Access JWT signature/JWKS, issuer, audience, and expiry before querying D1. Configure these Pages project variables:
- CF_ACCESS_TEAM_DOMAIN — the HTTPS Cloudflare Access team issuer, without a trailing slash
- CF_ACCESS_AUD — the Access application's audience tag
- CF_ACCOUNT_ID
- CF_D1_DATABASE_ID

Configure the Pages project secret:
- CF_D1_READ_TOKEN — a Cloudflare API token limited to D1 read access for this database

## D1 database and write credentials

Create one Cloudflare D1 database for internal metadata only. Configure these GitHub Actions repository secrets:
- CF_ACCOUNT_ID
- CF_D1_DATABASE_ID
- CF_D1_API_TOKEN — D1 edit access scoped to the required database operations
- CF_OWNER_PAGES_PROJECT_NAME — the dedicated private Pages project name (recommended: ph-exam-results-owner)

Configure the Watcher Worker variables CF_ACCOUNT_ID and CF_D1_DATABASE_ID, and the Worker secret CF_D1_API_TOKEN. Watcher logging is best-effort; D1 failures never stop source monitoring.

When the D1 credentials are absent, optional Python activity logging is disabled. Partial configuration produces a safe warning and does not block result processing.

## Schema setup

After the D1 database and GitHub secrets are configured and the initializer workflow is merged, run Actions > Initialize private D1 activity schema > Run workflow. It applies the versioned schema using the Cloudflare REST API. The migration creates only monitoring_logs, import_batches, and release_predictions.

## Data boundary

D1 stores timestamps, source identifiers, exam metadata, Greenlight counts/scores, publication states, and release-prediction metadata. It never stores examinee names or the public result dataset. The public search site does not call D1.
