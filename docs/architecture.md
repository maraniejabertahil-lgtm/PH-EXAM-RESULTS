# PH-EXAM-RESULTS implementation architecture

This document records the repository implementation. The approved Master Technical Blueprint remains the governing specification and is not modified here.

## Public request path

1. Cloudflare Pages serves the static files in `public/`.
2. The browser downloads `data/manifest.json` and the selected examination/year shard.
3. The browser verifies the shard SHA-256 hash.
4. IndexedDB caches the verified JSON shard.
5. A JavaScript Web Worker performs name matching; no public visitor query is sent to Python, D1, or a server.

## Processing path

1. GitHub Actions runs the approved source monitor on its schedule.
2. An owner manually starts the import workflow with a CSV held under `private-imports/`.
3. Python normalizes and validates records, reports exact/fuzzy duplicate candidates, and records lightweight metadata in D1 when credentials are configured.
4. Exact duplicates and invalid records block publication PR creation.
5. Python generates compact public JSON shards and a manifest on a dedicated branch.
6. A GitHub Pull Request presents the batch summary for owner review.
7. Only a merged PR can reach the production deployment workflow.

## Important boundaries

- The source registry starts empty. No website is assumed authorized for automated collection.
- The current automated import path accepts CSV. PDF extraction currently extracts text only and requires manual record mapping/review.
- Fuzzy duplicate candidates are not silently removed; they remain visible for human review.
- D1 is internal metadata only. Passer records are published as static JSON, not stored row-by-row in D1.
- Cloudflare deployment and D1 access remain inactive until the relevant account resources and GitHub Actions secrets exist.
- No real examination dataset is included in the initial public catalogue.
