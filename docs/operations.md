# PH-EXAM-RESULTS operations

## Current safe operating state

The public catalogue is empty. The source registry and examination prediction configuration are empty. No result is presented as live or official until a verified batch is owner-approved and merged.

## Enforce owner approval before publication

The automation creates Pull Requests and never merges them. However, the repository's `main` branch protection settings have not been verified. Until the owner configures GitHub to require an approved Pull Request review and prevent direct pushes that bypass review, owner approval is a documented operating rule rather than a technically enforced control.

Before production use, open **Settings → Branches** (or the repository rulesets page), configure protection for `main`, require a Pull Request review, and ensure the owner/reviewer policy matches the publication approval process. Do not treat the approval gate as enforced until the setting is visibly confirmed in GitHub.

## GitHub Actions workflows

| Workflow | Purpose |
|---|---|
| 1 - Manual Source Check (Owner Diagnostic) | Manually runs the legacy Python metadata check; no scheduled trigger remains |
| Cloudflare Watcher | Runs scheduled source monitoring every minute; Peak Week checks twice 30 seconds apart and sends `source-detected` repository dispatch events |
| Process Detected Source and Manual Drop | Validates Watcher events against the owner-approved registry and invokes the Phase 2 Python PDF review bridge; manual-drop pushes remain a separate intake path |
| 2 - Process Result Import and Open Approval PR | Manually processes an owner-supplied CSV in `private-imports/` |
| 2B - Extract PDF Text for Manual Review | Extracts text from a private PDF and stores a review artifact; does not publish results |
| 3 - Deploy Public Site to Cloudflare Pages | Validates and deploys the approved `public/` directory |
| 4 - Weekly Maintenance | Runs tests, checks public dataset hashes/sizes, and checks D1 storage when configured |
| 5 - Set Preparing or Searching Mode | Creates a PR to change public homepage mode using predefined stages |
| 6 - Update Release Predictions | Updates configured examination predictions every six hours |

## Required GitHub secrets

D1:
- `CF_API_TOKEN`: Cloudflare API token with D1 Read and Write permissions required by the implemented operations.
- `CF_ACCOUNT_ID`: Cloudflare account ID.
- `D1_DATABASE_ID`: D1 database ID.

Cloudflare Pages:
- `CF_PAGES_API_TOKEN`: token with Pages deployment permission.
- `CF_ACCOUNT_ID`: Cloudflare account ID.
- `CF_PAGES_PROJECT_NAME`: exact existing Pages project name.

GitHub Actions uses its automatically supplied `GITHUB_TOKEN` for PR creation, branch pushes, and dispatching the quality-check workflow on generated result PR branches. The repository setting **Allow GitHub Actions to create and approve pull requests** must be enabled under **Settings → Actions → General → Workflow permissions**; the workflows also declare the required per-workflow permissions. Do not copy the token into source files.

These secrets and Cloudflare resources have not been configured or verified by this implementation. The Watcher separately requires a Cloudflare Worker secret named `GITHUB_TOKEN` and a KV namespace binding named `PEAK_WEEK`; see below.

### D1 Free-plan guardrails

Cloudflare's current published Free limits include a 500 MB maximum per database, 5 GB total D1 storage per account, 5 million rows read per day, and 100,000 rows written per day. The weekly maintenance workflow reports the selected database's size against the 500 MB per-database reference. Public visitor searches do not query D1, which keeps public search traffic away from the D1 daily row limits. If a daily read/write limit is reached, D1 queries fail until the daily reset; if the storage ceiling is reached, further writes and schema changes can fail. Keep D1 limited to internal operational metadata.

## Official source entry-point candidates (not yet authorized in the registry)

These are official starting points identified for owner review only. They are not configured as sources, and this documentation change does not authorize automated acquisition.

- PRC examination-result articles: https://www.prc.gov.ph/articles/exam-results. Individual PRC result articles link to official result documents; the inspected example linked its list of successful examinees through Google Drive. Each direct document URL and its download/redirect behavior must be verified separately before enabling acquisition.
- CSC Examination Portal: https://exam.csc.gov.ph/list_passers.php. The portal exposes official passer-search categories and exam-year links, but its list-of-passers interface is interactive. A monitor-only page check is not equivalent to extracting a complete result dataset.
- CSC examination advisories: https://csc.gov.ph/examination-advisories/. These official notices can identify result-release announcements. For the 09 August 2026 CSE-PPT, CSC Region V published the official results page https://www.csc.gov.ph/regional-offices/region-v/examination/results-10072026, which links the Professional and Subprofessional passer-list PDFs hosted on Google Drive: https://drive.google.com/file/d/1jQmBLSU2azhFvCgU6l8m6ljXGDmIRa1l/view?usp=drive_link and https://drive.google.com/file/d/1qYaCbxIZ_6DHyMD9FhgZdj-YtbIJh5Wf/view?usp=drive_link. The CSC page is an official source; the linked files are cross-origin and require a separately tested, explicitly approved Google Drive acquisition route.

