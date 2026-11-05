# Approved CSC Google Drive PDF probe

This Python utility is a diagnostic companion to the Cloudflare Worker. It tests
whether the exact Google Drive file IDs already approved in the source registry
can be retrieved directly when the CSC announcement page is unavailable.

It does **not** bypass Google permissions, sign-in, CAPTCHAs, or access controls.
It only follows HTTPS redirects to the two Google download hosts and requires
every redirect to retain the exact approved file ID. It verifies the PDF byte
signature before saving anything.

## Run in Codespaces

From the repository root:

```bash
cd python-engine
PYTHONPATH=retrieval python -m unittest discover -s tests -v
PYTHONPATH=retrieval python retrieval/drive_pdf_probe.py \
  --source-id CSC-CSE-PPT-2026-08-09-REGION-V
```

Successful PDFs are saved locally under `python-engine/artifacts/drive-probe/`.
The output names contain source and Drive IDs, not passer names. Do not commit
or publish downloaded exam-result PDFs.

The source must be an enabled, authorized CSC source with
`direct_drive_fallback: true`. The tool will refuse unapproved or malformed
Drive IDs.

## Failure meanings

- `HTTP 403`: Google denied public retrieval; this tool does not attempt to
  defeat the restriction.
- `HTML instead of a PDF`: likely a permission/interstitial page; no file is
  accepted.
- `Blocked Google Drive redirect`: host, path, scheme, or file ID changed;
  retrieval is stopped.
- `downloaded_pdf`: bytes were downloaded and the PDF signature verified;
  this is not yet OCR or passer-name extraction.
