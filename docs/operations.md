# PH-EXAM-RESULTS operations

## Current safe operating state

The initial public catalogue is empty. The source registry is empty. No results are presented as live or official until an owner-reviewed dataset is merged.

## Import a CSV

The current import workflow is manual-dispatch only.

1. Keep the repository private.
2. Place the authorized CSV file inside `private-imports/`.
3. CSV must have a `name` column. Optional fields are `rating`, `region`, and `seq`.
4. Open GitHub Actions and run **2 - Process Result Import and Open Approval PR**.
5. Supply the CSV path, authority, examination identifier, year, source reference, and actual release date if known.
6. Inspect the processing report and generated dataset in the resulting PR.
7. Do not merge until the source and every duplicate/validation finding have been checked.

The workflow rejects paths outside `private-imports/`, non-CSV inputs, invalid records, and exact duplicate records. Replacing an existing examination/year requires explicitly selecting the replacement option.

## PDF handling

Run the Python `extract-pdf` command only for text extraction. Its output is not a passer dataset. Scanned PDFs may need OCR or manual conversion. Review and map extracted lines into a CSV before using the import workflow.

## D1 configuration

Create the D1 database in the Cloudflare account and add these GitHub Actions repository secrets:

- `CF_API_TOKEN` — token with the minimum required D1 database permissions.
- `CF_ACCOUNT_ID` — Cloudflare account ID.
- `D1_DATABASE_ID` — D1 database ID.

The Python client applies the checked-in schema through the Cloudflare D1 REST API. D1 must never be exposed to the public browser.

## Cloudflare Pages deployment

Create the Pages project and add these GitHub Actions repository secrets:

- `CF_PAGES_API_TOKEN` — token with Pages deployment permission.
- `CF_ACCOUNT_ID` — Cloudflare account ID.
- `CF_PAGES_PROJECT_NAME` — exact Pages project name.

The deployment workflow validates public files before deploying the `public/` directory.

## Recovery

If a bad data PR is merged and deployed, use GitHub Revert on the merge commit. The deployment workflow then republishes the restored `main` contents.
