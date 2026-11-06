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
  from the original extraction, plus the later live candidate capture,
  screenshot/text/hash evidence, Greenlight report, and local dataset.

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

The 33 focused tests use synthetic capture fixtures and do not access PRC or
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

The later live candidate run captured all 80 viewer pages in four sequential
browser shards, extracted 3,988 records matching the saved CSV exactly, passed
local Greenlight at 100/100, and generated one local dataset shard. The capture
bundle in `evidence/live-capture/` includes the 80 screenshots, rendered text,
records, and hash-bound manifests. Its relocated bundle was independently
verified offline against the included CSV. The local run summary and generated
reports are in `evidence/live-run/`.

The original CSV hash and canonical records hash are independently reproduced
in `evidence/package-validation.json`. The canonical serialization is
LF-joined `sequence<TAB>name` rows with no trailing LF. This is not a Watcher
detection-to-publication run. No GitOps, PR creation, publication, merge, or
deployment occurred, and visual review remains `PENDING`.

## Safety and scope

The code is configured for an exact, allowlisted PRC result article and Drive
file. It must stop rather than handle sign-in, CAPTCHA, human verification, or
other access barriers. Do not treat the sample source settings as blanket
authorization for another source or result. Review access directives and
reuse terms before use.

The package contains the public CPALE passer names as execution evidence.
