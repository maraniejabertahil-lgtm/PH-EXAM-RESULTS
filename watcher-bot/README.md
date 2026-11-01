# PH-EXAM-RESULTS Cloudflare Watcher

This folder implements Phase 1 of the approved Master Technical Blueprint. It is a monitoring Worker only; it does not extract, validate, approve, or publish examination records.

## Behaviour

- Runs from the one-minute Cloudflare Cron Trigger.
- Standard Mode checks each approved source once per invocation.
- Peak Week Mode is enabled by setting the `PEAK_WEEK` KV key to the text value `true`; the Worker performs two scans 30 seconds apart.
- Reads the authorized source registry from `python-engine/config/sources.json` on the configured GitHub ref.
- Checks source URLs using HTTPS `HEAD` requests. A `GET` with a one-byte range is used only when a server rejects `HEAD` with HTTP 405 or 501.
- When a monitored page's HTTP metadata changes, scans the page for same-origin PDF links and checks those links.
- During Peak Week, expands owner-configured `preemptive_url_templates` for the current and following UTC month. Supported placeholders: `{EXAM}`, `{YYYY}`, `{YY}`, `{MM}`, and `{YYYYMM}`.
- Dispatches GitHub `repository_dispatch` event type `source-detected` only after a PDF candidate returns a successful HTTP response.
- Uses KV to remember source metadata and successfully dispatched PDF URLs, preventing repeated dispatches.
- Rejects cross-origin redirects and cross-origin PDF links. Those sources require a separately verified/manual route.
- Caps outbound subrequests at 45 per scheduled invocation to stay below the Workers Free subrequest ceiling.

## Required Cloudflare setup

1. Create one Workers KV namespace, for example `PH_EXAM_RESULTS_WATCHER`.
2. Copy its namespace ID into `wrangler.toml`, replacing `REPLACE_WITH_CLOUDFLARE_KV_NAMESPACE_ID`.
3. Set the Worker secret `GITHUB_TOKEN` to a fine-grained token for this repository with **Contents: Read and write**. Read is used for the source registry; write is required by GitHub's repository-dispatch endpoint.
4. Confirm `GITHUB_REPOSITORY`, `GITHUB_SOURCE_REF`, and `GITHUB_SOURCE_PATH` in `wrangler.toml`.
5. Deploy from this folder with Wrangler after authenticating to the correct Cloudflare account.
6. Confirm the one-minute Cron Trigger is visible in the Worker dashboard.

Do not put the GitHub token in `wrangler.toml`, source code, or GitHub files.

## Source registry additions

The existing registry remains empty until the owner approves exact source URLs. An approved source may optionally include:

```json
{
  "preemptive_url_templates": [
    "https://approved.example.gov.ph/CSE_{MM}{YYYY}_passers.pdf"
  ]
}
```

Only templates on the same HTTPS origin as that source's `url` are accepted. The example above is illustrative, not an approved PRC/CSC URL. Do not add guessed or unapproved sources.

## Local tests

From this folder, run:

```bash
npm test
```

The tests use mocked GitHub and source responses. They do not prove that Cloudflare credentials, the KV namespace, real PRC/CSC source URLs, or the live GitHub webhook are configured.
