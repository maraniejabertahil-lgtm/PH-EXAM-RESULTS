# Reviewed Batch Input Guide

The Python-to-GitOps pipeline currently accepts a **reviewed, normalized JSON batch**. It does not yet convert arbitrary PDF table layouts into passer records automatically. The existing PDF parser extracts raw page text and tables; a person must map and review those rows before setting `record_mapping_reviewed` to `true`.

Only process examination results that have already been publicly released. Do not put private, unreleased, or otherwise restricted records into this workflow.

## Required top-level fields

- `authority`: `PRC` or `CSC`.
- `exam`: exact exam identifier used by the approved source registry.
- `year`: four-digit year.
- `announced_count`: official announced passer count.
- `publicly_released`: must be Boolean `true`.
- `source_id`: exact enabled source ID from `python-engine/config/sources.json`.
- `provenance`: `official_direct` or `third_party_fallback`.
- `records`: reviewed record objects containing `name` and `sequence_number`; optional `rating` and `region`.

## Official-direct fields

For `official_direct`, also provide:

- `official_source_url`: must exactly match the approved registry URL.
- `official_document_url`: credential-free HTTPS URL on the approved source host, or an allowed Google Drive link.
- `source_pdf`: optional repository-relative path to an already-acquired official PDF. If omitted, the pipeline attempts a bounded official download.
- `official_article_url`: required when `source_pdf` is omitted; the PDF URL must be an actual link on this official article.
- `record_mapping_reviewed`: Boolean `true` when supplying pre-normalized `records`.
- `table_mapping`: alternatively, an explicit mapping with `table_indexes`, `header_rows`, `name_column`, `sequence_column`, and optional `rating_column` / `region_column`.
- `table_mapping_reviewed`: Boolean `true` when supplying `table_mapping`.
- `source_pdf_sha256`: optional expected SHA-256 fingerprint.

For `official_content_mode: "manual_handoff"`, provide:

- `official_article_url`: the exact PRC/CSC official result article URL.
- `official_content_url`: the exact linked Google Drive URL shown on that official article.
- `official_content_reviewed`: Boolean `true` only after the owner has legitimately opened and reviewed the complete publicly released contents.
- `record_mapping_reviewed`: Boolean `true` only after checking that every supplied name is paired with its original sequence number.
- `records`: the reviewed name/sequence records.

Automated PDF acquisition remains limited to same-origin HTTPS PDF links. External Google Drive files are not downloaded by the manual-handoff path. The content handoff verifies the official article-to-Drive link and records that the owner reviewed the source contents; it does not access Google Drive or bypass sign-in, permissions, or human verification.

The PRC homepage registry entry is an official source for all PRC licensure examinations. Each batch must still identify its actual examination with a specific safe `exam` identifier; the generic homepage identifier must not be used as the published examination name.

## Third-party fallback fields

For `third_party_fallback`, also provide:

- `official_attempt_log`: repository-relative path to the persisted official-first attempt evidence.
- `source_a_id` and `source_b_id`: distinct source identities.
- `source_a_url` and `source_b_url`: distinct HTTPS sources hosted on different domains.
- `comparison_records`: records transcribed from the second source.

The official-first gate must allow fallback, and Greenlight must confirm exact sequence-number/name-pair agreement, announced-count agreement, complete sequence coverage, and zero integrity issues.

## Run the workflow

1. Add the reviewed JSON file to the repository at a repository-relative path. The file must contain only publicly released result information.
2. Open GitHub **Actions**.
3. Select **Process Detected Source and Manual Drop**.
4. Select **Run workflow** and enter the JSON file path in `batch_file`.
5. The Python pipeline validates the batch and creates a data-only pull request only when Greenlight is exactly 100/100.
6. GitOps explicitly dispatches `watcher-ci.yml` against that exact PR commit. It merges only after the workflow and all commit checks succeed. Failure or timeout leaves the PR open.

A failed Greenlight report is written in the runner workspace for that run; no dataset PR is created. The current workflow does not yet upload that report as a retained artifact.

## Important current boundary

This is the safe handoff from **reviewed normalized records** to Greenlight, JSON generation, GitOps PR creation, CI, and merge. It does not claim automatic PDF acquisition or automatic table-to-record normalization. Those remain separate processing work and must be validated against real, authorized result PDFs before being automated.


## CSC official portal handoff (no PDF required)

The CSC portal source is registered as `CSC-CSE-PORTAL`. Its official public search page is:

`https://exam.csc.gov.ph/list_passers?type_id=1`

This route is intentionally owner-reviewed and makes **no automated request** to the CSC portal. The owner must use the official portal through ordinary authorized browser access, confirm the result is publicly released, review the complete applicable result, and verify every exact name/sequence pair. Do not automate CAPTCHA, login, or other interactive controls.

For this route, create a JSON batch with:

- `authority`: `CSC`
- `exam`: a specific examination identifier, e.g. `CSE-PPT-2026-03`
- `source_id`: `CSC-CSE-PORTAL`
- `official_source_url`: exact registry URL, including `?type_id=1`
- `official_portal_url`: the official portal page URL used for the reviewed result; same approved HTTPS host and `/list_passers` path
- `provenance`: `official_direct`
- `official_content_mode`: `owner_reviewed_portal_handoff`
- `publicly_released`, `official_content_reviewed`, and `record_mapping_reviewed`: Boolean `true`
- `announced_count`: the exact official announced passer count for the batch scope
- `records`: reviewed objects with exact `name` and `sequence_number` values copied from the official result; never infer or renumber them

The current dedicated command validates source identity, owner-review attestations, record integrity, and Greenlight, then creates local dataset artifacts only:

```bash
python python-engine/run_portal_validation.py path/to/csc-portal-batch.json
```

This dedicated portal route is a validation-only handoff. It does not fetch the portal, solve interactive checks, create a GitOps PR, or publish a dataset. The regular PDF/Drive processing route remains unchanged. A representative official batch is still required before the access path and extraction mapping can be marked accepted.
