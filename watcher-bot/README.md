# PH-EXAM-RESULTS Cloudflare Watcher

This folder implements Phase 1 of the approved Master Technical Blueprint. It is a monitoring Worker only; it does not extract, validate, approve, or publish examination records.

## Behaviour

- Runs from the one-minute Cloudflare Cron Trigger.
- Standard Mode checks each approved source once per invocation.
- Peak Week Mode is enabled by setting the `PEAK_WEEK` KV key to the text value `true`; the Worker performs two scans 30 seconds apart.
- Reads the authorized source registry from `python-engine/config/sources.json` on the configured GitHub ref.
- Checks official sources first for each authority/examination. Verified third-party sources are checked only when configured official sources for that same scope are unavailable; third-party sources are not used when no official source is configured.
- Checks source URLs using HTTPS `HEAD` requests. If a server rejects `HEAD` with HTTP 403, 405, or 501, it retries the same approved URL with a bounded `GET` range (bytes 0–1023); redirects remain HTTPS and same-origin only.
- Scans approved monitored pages for same-origin PDF links when HTTP metadata changes. For PRC listing sources using `track_new_articles_only`, rechecks the bounded article listing on every scheduled scan even when HTTP metadata is unchanged, so newly added articles are not hidden by stable ETag/Last-Modified values.
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

The source registry is maintained in `python-engine/config/sources.json`. Enable a source only after its exact official URL and acquisition policy have been owner-approved. An approved source may optionally include:

```json
{
  "preemptive_url_templates": [
    "https://approved.example.gov.ph/CSE_{MM}{YYYY}_passers.pdf"
  ]
}
```

Only templates on the same HTTPS origin as that source's `url` are accepted. The example above is illustrative, not an approved source URL. Do not add guessed or unapproved sources.

## Local tests

From this folder, run:

```bash
npm test
```

The tests use mocked GitHub and source responses. They do not prove that Cloudflare credentials, the KV namespace, real PRC/CSC source URLs, or the live GitHub webhook are configured.


## Optional official-page Google Drive discovery

A source may opt in to `allow_linked_drive_documents: true` only after its exact HTTPS page URL has been owner-authorized. The Watcher then accepts new Drive IDs only from exact `drive.google.com/file/d/{id}/view` links in that official page's HTML. Each candidate must still pass the existing strict Drive redirect-host, path, and ID checks and the bounded `%PDF-` byte-signature check. The dispatch carries the exact source page URL and `official_page_drive_link` detection method. The GitHub receiver accepts this path only when the page URL exactly matches the enabled, authorized registry entry and the opt-in flag is true. This option remains off by default; the PRC source is the currently enabled official source using this explicit opt-in.


### Bounded official result-article discovery

For an owner-approved official listing page, `discover_official_result_articles: true` enables a bounded same-origin crawl across up to three documented listing pages. The PRC registry currently reads up to ten result-related article links per page and processes no more than three newly posted articles per scheduled scan. Only `/article/` and numeric `/node/{id}` paths are followed; external hosts, query strings, and fragments are rejected. With `track_new_articles_only: true`, the first successful scan snapshots existing article URLs without opening their PDFs; every later scheduled scan rechecks the bounded listing even when HTTP metadata is unchanged, and processes only newly discovered articles. If more than three new articles arrive together, the Watcher processes them in batches and retries the remaining articles on subsequent runs. Article-page Drive links still require `allow_linked_drive_documents: true`, exact Google Drive host/path validation, a verified PDF byte signature, and receiver-side validation of both the registered listing URL and the same-origin article URL. Use `drive_link_text_patterns` to select the intended document label (for example, `list of successful examinees`) when an article contains multiple attachments. Verify the official site's `robots.txt` before enabling this feature.

### PRC release processing

The `prc-release-detected` receiver in `.github/workflows/process-import.yml` attempts bounded HTTPS acquisition of the single official result document. Redirects are limited to approved PRC/Google hosts, response size is capped, and a PDF URL returning HTML (including a sign-in or consent page) is rejected. Automatic normalization requires an exam/level/format entry in `python-engine/config/adapter_mappings.json`; ambiguous links, missing counts, disabled exam-specific sources, unsupported layouts, or any Greenlight failure stop the run without creating a publication batch.

Only a batch that passes ingestion checks is sent to the existing Python Greenlight/GitOps pipeline. The publisher remains fail-closed and can publish only through its validated dataset PR/CI path. A configured exam-specific source overrides the general PRC listing source, so a disabled exam cannot be acquired through the general listing. The current CPALE Drive list remains disabled because its ordinary public route presented a sign-in page; no authentication, CAPTCHA, or access-control workaround is attempted. With no reviewed CPALE PDF mapping, the system cannot yet publish that exam automatically.

This improves the processing path but does not change the one-minute Worker schedule or prove a production run. "Second after PRC" timing is not guaranteed by the current polling interval or by a release whose official linked content is not publicly accessible.

### Official PRC future-release schedule discovery

The Watcher also discovers the nearest upcoming PRC target release date from the official examination-schedule index. The authorized registry entry is `PRC-OFFICIAL-SCHEDULE-INDEX` in `python-engine/config/sources.json`.

- Starts at the official PRC schedule index: `https://www.prc.gov.ph/exam-schedules-menu`.
- Discovers only same-origin yearly schedule pages matching the official `/{year}-schedule-examination` path, limited to the current and following Manila calendar year.
- Fetches the same-origin `robots.txt` on each refresh and stops without fetching schedule pages if the index or any discovered schedule path is disallowed or the robots policy cannot be verified.
- Uses disclosed HTTPS GET requests, same-origin redirects only, a 10-second request timeout, a 32 KiB robots limit, and a 1 MiB per-page HTML limit.
- Extracts only the official examination-name and **Target Date of Release of Examination Results** fields needed to identify upcoming dates; it does not collect applicant or passer personal information.
- Deduplicates only rows with the same normalized examination name and the same target release date. Different examinations on the same date, and the same examination with different dates, remain separate.
- Accepts harmless spacing around date punctuation (for example, `October 23 , 2026`) and refuses to publish a nearest date if the expected table structure cannot be identified.
- Calculates date-only countdowns using the Philippines (Asia/Manila, UTC+8) calendar. The public snapshot also records the robots.txt URL, check time, user-agent token, and allowed outcome for transparency. These are PRC **target** dates, not confirmation that results have actually been published.
- Refreshes at most once every six hours and caches the public schedule snapshot in the existing `PEAK_WEEK` KV namespace. A failed refresh preserves the last known-good snapshot.
- Exposes the cached public schedule at `GET /api/releases/upcoming`. The endpoint contains only public schedule data; it does not expose D1 records or secrets. The endpoint returns 503 until the first compliant schedule snapshot has been stored.
- Existing official result-announcement detection and the Python Greenlight/GitOps publication pipeline remain separate and unchanged.

Run the schedule parser and policy tests with:

```bash
node --test tests/release-schedule.test.mjs
npm test
```

Unit tests use mocked PRC responses. They do not prove the live PRC robots policy, live schedule retrieval, Worker deployment, or production endpoint availability; those remain separate acceptance checks.