Do not enable `auto_acquire` for these index pages. The source registry remains empty until the owner approves each precise source and its supported acquisition method. The downloader follows only same-host, same-port HTTPS redirects and rejects cross-origin redirects before following them. Some PRC Google Drive attachments may redirect to a different Google host; those must remain manual-download/manual-review inputs unless a compliant direct-download route is verified.

## Cloudflare Watcher setup (Phase 1)

1. Confirm the existing `PEAK_WEEK` KV namespace ID in `watcher-bot/wrangler.toml` matches the intended Cloudflare account. Do not replace it with a placeholder.
2. Set a Cloudflare Worker secret named `GITHUB_TOKEN`. Use a fine-grained GitHub token limited to this repository with **Contents: Read and write** permission. Read is needed to load the private source registry; write is needed for the repository-dispatch endpoint.
3. Confirm `GITHUB_REPOSITORY`, `GITHUB_SOURCE_REF`, and `GITHUB_SOURCE_PATH` in `wrangler.toml`.
4. From the `watcher-bot/` folder, authenticate Wrangler to the intended Cloudflare account and deploy the Worker.
5. Confirm the one-minute Cron Trigger appears in the Worker dashboard and inspect its invocation logs.
6. Set the KV key `PEAK_WEEK` to the text value `true` to enable Peak Week Mode; set it to `false` to return to Standard Mode.
7. Do not call Phase 1 live until a real owner-approved source is configured and a real PDF detection reaches the GitHub Actions receiver.

The GitHub receiver and Phase 2 Python bridge are on the implementation PR branch. GitHub `repository_dispatch` workflows must exist on the repository's default branch to run. Therefore, the live webhook-to-Python path cannot be verified until the reviewed implementation is merged into `main`. No merge or deployment is performed by these code changes.

The Watcher uses a maximum of 45 outbound subrequests per scheduled invocation to stay below the Workers Free subrequest limit. It does not monitor any source while the registry is empty.

## Configure source monitoring

1. Confirm the official source and that the intended access method is authorized.
2. Add an entry to `python-engine/config/sources.json`.
3. Include a unique ID, authority, exam identifier, source type, HTTPS URL, enabled flag, and authorization flag.
4. If preemptive checking is needed, add owner-approved `preemptive_url_templates` that expand only on the same HTTPS origin. Supported placeholders are `{EXAM}`, `{YYYY}`, `{YY}`, `{MM}`, and `{YYYYMM}`; the Worker checks the current and next UTC month during Peak Week.
5. Keep `auto_acquire` false until a direct file URL and format have been tested.
6. For CSV, verify the `name` column and optional `rating`, `region`, and `seq` columns.
7. For PDF, expect text extraction only and manual review.
8. Add a third-party source only after owner verification. It is used only when configured official sources for that authority/exam are unavailable.
9. Enable automatic acquisition only after the source and sample file are verified.

The source registry contains one owner-approved CSC Region V entry for the 09 August 2026 CSE-PPT result page. A one-time owner-approved live smoke test can verify the two Drive downloads and text extraction; it uploads the original PDFs and review JSON together as a private seven-day artifact; it does not publish passer records. Its Google Drive acquisition is restricted to the two exact file IDs linked from that official page. The Watcher scans the page on its first baseline and dispatches only those exact IDs. The Python bridge accepts only the constructed `drive.google.com/uc?export=download&id=...` URL for an ID in that source entry. Redirects are limited to HTTPS Google download host families, the download is capped at 50 MiB, and the resulting PDF must pass the PDF signature check. The artifact is private and retained for seven days for manual review only. This branch configuration is not active in production until the reviewed code is merged and the Worker is deployed.


## Phase 2 Watcher-to-Python PDF review bridge

The implementation branch now contains `python-engine/scraper/event_processor.py` and a `process-import.yml` receiver that connects a validated `source-detected` event to the Python engine.

