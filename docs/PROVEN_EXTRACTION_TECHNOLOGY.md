# Proven Extraction Technology Reference

**Purpose:** Preserve the extraction approach demonstrated by GitHub Actions run [#41551294389](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/actions/runs/41551294389), so it can be reused and improved in the PH-EXAM-RESULTS project.

## What actually worked

The successful extraction path was a Python HTML-extraction and independent-source comparison workflow executed by GitHub Actions.

| Component | Actual role in the successful run |
|---|---|
| Python 3 | Main acquisition, parsing, extraction, and comparison runtime |
| Python `urllib` | HTTP retrieval of source webpages |
| Python `html.parser.HTMLParser` | HTML parsing and visible-text collection |
| Python `re` (regular expressions) | Identification of passer names and their sequence numbers from parsed text |
| Python comparison logic | Pair-by-pair comparison using sequence number as the key |
| Python `hashlib` | SHA-256 evidence hashes for retrieved source content |
| GitHub Actions | Automated execution, logs, and private evidence artifact storage |

The workflow compared two independent public transcription sources. Its report recorded:

- Source 1: 28,652 extracted records
- Source 2: 28,652 extracted records
- Reported sequence-number disagreements: 0
- Greenlight: **false**
- Publication: **not performed**

This is evidence that the extraction and cross-checking path ran successfully for that NLE release. It is **not** evidence that the batch passed the project's complete Greenlight checks or was published.

## Tools installed but not used in the successful extraction path

- **Poppler** (`pdfinfo`, `pdftotext -layout`, `pdftotext -bbox-layout`) was installed. Its PDF commands were conditional on successfully acquiring the official PDF; the successful fallback extraction path did not use them.
- **Tesseract OCR** was installed but was not invoked by the successful extraction scripts.
- Node.js was set up by the workflow but was not the extraction engine.

Do not describe this run as a successful Poppler or Tesseract extraction.

## Reuse rules for this project

1. Keep the project's **official-first, content-first** acquisition policy. Attempt the official PRC result announcement and its linked result contents first, using only authorized, low-impact access.
2. Use this Python HTML parsing approach when the source is a publicly accessible webpage and its terms/robots policy permit automated retrieval.
3. Third-party transcription sources are fallback-only under the governing blueprint. Use them only after compliant official retrieval has been confirmed unavailable and the fallback gate is satisfied. A user instruction restricting a particular test to official sources overrides fallback for that test.
4. For fallback, use two independent sources and compare the exact **sequence-number/name pairs**, not just record counts or names. Preserve source provenance and acquisition evidence.
5. A matching count and zero reported disagreements do not alone prove correctness. Greenlight must still verify the announced count, complete sequence coverage, missing/extra records, blanks, duplicates, anomalies, and exact pair agreement.
6. Never bypass authentication, CAPTCHA, MFA, permissions, robots.txt, rate limits, or other access controls.
7. Do not publish or auto-merge unless the existing Greenlight and GitOps gates pass at 100%.

## Historical implementation references

- Successful workflow run: [#41551294389](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/actions/runs/41551294389)
- Commit used by that run: `d9b358604b51d56d26dfc591013bd309088ce43f`
- Workflow: `.github/workflows/private-prc-extraction.yml`
- Acquisition script: `tools/prc-drive-acquire.py`
- HTML extraction/comparison script: `tools/prc-mirror-extract.py`

These files are historical implementation evidence. Reuse their approach selectively; do not assume the scripts are generic for every examination, source layout, or release.
