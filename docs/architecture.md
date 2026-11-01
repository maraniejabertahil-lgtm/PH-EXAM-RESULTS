# PH-EXAM-RESULTS implementation architecture

The approved Master Technical Blueprint remains the governing specification. This document records what the current implementation does and what remains unconfigured; it does not replace or modify that blueprint.

## Public request path

1. Cloudflare Pages serves the static files in `public/`.
2. The browser downloads `data/manifest.json` and only the selected examination/year alphabetical shard.
3. The browser verifies the shard SHA-256 hash.
4. IndexedDB caches the verified JSON shard by path and hash.
5. The browser sends the dataset to a JavaScript Web Worker once.
6. The Worker searches names without blocking the main UI thread.

No public visitor search is sent to Python, D1, a Worker, or a backend server.

## Processing and publication path

1. The Cloudflare Watcher runs from a one-minute Cron Trigger and reads the approved source registry from GitHub.
2. The source registry is checked official-first by authority and examination.
3. Verified third-party sources are checked only when configured official sources for the same scope are unavailable.
4. Standard Mode checks once. Peak Week checks twice, 30 seconds apart, and expands owner-configured preemptive URL templates.
5. The Watcher detects successful PDF URLs and sends a GitHub `repository_dispatch` event. The Phase 1 receiver validates the event against the approved source registry.
6. Phase 2 connects the event to Python acquisition and extraction. When D1 is configured, Python compares ETag and Last-Modified metadata.
7. Only an explicitly approved source with `auto_acquire: true` can be downloaded.
8. CSV files are normalized, validated, and checked for exact/fuzzy duplicate candidates.
9. Text-based PDFs are text-extracted for manual review; scanned/uncertain layouts are not automatically converted into passer records.
10. Valid CSV batches can generate a private Git branch and owner-approval Pull Request.
11. Exact duplicate records block automatic publication PR creation. Fuzzy candidates remain visible for review.
12. Only a merged PR can reach the production Pages deployment workflow.
13. When D1 is configured, batch status is updated to awaiting approval and then published after deployment.

The manual import workflow is also available for CSV files stored in the private `private-imports/` directory.

## Python engine

- `scraper/monitor.py`: HTTPS metadata checks and official-first fallback selection.
- `scraper/downloader.py`: acquisition only from approved HTTPS sources, with same-host redirect checks, a download size cap, and SHA-256.
- `extractor/pdf_parser.py`: text extraction from text-based PDFs only.
- `processor/normalizer.py`: preserves original names and creates normalized comparison keys.
- `processor/validator.py`: validates authority, examination identifier, year, name, rating, and sequence fields.
- `processor/duplicates.py`: exact duplicate detection and bounded fuzzy candidate checks; records are never automatically deleted.
- `prediction/release_predictor.py`: estimates release timing from up to five historical intervals.
- `preparation/status_builder.py`: predefined preparation stages and fixed percentages.
- `publisher/json_builder.py`: compact array-of-arrays datasets with adaptive alphabetical shards capped at 10 MiB.
- `publisher/manifest.py`: manifest generation with paths, hashes, counts, and sizes.
- `publisher/gitops_manager.py`: candidate branch and owner-approval PR creation.
- `database/d1_client.py`: parameterized Cloudflare D1 REST operations and storage-size reporting.

## Source registry

File: `python-engine/config/sources.json`. It starts empty.

A source entry must include a unique `id`, `authority`, `exam`, `source_type`, `enabled`, and HTTPS `url`.

Official source entries require `source_type: "official"` and `authorized: true`.

Third-party entries require `source_type: "verified_third_party"` and `verified_by_owner: true`. A third-party source is considered only when official source entries for the same authority/exam scope are unavailable.

For automatic acquisition, set `auto_acquire: true`, `file_format` to `csv` or `pdf`, and provide the authority, exam identifier, and integer year. A CSV must contain a `name` column. A PDF is only extracted to text and requires manual mapping/review.

No real source URL or preemptive URL template is preconfigured. The optional `preemptive_url_templates` field is used by the Cloudflare Watcher only after the owner approves the exact source origin and URL pattern.

## Cloudflare Watcher

- `watcher-bot/src/index.js`: scheduled source checks, Peak Week 30-second second scan, preemptive PDF URL expansion, PDF detection, GitHub repository dispatch, and KV deduplication.
- `watcher-bot/wrangler.toml`: one-minute Cron Trigger and `PEAK_WEEK` KV binding.
- `watcher-bot/tests/`: mocked Standard Mode, Peak Week, PDF detection, authorization, redirect, and webhook tests.
- `.github/workflows/process-import.yml`: receives `source-detected` events and manual-drop pushes. In Phase 1 it validates and records the event only; Phase 2 connects Python processing.

The Worker requires a Cloudflare KV namespace binding named `PEAK_WEEK` and a Cloudflare Worker secret `GITHUB_TOKEN`. The fine-grained GitHub token needs repository Contents read/write permission. The source registry remains empty until owner-approved sources are configured.

## D1

D1 is internal metadata only. It stores source state, monitoring logs, import batch summaries, release history/predictions, and publication audit information.

The public browser never queries D1.

Required GitHub Actions secrets:
- `CF_API_TOKEN`
- `CF_ACCOUNT_ID`
- `D1_DATABASE_ID`

If D1 is not configured, source-state comparison and automatic acquisition are skipped. CSV processing can still run, but D1 audit and prediction persistence are unavailable.

## Public datasets

Each dataset file contains `columns: ["name", "rating", "region", "seq"]` and an array-of-arrays `data` field.

The manifest maps authority → examination → year → shard. The frontend selects the shard using the first character of the search query. Names not beginning A-Z use OTHER.

The builder starts with A-M and N-Z ranges and recursively subdivides oversized ranges. A single-letter or OTHER shard exceeding 10 MiB fails safely and requires further partitioning.

## Preparing Mode

`public/data/site-status.json` controls whether the public application displays Searching or Preparing Mode.

The current manual owner workflow supports these predefined stages:
- monitoring: 10%
- source_detected: 25%
- document_acquired: 40%
- extracting: 55%
- validating: 70%
- awaiting_approval: 90%

The owner selects the actual stage; arbitrary percentages are not accepted. The status change is proposed through a PR and becomes public only after merge and deployment.

The scheduled prediction workflow updates configured examinations in `python-engine/config/examinations.json`. That configuration currently starts empty. Automatic prediction-based Preparing Mode activation is not yet connected; manual activation is available.

When a result publication PR matches the currently active authority, exam, and year, its candidate branch resets the site status to Searching Mode. This reset becomes public only after that result PR is merged and deployed.

## Current limitations

- Source registry and examination prediction configuration are empty.
- No real result records are included.
- No Cloudflare Worker deployment, KV namespace, GitHub dispatch secret, D1, or Cloudflare Pages credentials have been verified.
- PDF OCR and automatic passer extraction are not implemented.
- Automatic Preparing Mode activation from predictions is not yet connected.
- A synthetic 50,000-row Web Worker search test passes in CI (latest measured Node-runner execution: 71.30 ms); this is not a real browser or 30,000–59,000 concurrent-visitor load test.
- The 30,000–59,000 simultaneous visitor target has not been load-tested.
- Cloudflare Pages deployment has not been performed or verified.
- The Cloudflare Watcher has only been tested locally with mocked source and GitHub responses; live Cron, KV, source URLs, and repository-dispatch delivery remain unverified.