- The event must match exactly one enabled, owner-authorized registry source and its authority/exam.
- The detected document must be identified as a PDF and remain on the exact approved HTTPS origin.
- The bridge downloads only when `auto_acquire: true`; otherwise it records that owner acquisition approval is still required and does not download.
- Downloaded content is checked for a PDF signature, size-limited by the existing downloader, SHA-256 hashed, and text-extracted.
- The output is a short-lived GitHub Actions review artifact. It is not a passer dataset, is not OCR, and is never published automatically.
- The owner-approved CSC Region V source entry authorizes only the two exact Google Drive file IDs linked from the official page. The Watcher discovers those IDs from the official page and dispatches a constructed Drive download URL; it does not accept arbitrary Drive links.
- The Python bridge checks the exact approved file ID and download route, allows redirects only to HTTPS Google download host families, checks the PDF signature, enforces the 50 MiB cap, and extracts text only for a private manual-review artifact. It does not OCR, parse passer records, or publish.
- The source registry and receiver changes are on the implementation branch. Repository-dispatch processing cannot be live until the receiver workflow is on the default branch, and the Worker must separately be deployed with the approved source registry reference.

## Manual CSV import

1. Keep the repository private.
2. Place the authorized CSV inside `private-imports/`.
3. Open GitHub Actions.
4. Run **2 - Process Result Import and Open Approval PR**.
5. Supply the file path, authority, examination identifier, year, and source reference.
6. Enter the actual official release date if known.
7. Enable replacement only when intentionally replacing a complete existing examination/year dataset.
8. Review the generated PR, source SHA-256, validation counts, and duplicate report.
9. Exact duplicates block publication PR creation. Resolve them in the source CSV and reprocess.
10. Merge only after confirming the official source and the entire batch.

Only CSV is accepted by the current automated import workflow. Headers are normalized for case/spacing, but blank or duplicate headers and rows containing extra unlabelled values are rejected rather than silently discarded. Manual CSV and PDF workflow inputs are capped at 50 MiB each.

## PDF handling

For an iPad-friendly workflow, place a PDF of no more than 50 MiB inside `private-imports/`, then run **2B - Extract PDF Text for Manual Review** from GitHub Actions. Download the resulting artifact and manually verify/map the records. The workflow never publishes PDF content or extracted names.

The equivalent local command extracts text from text-based PDFs:

```bash
cd python-engine
python main.py extract-pdf --input ../private-imports/source.pdf --output ../artifacts/pdf-extraction.json
```

Its output is not a passer dataset. Scanned PDFs and uncertain layouts require manual conversion/review before CSV import.

## Preparing Mode

Run **5 - Set Preparing or Searching Mode** in GitHub Actions.

For Preparing Mode, provide authority, examination identifier, year, public display name, and the actual workflow stage. The percentage is fixed by the stage and cannot be typed freely.

For normal homepage mode, select Searching.

The workflow opens a PR. The public site changes only after merge and successful Pages deployment. The scheduled prediction workflow does not yet automatically activate Preparing Mode.

Manual source diagnostics, manual CSV imports, and homepage-status changes share one GitHub Actions concurrency group so they do not prepare conflicting owner-review PRs at the same time. Scheduled source monitoring is handled by the Cloudflare Watcher, not GitHub Actions.

## Release predictions

Add only verified examination categories to `python-engine/config/examinations.json`. Predictions require sufficient actual release dates stored in D1. The scheduled workflow updates predictions every six hours; scheduled Actions may be delayed and are not a real-time scheduler.

## Tests and validation

```bash
python -m pip install -r python-engine/requirements.txt
cd python-engine
python -m unittest discover -s tests -v
cd ..
python python-engine/maintenance.py
node tests/search-worker.test.mjs
```

The Node test exercises the browser Web Worker search logic against 50,000 synthetic rows. It is a code-path performance check, not a browser rendering or concurrent-visitor load test. The maintenance script verifies the public manifest, file paths, dataset hashes, record counts, row shape, and 10 MiB shard cap.

## Deployment

The Pages deployment workflow requires an existing Cloudflare Pages project and the listed GitHub secrets.

Cloudflare Pages output directory: `public`. No build command is required.

If credentials are missing, deployment cannot complete. The workflow must fail clearly rather than claim that the website was published.

## Recovery

- Invalid CSV batches do not create a publication PR.
- Exact duplicate candidates block PR creation.
- Fuzzy candidates are shown for owner review and are never automatically removed.
- Existing datasets are not replaced unless the owner explicitly enables replacement.
- Invalid JSON, incorrect hashes, or oversized shards block deployment.
- If a bad data PR is merged and deployed, use GitHub Revert on the merge commit; the restored main contents can then be redeployed.
- If D1 or monitoring fails, keep the last verified public dataset.
