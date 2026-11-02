# PH-EXAM-RESULTS Cloudflare Watcher

This folder implements Phase 1 of the approved Master Technical Blueprint. It is a monitoring Worker only; it does not extract, validate, approve, or publish examination records.

## Behaviour

- Runs from the one-minute Cloudflare Cron Trigger.
- Standard Mode checks each approved source once per invocation.
- Peak Week Mode is enabled by setting the `PEAK_WEEK` KV key to the text value `true`; the Worker performs two scans 30 seconds apart.
- Reads the authorized source registry from `python-engine/config/sources.json` on the configured GitHub ref.
- Checks official sources first for each authority/examination. Verified third-party sources are checked only when configured official sources for that same scope are unavailable; third-party sources are not used when no official source is configured.
- Checks source URLs using HTTPS `HEAD` requests. If a server rejects `HEAD` with HTTP 403, 405, or 501, it retries the same approved URL with a bounded `GET` range (bytes 0–1023); redirects remain HTTPS and same-origin only.
- When a monitored page's HTTP metadata changes, scans the page for same-origin PDF links and checks those links.
- During Peak Week, expands owner-configured `preemptive_url_templates` for the current and following UTC month. Supported placeholders: `{EXAM}`, `{YYYY}`, `{YY}`, `{MM}`, and `{YYYYMM}`.
- Dispatches GitHub `repository_dispatch` only after a candidate passes the PDF byte check. Every direct PDF candidate, including same-origin page links and Peak Week preemptive URLs, must return a bounded first-kilobyte response containing the `%PDF-` signature before dispatch.
- An owner-approved Google Drive ID is not treated as proof of PDF content. Its download is followed manually for at most five redirects, only over HTTPS, only on `drive.google.com` or the exact `drive.usercontent.google.com` download host, and only while the exact approved file ID remains in the redirect URL. The final bounded response must contain the `%PDF-` signature. Any other host, path, ID, or unverified response is held for manual review and is not dispatched.
- Uses KV to remember source metadata and successfully dispatched PDF URLs, preventing repeated dispatches. A failed or unverified candidate is not marked as dispatched.
- Rejects cross-origin redirects for CSC/source pages and arbitrary PDF links. The sole cross-origin exception is the narrow, exact-host Google Drive download route described above; it cannot be used for general external links.
- Counts both outbound HTTP requests and KV operations, then stops at 45 total subrequests per invocation to leave headroom below the Workers Free limit of 50.

## Required Cloudflare setup

Run these commands in the GitHub Codespaces terminal from this folder:

```bash
cd watcher-bot
npx wrangler login
npx wrangler kv namespace create PH_EXAM_RESULTS_WATCHER --binding PEAK_WEEK --update-config
```

The last command creates the KV namespace and updates `wrangler.toml` with its real namespace ID. Keep that updated configuration; the namespace ID is not a secret.

Create a fine-grained GitHub personal access token limited to this repository, with **Contents: Read and write**. Read is used for the source registry; write is required by GitHub's repository-dispatch endpoint. Do not paste the token into chat or save it in a repository file.

Deploy the Worker, then enter the token when Wrangler prompts:

```bash
npx wrangler deploy
npx wrangler secret put GITHUB_TOKEN
```

Confirm the Worker is deployed, the one-minute Cron Trigger is visible, and its logs show successful registry reads. New Cron Trigger changes can take several minutes to propagate.

To enable Peak Week Mode only when approved source entries are configured:

```bash
npx wrangler kv key put --binding=PEAK_WEEK PEAK_WEEK true --remote
```

Return to Standard Mode with:

```bash
npx wrangler kv key put --binding=PEAK_WEEK PEAK_WEEK false --remote
```

Do not put the GitHub token in `wrangler.toml`, source code, or GitHub files. The Worker secret must be configured with Wrangler's secret command.

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


## Optional official-page Google Drive discovery

A source may opt in to `allow_linked_drive_documents: true` only after its exact HTTPS page URL has been owner-authorized. The Watcher then accepts new Drive IDs only from exact `drive.google.com/file/d/{id}/view` links in that official page's HTML. Each candidate must still pass the existing strict Drive redirect-host, path, and ID checks and the bounded `%PDF-` byte-signature check. The dispatch carries the exact source page URL and `official_page_drive_link` detection method. The GitHub receiver accepts this path only when the page URL exactly matches the enabled, authorized registry entry and the opt-in flag is true. The option is off by default and is not enabled in production by this change.


### Bounded official result-article discovery

For an owner-approved official listing page, `discover_official_result_articles: true` enables a bounded same-origin crawl of at most three result-related article links. Only `/article/` and numeric `/node/{id}` paths are followed; external hosts, query strings, and fragments are rejected. Article-page Drive links still require `allow_linked_drive_documents: true`, exact Google Drive host/path validation, a verified PDF byte signature, and receiver-side validation of both the registered listing URL and the same-origin article URL. Use `drive_link_text_patterns` to select the intended document label (for example, `list of successful examinees`) when an article contains multiple attachments. Verify the official site's `robots.txt` before enabling this feature, and keep `scan_page_on_baseline: false` when existing historical articles must not be dispatched on initial setup.
