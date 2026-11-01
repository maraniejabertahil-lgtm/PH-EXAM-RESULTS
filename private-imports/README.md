# Private source imports

This directory is for owner-supplied source files used by the manual import workflow.

- The repository must remain private.
- Only CSV files with a required `name` column are accepted by the current import workflow.
- Keep original official source files unchanged.
- Never place source documents inside `public/`.
- Do not commit passwords, API tokens, or unrelated personal information.
- PDF text extraction is currently a separate manual-review step; it does not automatically create passer records.
- Every generated public dataset is proposed in a GitHub Pull Request and remains unpublished until the owner merges it.

The directory is intentionally empty in the initial implementation.
