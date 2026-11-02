# PH-EXAM-RESULTS — Phase 1 Watcher Acceptance Audit

**Audit date:** 2026-11-03  
**Audited branch:** `main`  
**Result:** **NOT ACCEPTED — operational core verified; source coverage and genuine preemptive detection remain incomplete.**

This report records live repository, GitHub Actions, Cloudflare diagnostics, and official-source checks. It deliberately separates verified production behavior from automated simulations and staging-only work.

## 1. Verified production state

- Cloudflare Watcher production deployment completed successfully on 2026-11-02.
- Cron configuration is `* * * * *`.
- Production Worker tail showed successful cron execution with no exceptions.
- Production `PEAK_WEEK` KV key was absent (HTTP 404), so the Worker correctly operated in standard mode. No production KV value was changed.
- The enabled production source registry contains exactly one source: CSC Region V, 09 August 2026 CSE-PPT results.
- The CSC source returned HTTP 403 during the diagnostic window. Its two exact owner-approved Google Drive fallback IDs were already marked dispatched.
- The production `source-detected` receiver accepted two synthetic diagnostic events. Both receiver runs succeeded and produced validation-only artifacts. The artifacts explicitly recorded `pdf_acquired=false`, `extraction_performed=false`, and `published=false`.
- The receiver therefore has live validation evidence, but no fresh PDF was acquired or processed during this test.

## 2. Automated test evidence

- Main-branch Watcher test suite: 21 passed, 0 failed.
- Main-branch Python approved-Drive retrieval suite: 9 passed, 0 failed.
- All 18 branches with Watcher/processing quality-check evidence have at least one successful run. The diagnostics-only branch also completed its read-only diagnostics run successfully.
- Two staging branches that previously had no recorded quality run were tested through temporary draft PRs:
  - `staging/node-pdf-extraction`: 21 Watcher tests and 9 Python tests passed.
  - `staging/private-csc-ocr`: 21 Watcher tests and 9 Python tests passed.
- Temporary validation PRs #19 and #20 were closed without merging. Their temporary CI trigger files were removed.
- PR #18, which adds a read-only Cloudflare diagnostics workflow, was merged as commit `ebaae3f2d7268ab291c2d3468495d80a25bb7bfd`. The workflow uses `contents: read`; its successful diagnostic run did not modify production KV or Worker secrets.

Successful CI on individual branches is branch-level test evidence; it does not mean all branches have been merged or that every branch has been reconciled with `main`.

## 3. Source coverage gap

The production file `python-engine/config/sources.json` currently contains only one enabled CSC Region V source. It is not a complete PRC/CSC source registry.

PR #15 (`staging/prc-let-support`) contains three sample PRC source records (March 2026 LEPT Elementary, March 2026 LEPT Secondary, and February 2026 Nurses) and a separate private extraction foundation. It remains a draft and is not integrated into the production Watcher registry. Those historical records must not be treated as complete future-result monitoring coverage.

Official-source checks confirm that PRC result announcements use descriptive article URLs and link to Google Drive documents. For example:
- PRC August/September 2026 NLE announcement: https://www.prc.gov.ph/article/august-and-september-2026-nurses-licensure-examination-results-released-five-5-working-days
- Official list-of-successful-examinees Drive file: https://drive.google.com/file/d/13u_FOsF3DxS7RvMOdMqsg4Q1HF2rKtvU/view?usp=sharing
- CSC Region V 09 August 2026 results page: https://www.csc.gov.ph/regional-offices/region-v/examination/results-10072026
- CSC Region V 08 March 2026 results page: https://www.csc.gov.ph/regional-offices/region-v/examination/results-05052026

The two CSC date-stamped page examples are not enough evidence to generalize a future URL template across CSC regions or examination dates. PRC article slugs are descriptive and do not establish a predictable future URL pattern.

## 4. Preemptive URL detection gap

- The Watcher code supports `preemptive_url_templates` and performs HEAD checks on expanded targets during Peak Week.
- The production source registry currently has no `preemptive_url_templates`.
- The successful preemptive URL tests use synthetic fixture domains and URLs. They verify the implementation logic, not a real PRC/CSC official future-result URL.
- No genuine production event has yet demonstrated that an official result PDF was found by a preemptive HEAD request before its announcement page changed.

Do not add guessed production URL templates. Add a template only after its pattern has been established from sufficient official historical examples and verified against the responsible authority's actual URL behavior.

## 5. Remaining acceptance criteria

1. Build a complete, owner-approved PRC/CSC source registry, with verified official source pages and safe document-link handling.
2. Establish official URL patterns before enabling production preemptive templates. Where an authority uses unpredictable article slugs or newly generated Drive IDs, document and implement an approved discovery method rather than guessing.
3. Perform a genuine live test in which a newly available official PDF is detected, verified, and dispatched to the production receiver.
4. Preserve receiver evidence proving validation, duplicate prevention, and correct handling of unapproved URLs. Keep acquisition/extraction/publication out of Phase 1 receiver tests.
5. Re-run production diagnostics after any approved source-registry or Watcher configuration change.

## 6. Safety and deployment statement

No production Watcher source registry, production Worker code, production KV value, or production secret was changed during this audit. The only merge was the read-only diagnostics workflow in PR #18. No Phase 1 acceptance is granted by this report.

**Phase 1 remains operational but incomplete. Phase 2 must not be declared unblocked by the existence of staging extraction code alone.**
