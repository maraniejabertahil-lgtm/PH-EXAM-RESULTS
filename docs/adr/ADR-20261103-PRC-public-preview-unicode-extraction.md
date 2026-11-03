# ADR-20261103-PRC: Unicode-Aware Extraction from the Official Public Preview

- **Status:** Active (Python Engine integration merged; full Elementary Greenlight passed; GitOps publication pending)
- **Date:** 2026-11-03
- **Owner:** PH-EXAM-RESULTS Project Owner
- **Technical owner:** PH-EXAM-RESULTS engineering workflow
- **Target constraint:** The first text parser accepted only English A–Z names and missed 926 of the 18,376 announced March 2026 LEPT Elementary records. Downloading the linked PDF is not required by the project's content-first policy. The official PRC article links a publicly accessible Google Drive preview, but the preview's accessible text is cumulative as pages are visited.
- **Official source:** https://www.prc.gov.ph/index.php/article/march-2026-licensure-examination-professional-teachers-results-released-thirty-nine-39
- **Official linked content:** https://drive.google.com/file/d/1kY0CTSuwdxDwnf1UEvWe27HDEXU3rolE/view

## Options considered

1. **Direct PDF acquisition and PDF parsing (PyMuPDF/pdfplumber).** Technically available as an optional route, but not required for the data outcome and the official content-first policy does not require storing or downloading the PDF.
2. **Ordinary public-preview text via Playwright.** Uses the publicly available viewer UI and its visible page-number control. Does not call private endpoints or download APIs. The accessible body text accumulates as pages are navigated.
3. **Tesseract OCR over rendered screenshots.** Useful as an independent advisory check for difficult records, but OCR output is not authoritative and must never silently replace source text.

## Adopted prototype

Use Playwright to navigate the ordinary public Google Drive preview through its visible page control, capture the final cumulative text snapshot, and parse sequence/name pairs with a Unicode-aware Python parser. The parser accepts Unicode letters and combining marks, numbers, whitespace, and ordinary name punctuation while preserving the exact source spelling. Tesseract is used only as an advisory cross-check. Screenshots of any flagged records are retained for visual review.

The extraction prototype must retain only the final cumulative document-text snapshot rather than concatenating every intermediate viewer snapshot. This avoids repeated records and a 122 MB intermediate text artifact while preserving the full document content.

## Evidence and result

- PRC's official announcement, posted 12 May 2026, states that 18,376 Elementary examinees passed and links the official list.
- The final cumulative preview-text snapshot produced 18,376 unique sequence/name pairs.
- Prototype validation: 18,376 records; zero missing sequence numbers; zero conflicting assignments; zero duplicate names; zero blank names; zero out-of-range records.
- Sequence 10,710 was visually checked on printed page 216: `MAGANGCONG, MUHAMMAD_THANI PAUTE`.
- Sequence 15,066 was visually checked on printed page 303: `ROBLES, D9 BASUG`.
- The integrated full-batch evidence is retained in [run #41664546615](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/actions/runs/41664546615), artifact `prc-official-lept-elementary-2026-evidence`. Screenshot SHA-256 values in the latest reconciled capture:
  - Page 216: `f35571961f7fe6a946097b1cfc82f82e8988d45fe04d7bb2b79688e79dbd0968`
  - Page 303: `7b32b939a5e8deefed29c94de644fd4db0bb8da9d503f2522d7253189971c10e`
- Python Engine integration was merged in PRs #58 and #59. The full 18,376-record batch passed Greenlight 100/100 in runs #41663204288 and #41664546615. Canonical records SHA-256: `37cd69173dc25d2792c0602daaa1ff5bcd4e3f87569e2fe4598b14300c01e21e`.
- Dataset manifest contains one 862,332-byte Array-of-Arrays shard; its SHA-256 matches the generated file. The optimized incremental shard-size calculation reduced the Python Engine validation/dataset step from 73 seconds to 5 seconds on the same 18,376-record batch (PR #60; 116 tests passed).
- The visible document pages contain a DRAFT watermark. The official PRC article nevertheless identifies the result as released and links this document. Preserve the watermark as a source-quality observation; do not interpret it as permission to alter the records.

## Safeguards and compliance

- Official PRC article and its linked Drive document remain the provenance source.
- Access only through the normal public preview UI and visible page navigation.
- No login, CAPTCHA, MFA, Turnstile, permission, private API, download endpoint, or rate-limit bypass.
- Respect the official source's robots policy and use bounded, low-frequency requests.
- Do not infer, autocorrect, transliterate, or renumber names or sequences.
- OCR is advisory only; original visible source text and screenshot evidence control.
- Full Greenlight remains fail-closed. The GitOps attempt [run #41665288366](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/actions/runs/41665288366) staged the dataset on `data/greenlight-37cd69173dc2` but GitHub rejected `POST /pulls` with HTTP 403 because Actions is not permitted to create or approve pull requests. The repository setting must be enabled by the Owner before the automated PR path can proceed.
- The source file carries a visible DRAFT watermark and the visual report retains `human_visual_verification: PENDING`. The Owner must review this source-quality caveat before the dataset PR is merged. No dataset has been merged into `main` or deployed.

## Trade-offs and known debt

- Viewer accessibility text can be cumulative and may repeat prior pages if intermediate snapshots are concatenated. The prototype therefore retains only the final cumulative snapshot and records page-navigation evidence.
- Playwright adds browser-install and CI runtime cost, though it uses the existing free GitHub Actions runner.
- Tesseract may misread underscores, digits, or accented names; it is never allowed to alter extracted records.
- The hash-bound `public_preview_capture` mode is now a first-class Python Engine acquisition path (`python-engine/acquisition/public_preview.py` and `python-engine/main.py`), with tests for manifest integrity, screenshot binding, and fail-closed behavior. The full Elementary Greenlight and dataset generation are proven; live GitOps PR creation/CI/merge remains blocked by the repository Actions permission setting and the DRAFT-watermark Owner review.

## Rollback plan

Revert the source-specific trial workflow/scripts on `integration/prc-public-preview-python-engine` if they are no longer needed. The reusable Python Engine integration can be rolled back by reverting PRs #58 and #59; the linear-time shard optimization can be reverted by PR #60. No dataset has been merged into `main` or deployed. Keep the last-known-good public data untouched.

## Review date

2026-12-03

## Deprecation trigger

Retire or replace this prototype if PRC supplies an officially supported public structured dataset/export or a stable authorized content endpoint that yields the same exact sequence/name pairs with stronger provenance and lower maintenance cost.
