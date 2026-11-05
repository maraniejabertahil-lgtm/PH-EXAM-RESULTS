# Phase 3 — Automated Broadcasting

## Delivery boundary

The broadcaster is a post-deployment notification component. It does not extract records, approve a batch, merge a dataset PR, or deploy the website. It can run only after the **Deploy Cloudflare Pages** workflow completes successfully.

The workflow additionally checks the deployed commit for changed result `manifest.json` files under `public/data/`. A successful code-only deployment does not send an announcement.

## Channels

- **Facebook Pages:** publishes a Page feed post through the Meta Graph API.
- **Telegram:** sends a message through the Telegram Bot API.

Each message identifies the authority, examination, year, and public search URL. No passer names or personal records are included in the announcement.

## Required repository configuration

Set these GitHub Actions secrets:

| Secret | Purpose |
|---|---|
| `FACEBOOK_PAGE_ID` | The school/platform Facebook Page ID |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | Page access token with permission to publish Page posts |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Destination group/channel/chat ID |

Set these GitHub Actions variables:

| Variable | Purpose |
|---|---|
| `PUBLIC_SITE_URL` | Canonical public HTTPS website URL |
| `FACEBOOK_GRAPH_API_VERSION` | Supported Meta Graph API version, in `vNN.N` format |

The workflow also uses the repository-provided `GITHUB_TOKEN` with `contents: write` to maintain its delivery ledger. Do not place provider tokens in source files, workflow YAML, public assets, or the ledger.

## Idempotency and recovery

The delivery ledger is stored in `.github/broadcast-ledger.json` on the separate `automation/broadcast-ledger` branch, not on the Pages deployment branch. The workflow serializes ledger updates.

- `sent`: the channel is skipped on a rerun.
- `failed`: the provider returned a definite rejection; a later run may retry.
- `pending`: delivery outcome is uncertain (for example, a timeout after request submission). The system stops and requires owner reconciliation instead of risking a duplicate post.

The ledger contains event IDs, route identifiers, statuses, and provider post/message IDs only. It must never contain access tokens or passer data.

## Current verification boundary

The broadcaster has offline unit coverage for route filtering, deployment gating, provider request construction, provider confirmations, and duplicate-send prevention. Real provider connectivity is not verified until the Owner configures the required secrets/variables and the final Live Acceptance Test is run.

The deployment workflow name is deliberately fixed as `Deploy Cloudflare Pages`. Phase 4 must use that exact workflow name so the `workflow_run` trigger connects correctly.
