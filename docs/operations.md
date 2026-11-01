# PH-EXAM-RESULTS operations

## Current safe operating state

The public catalogue is empty. The source registry and examination prediction configuration are empty. No result is presented as live or official until a verified batch is owner-approved and merged.

## GitHub Actions workflows

| Workflow | Purpose |
|---|---|
| 1 - Monitor Approved Sources | Checks configured sources every two hours; with D1 configured, it can detect changes, acquire approved CSV/PDF files, process them, and propose a PR |
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

GitHub Actions uses its automatically supplied `GITHUB_TOKEN` for PR creation and branch pushes. Do not copy it into source files.

These secrets and Cloudflare resources have not been configured or verified by this implementation.

### D1 Free-plan guardrails

Cloudflare's current published Free limits include a 500 MB maximum per database, 5 GB total D1 storage per account, 5 million rows read per day, and 100,000 rows written per day. The weekly maintenance workflow reports the selected database's size against the 500 MB per-database reference. Public visitor searches do not query D1, which keeps public search traffic away from the D1 daily row limits. If a daily read/write limit is reached, D1 queries fail until the daily reset; if the storage ceiling is reached, further writes and schema changes can fail. Keep D1 limited to internal operational metadata.

## Configure source monitoring

1. Confirm the official source and that the intended access method is authorized.
2. Add an entry to `python-engine/config/sources.json`.
3. Include a unique ID, authority, exam identifier, source type, HTTPS URL, enabled flag, and authorization flag.
4. Keep `auto_acquire` false until a direct file URL and format have been tested.
5. For CSV, verify the `name` column and optional `rating`, `region`, and `seq` columns.
6. For PDF, expect text extraction only and manual review.
7. Add a third-party source only after owner verification. It is used only when configured official sources for that authority/exam are unavailable.
8. Enable automatic acquisition only after the source and sample file are verified.

The registry is currently empty. Do not add guessed URLs or scrape a site without permission.

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

Only CSV is accepted by the current automated import workflow.

## PDF handling

For an iPad-friendly workflow, place the PDF inside `private-imports/`, then run **2B - Extract PDF Text for Manual Review** from GitHub Actions. Download the resulting artifact and manually verify/map the records. The workflow never publishes PDF content or extracted names.

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
