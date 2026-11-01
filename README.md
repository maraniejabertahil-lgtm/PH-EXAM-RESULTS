# PH-EXAM-RESULTS

Python-first, free-only Philippine examination results platform for PRC and CSC.

## Current implementation status

This repository contains the initial implementation of the approved architecture. It is not yet a live results service.

- Searching and Preparing page layouts are preserved in `public/`.
- Public search uses static JSON datasets, a browser Web Worker, and IndexedDB caching.
- Python processes CSV records, extracts text from text-based PDFs, normalizes names, validates records, and flags duplicate candidates.
- Python generates compact array-of-arrays JSON datasets and a SHA-256 manifest.
- The Cloudflare Watcher implementation is included in the current implementation PR for one-minute source monitoring, but it is not deployed yet. GitHub Actions receives `source-detected` events. Phase 1 validates and records the event only; Phase 2 connects Python acquisition/extraction and Greenlight processing.
- GitHub Actions retains manual source diagnostics, manual CSV import, release-prediction updates, Preparing/Search status PRs, tests, maintenance, and Cloudflare Pages deployment workflows.
- Cloudflare D1 REST integration and initial metadata schema are included.
- The official source registry is intentionally empty.
- No official examination records are included.
- No Cloudflare credentials or D1 secrets have been configured or verified in this repository.

**Do not present this site as an official live results database until authorized sources are configured and real result batches have passed owner approval.**

## Architecture

1. Cloudflare Workers monitors only explicitly authorized sources on a one-minute schedule; Peak Week performs two checks 30 seconds apart.
2. When a PDF is detected, the Watcher sends a GitHub `repository_dispatch` event. The Phase 1 receiver validates the event against the owner-approved source registry. Phase 2 will connect the Python processing pipeline.
3. Python performs acquisition, extraction, normalization, validation, duplicate detection, prediction, and public dataset generation.
4. GitHub Actions runs Python on webhook or manually dispatched jobs.
5. Cloudflare D1 stores internal operational metadata only.
6. GitHub Pull Requests are the owner approval gate for result publication.
7. Cloudflare Pages serves the static `public/` directory.
8. JavaScript loads only the selected result shard and searches locally inside a Web Worker.
9. IndexedDB caches verified datasets by path and SHA-256 hash.

Ordinary visitor searches do not call Python, D1, or a Cloudflare Worker.

## Repository layout

- `public/`: Cloudflare Pages static root.
- `public/assets/js/`: frontend, dataset loader, IndexedDB cache, and Web Worker.
- `public/data/`: public manifest, site status, and approved result datasets.
- `watcher-bot/`: Cloudflare source-monitoring Worker, Cron Trigger configuration, and local tests.
- `python-engine/`: Python processing and automation package.
- `python-engine/config/sources.json`: authorized source registry; initially empty.
- `python-engine/config/examinations.json`: prediction targets; initially empty.
- `python-engine/database/schema.sql`: internal D1 schema.
- `python-engine/tests/`: Python unit tests.
- `.github/workflows/`: webhook receiver, manual import, tests, deployment, and maintenance workflows.
- `manual-drop/`: owner-supplied PDF fallback folder; processing is connected in Phase 2.
- `private-imports/`: owner-supplied source files in this private repository; never deployed.
- `docs/`: architecture and operating documentation.
- `tests/search-worker.test.mjs`: 50,000-row Web Worker search performance check.

## Run Python tests locally

Use Python 3.12:

```bash
python -m pip install -r python-engine/requirements.txt
cd python-engine
python -m unittest discover -s tests -v
cd ..
node tests/search-worker.test.mjs
cd watcher-bot
npm test
```

The PDF extractor uses `pdfplumber`. It extracts text only; scanned PDFs and uncertain layouts require manual review. It does not claim perfect automatic passer-name extraction.

## Process a CSV file

The CSV must contain a `name` column. Optional columns are `rating`, `region`, and `seq`.

```bash
cd python-engine
python main.py process \
  --input ../private-imports/example.csv \
  --authority PRC \
  --exam LET \
  --year 2026 \
  --source-reference "OFFICIAL SOURCE URL" \
  --output ../artifacts/import-report.json
```

A valid processing report is not publication approval.

## Manual import through GitHub Actions

1. Add the owner-supplied CSV to `private-imports/` in this private repository.
2. Open GitHub Actions.
3. Run **2 - Process Result Import and Open Approval PR**.
4. Supply the file path, authority, examination identifier, year, and source reference.
5. Review the generated Pull Request, including validation and duplicate findings.
6. Merge only after confirming the source and the entire batch.

If replacing an existing examination/year dataset, explicitly enable `replace_existing`. Existing records are not silently overwritten.

The manual import workflow accepts CSV only. Exact duplicate candidates block publication PR creation; fuzzy duplicate candidates remain visible for review. For PDFs, place the source inside `private-imports/` and run **2B - Extract PDF Text for Manual Review** in GitHub Actions. Download its private extraction artifact, manually verify and map the records, then convert them into a reviewed CSV before using the CSV import workflow.

## Source monitoring

The Cloudflare Watcher runs every minute and reads only `python-engine/config/sources.json`. Standard Mode checks once. Peak Week Mode is activated by setting the Cloudflare KV key `PEAK_WEEK` to the text value `true`; it performs two scans 30 seconds apart. The Worker uses HTTPS `HEAD` checks, detects metadata changes, checks same-origin PDF links, and expands only owner-configured preemptive URL templates. A successful PDF detection triggers a GitHub `repository_dispatch` event. GitHub Actions validates the event against the approved registry; Python extraction/Greenlight processing is connected in Phase 2.

