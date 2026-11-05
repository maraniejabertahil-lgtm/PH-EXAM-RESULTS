# CPALE public-preview extraction package

This package collects the existing CPALE extraction implementation from the
isolated `fix/pages-search-runtime` candidate. It is provided for inspection
and local testing; it is not merged into `main`, deployed, or authorized for
automatic publication.

## What is included

- `python-engine/`: the acquisition, visible-preview capture, parsing,
  Greenlight, dataset, and supporting Python engine modules.
- `python-engine/config/`: the candidate source registry and reviewed CPALE
  rendered-text mapping used by the integration.
- `python-engine/tests/`: the four focused preview/acquisition suites.
- `python-engine/requirements.txt` and `requirements-preview.txt`: pinned base
  and optional Playwright dependencies.
- `examples/process-import.yml`: the repository workflow context from the
  candidate branch. It is an example, not a standalone or production workflow.
- `evidence/`: the actual CPALE result CSV and the source/validation record
  from the local extraction.

The capture uses Playwright/Chromium to read visible rendered DOM text from
PRC's ordinary public Google Drive preview. PNG screenshots are capture
evidence; OCR was not used to extract the names. The candidate's reviewed
parser validates exact sequences, count, duplicates, capture hashes, and
Greenlight requirements.

## Local test instructions

From this package directory:

```sh
python -m pip install -r python-engine/requirements.txt
python -m pip install -r python-engine/requirements-preview.txt
cd python-engine
python -m unittest \
  tests.test_prc_orchestrator \
  tests.test_prc_public_preview_pipeline \
  tests.test_public_preview \
  tests.test_public_preview_shards -v
```

The focused tests use synthetic capture fixtures and do not access PRC or
publish any data. Installing the optional browser package alone does not
install Chromium; the repository workflow installs it conditionally with
`python -m playwright install --with-deps chromium`.

## Included CPALE execution evidence

The saved local extraction record reports:

- PRC release: October 2026 CPALE, published November 3, 2026.
- 80 public-preview viewer pages captured.
- 3,988 passer records, sequences 1 through 3,988, no sequence gaps or
  duplicates, and no duplicate names.
- CSV SHA-256:
  `a010e6168cab5a0c386220e66c336e834888b962aba05d04bfc84144e3aad41a`
- Canonical sequence-tab-name records SHA-256:
  `c77042c9ffeac17926cf10803a8b930e30fcef8295c5a01db0ffe9b6f3f1fa7c`

This evidence is from the original local extraction, not from an automated
Watcher's detection-to-publication run. The focused integration tests are
synthetic. No publication, merge, or deployment is evidenced by this package.
The CSV's independently checked hash and sequence/count checks are recorded
in `evidence/package-validation.json`. That check also records that the
canonical records hash stated in the original validation JSON could not be
reproduced from the included CSV; treat that particular digest as unverified.

## Safety and scope

The code is configured for an exact, allowlisted PRC result article and Drive
file. It must stop rather than handle sign-in, CAPTCHA, human verification, or
other access barriers. Do not treat the sample source settings as blanket
authorization for another source or result. Review access directives and
reuse terms before use.

The package contains the public CPALE passer names as execution evidence.
