# Manual Source Validation (Phase 1)

This owner-triggered workflow is a safe fallback for an official source that is deliberately disabled for automated polling.

## Run it

1. Open the repository's **Actions** tab.
2. Select **Manual Source Validation**.
3. Select the disabled source ID shown in the workflow input.
4. Enter the exact Google Drive file ID already listed in `python-engine/config/sources.json`.
5. Set **Confirm validation only** to true.
6. Run the workflow and inspect the `manual-source-validation-<run id>` artifact.

## Safety limits

- The source must be disabled, official, owner-authorized, and marked `manual_drop_required: true`.
- The Drive file ID must match an exact entry in that source's allowlist.
- The workflow performs no network request and does not download PDF bytes.
- It does not re-enable automated polling.
- It does not acquire, extract, grade, or publish results.
- It produces a validation-only JSON artifact with `pdf_acquired=false`, `extraction_performed=false`, and `published=false`.

To validate a new Drive ID, first add it to the correct source's owner-approved `drive_file_ids` list through a reviewed repository change. Do not bypass the allowlist by entering an arbitrary ID.

This is a Phase 1 source-confirmation mechanism, not a completed manual PDF import or extraction pipeline.