The initial source registry is empty:

`python-engine/config/sources.json`

A configured source must have a unique ID, authority, exam identifier, source type, HTTPS URL, and enabled flag. Official sources require explicit authorization. Verified third-party sources are checked only when configured official sources for the same examination are unavailable. Optional `preemptive_url_templates` must use the same HTTPS origin as the approved source URL. Do not add guessed or unapproved source URLs or templates.

When D1 is configured, Python compares ETag, Last-Modified, and content length. A source with no reliable change metadata is not automatically acquired. Set `auto_acquire: true` only after verifying a direct CSV/PDF file URL and its format. CSV files can be processed into an owner-approval PR; PDF text extraction remains a manual-review step.

A detected source change is not proof that official results have been released.

## Preparing Mode

Run **5 - Set Preparing or Searching Mode** in GitHub Actions. Preparing Mode requires an existing D1 release prediction within five days of its predicted date. The owner selects the actual workflow stage from a fixed list; the percentage is mapped to that stage and cannot be typed freely. A status-change PR must be merged before the public homepage changes.

The scheduled prediction workflow uses `python-engine/config/examinations.json`, which starts empty. Historical actual release dates must first be recorded in D1. Automatic prediction-based homepage activation is not yet connected; the owner can activate Preparing Mode manually through the workflow.

## GitHub Actions workflows

- **1 - Manual Source Check (Owner Diagnostic):** manually runs the legacy Python metadata check; it has no scheduled trigger. The Cloudflare Watcher owns scheduled monitoring.
- **Process Detected Source and Manual Drop:** receives the Watcher's `source-detected` webhook and manual-drop pushes. Phase 1 validates and records the event only; Phase 2 connects Python processing.
- **2 - Process Result Import and Open Approval PR:** manual CSV import.
- **2B - Extract PDF Text for Manual Review:** owner-triggered text extraction from a private PDF; it never publishes records.
- **3 - Deploy Public Site to Cloudflare Pages:** production static deployment after approved changes reach main.
- **4 - Weekly Maintenance:** tests, public dataset integrity, and D1 storage checks.
- **5 - Set Preparing or Searching Mode:** owner-controlled homepage status PR.
- **6 - Update Release Predictions:** scheduled prediction updates for configured examinations.

## Cloudflare Watcher setup

See `watcher-bot/README.md`. Deployment requires a Workers KV namespace bound as `PEAK_WEEK`, a Worker secret named `GITHUB_TOKEN`, and the correct repository/ref variables. The GitHub token must have repository Contents read/write permission: read the source registry and write to the repository-dispatch endpoint. The token must be stored as a Cloudflare Worker secret, never in source code or GitHub files.

The Watcher is not considered live until the Worker is deployed, the Cron Trigger is visible, the KV binding and secret are verified, and a real authorized source test successfully reaches the GitHub receiver.

## D1 configuration

The D1 REST client reads these GitHub Actions secrets:

- `CF_API_TOKEN`
- `CF_ACCOUNT_ID`
- `D1_DATABASE_ID`

The API token must have only the Cloudflare permissions required for the D1 operations. D1 stores metadata and history, not the public passer-name dataset.

If these secrets are absent, processing continues without D1 persistence and the run reports that D1 is not configured.

## Cloudflare Pages deployment

The deployment workflow requires:

- `CF_PAGES_API_TOKEN`
- `CF_ACCOUNT_ID`
- `CF_PAGES_PROJECT_NAME`

The Pages API token must have the required Pages deployment permission. The project must already exist in the owner's Cloudflare account.

Cloudflare Pages output directory: `public`.

No build command is required for this static HTML/CSS/JavaScript site.

**Deployment has not been performed or verified by this repository change.** Without the Cloudflare credentials and an existing Pages project, the deployment workflow cannot publish the site.

## Free-tier safeguards

- No Worker is used for public searching.
- Public result searches use static Pages assets.
- D1 is not queried by visitors.
- GitHub Actions usage must remain within the repository's actual free allowance.
- Cloudflare Pages file count and per-file size limits must be monitored.
- Generated JSON shards are capped at 10 MiB by the Python builder.
- A failed import or deployment must not replace the last approved public result dataset.
- No workflow may silently upgrade to a paid plan.

Free-tier limits and GitHub account allowances can change. Verify current limits before production launch.

## Important limitations

- No PRC or CSC source is configured yet.
- No real result dataset has been imported or published.
- PDF extraction is not a universal layout parser; OCR is not implemented.
- Release prediction requires sufficient actual release history in D1.
- Preparing Mode is controlled through an owner-approved status PR and requires a D1 prediction within the five-day activation window; automatic prediction-based activation is not yet connected.
- The Watcher code has local mocked tests, but Cloudflare deployment, KV, GitHub credentials, and real-source/webhook integration are not yet verified.
- The 30,000–59,000 concurrent visitor target has not been load-tested.
- Cloudflare Pages deployment and D1 connectivity have not been verified.

## Safety rule

Only owner-approved, verified result batches may be merged into `main`. Public datasets are generated in a separate Pull Request. The last verified public result dataset must remain available if processing or deployment fails.
