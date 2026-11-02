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

No production Watcher source registry, production Worker code, production KV value, or production secret was changed during this audit. No production runtime code or source-registry change was merged. The only operational workflow merged was the read-only diagnostics workflow in PR #18. No Phase 1 acceptance is granted by this report.

**Phase 1 remains operational but incomplete. Phase 2 must not be declared unblocked by the existence of staging extraction code alone.**

## 8. Follow-up work completed on 2026-11-03

- Merged PR #24, adding plain-text Google Drive URL recognition for explicitly owner-enabled official pages. The detector still requires the exact HTTPS `drive.google.com` host, the supported `/file/d/{id}/view` path, an approved/discovered ID from an authorized official page, a permitted Google download redirect, and a real PDF byte signature.
- Merged PR #23, adding a normal GET metadata fallback after an approved page rejects both HEAD and a bounded Range GET. The response body is cancelled immediately; the existing bounded scanners remain responsible for reading page/PDF bytes.
- Merged PR #25, adding opt-in, bounded discovery of up to three same-origin PRC result article pages from an approved listing page. Article links must be same-origin, use an approved `/article/` or `/node/{numeric-id}` path, and have a result-related title. Article PDFs still pass the existing Drive redirect and PDF signature checks. The feature is not enabled in the production source registry.
- The production Worker build and deployment for the PR #25 merge completed successfully. Its tests passed before deployment.
- Merged PR #27 to disable the CSC Region V source while direct requests return HTTP 403 security verification. The approved source record and its historical Drive IDs were preserved, but the source is now disabled and marked for manual-drop fallback. This prevents repeated polling against a site presenting an anti-bot verification barrier.

## 9. PRC source-discovery findings

- The official PRC exam-results listing is `https://www.prc.gov.ph/articles/exam-results`. It lists recent exam-result announcement articles.
- Official PRC announcement pages expose separate Google Drive documents, including a "List of Successful Examinees" file. For example, the official August/September 2026 Nurses announcement links to `https://drive.google.com/file/d/13u_FOsF3DxS7RvMOdMqsg4Q1HF2rKtvU/view?usp=sharing`.
- PRC pages were reachable with HTTP 200 from the GitHub-runner diagnostic. However, the PRC `robots.txt` policy was not successfully verified. Therefore the new PRC article-discovery capability remains opt-in and **no PRC source has been added or enabled in production**.
- The Jina Reader diagnostic returned cached page text with existing CSC Drive IDs, but its fresh/browser-mode response returned HTTP 401 and its JSON response contained a "Just a moment" security-verification page. It is not accepted as a production source or a compliant bypass. It will not be used by the production Watcher.

## 10. Current production source status

- The production registry currently contains one source record, CSC Region V, but it is disabled.
- There are currently **zero enabled automated sources** in production.
- No PRC source is active because its robots policy remains unverified.
- CSC direct automated monitoring is paused because of the security-verification barrier.
- The `manual-drop/` push trigger currently only acknowledges the event; its workflow explicitly does not acquire, extract, or publish results. Manual-drop extraction is therefore **not yet implemented** and must be completed as part of the processing/worker phase before it can be treated as an operational fallback.
- No preemptive URL templates have been configured or proven against a genuine official PDF appearing before its announcement page changes.

## 11. Updated acceptance decision

**PHASE 1 REMAINS NOT ACCEPTED.**

The Watcher runtime, event receiver validation, bounded PDF verification, deduplication, test suite, and deployment pipeline have useful verified evidence. However, the current production source registry has no enabled sources, there is no genuine fresh official PDF detection-to-receiver test, PRC robots policy remains unverified, CSC presents a security-verification barrier, and manual-drop processing is not implemented. Synthetic test fixtures and cached proxy content do not satisfy live-source acceptance.



## 12. Superseding follow-up addendum — 2026-11-03

This addendum supersedes earlier statements in Sections 9–10 that said no PRC source was enabled. It preserves the earlier audit history and records the verified follow-up changes.

### Merged implementation and governance changes

- [PR #22](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/pull/22) added opt-in, provenance-gated discovery of Google Drive documents linked from an owner-approved official page.
- [PR #23](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/pull/23) added a bounded normal-GET fallback when an official page rejects HEAD and Range GET.
- [PR #24](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/pull/24) added exact plain-text Google Drive URL recognition.
- [PR #25](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/pull/25) added opt-in, bounded discovery of up to three same-origin PRC result article pages.
- [PR #26](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/pull/26) added owner-configured attachment-label filtering, allowing the PRC source to select only the “List of Successful Examinees” document.
- [PR #27](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/pull/27) paused CSC automated polling after direct requests returned HTTP 403 and marked that source as requiring manual handling. This pause was preserved; it was not reversed by subsequent work.
- [PR #30](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/pull/30) registered the official PRC homepage as a safe baseline-only source and added source-registry tests.
- [PR #31](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/pull/31) corrected listing-page versus article-page provenance and added receiver-side validation for same-origin PRC article URLs.
- [PR #32](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/pull/32) enabled the robots-compliant PRC article-discovery configuration with a strict successful-examinees attachment filter.

All listed PRs passed their required Watcher tests and preview/deployment checks before merge. Production Worker deployments after code changes completed successfully.

### Current production source registry

The registry now contains two source records:

1. **PRC homepage — enabled**
   - URL: `https://www.prc.gov.ph/`
   - Official source; `file_format: pdf`
   - `discover_official_result_articles: true`
   - `allow_linked_drive_documents: true`
   - Attachment label filter: `list of successful examinees`
   - Follows at most three same-origin result article pages under `/article/` or numeric `/node/{id}` paths.
   - `scan_page_on_baseline: false`, `direct_drive_fallback: false`, `auto_acquire: false`, and no static Drive IDs. Initial setup therefore does not dispatch historical PDFs.
   - The PRC robots.txt was retrieved with HTTP 200. Its disallowed paths are administrative, authentication, search, and system paths; it does not disallow the public `/article/` or numeric `/node/{id}` result pages.
   - The production Worker can retrieve the PRC homepage and has an established baseline. A post-PR #32 live scheduled event observed at 22:51:14 UTC reported `unchanged` for the PRC homepage in both Peak Week scans; no historical document was dispatched by baseline setup.

2. **CSC Region V — disabled**
   - URL: `https://csc.gov.ph/regional-offices/region-v/examination`
   - Remains disabled with `manual_drop_required: true` and the HTTP 403 security-verification reason.
   - The exact two owner-approved Drive IDs remain in the registry.
   - Both the Cloudflare Worker and GitHub runner received HTTP 403 from the CSC page, including the `www` and canonical host variants. Existing previously dispatched IDs remained deduplicated.
   - Do not re-enable CSC polling until official access is available or an approved alternative is verified.

### Runtime evidence and safety

- A live scheduled Worker event at 22:51:14 UTC, after PR #32, reported two configured sources and one enabled source. The PRC homepage check used 6 outbound subrequests against the 45-request safety limit and produced no runtime exceptions. The Cloudflare schedules API returned HTTP 200 and confirmed the deployed cron `* * * * *`.
- `PEAK_WEEK=true` was observed in production KV diagnostics; this work did not change that value.
- The Worker automatically created/uses its normal PRC homepage baseline state. No production KV values were manually edited and no secrets were changed.
- Phase 1 remains validation-only: no PDF acquisition, extraction, or publication was performed.
- The post-PR #32 scheduled event reported Worker `scriptVersion.id` `305e915d-099b-479d-bb28-c57c90cc3a35`.

### Remaining acceptance gaps

- No newly published PRC result article has yet caused a genuine live PDF detection-to-GitHub-receiver event. The PRC crawler is enabled and waiting for a homepage change that exposes a result article.
- The crawler only follows up to three matching same-origin article links when the homepage fingerprint changes. It does not independently poll already-listed article pages for later edits when the homepage itself remains unchanged.
- CSC automated discovery remains paused. The `manual-drop/` push trigger is currently only an acknowledgement placeholder; its workflow explicitly performs no result processing. A functioning owner-triggered manual validation/import route is still outstanding.
- Coverage is not complete across PRC examination categories or all 16 CSC regions.
- No preemptive URL template has been proven against a genuine official PDF appearing before its announcement page changes.

**Updated decision: PHASE 1 REMAINS NOT ACCEPTED.** The PRC source path is now configured and safely gated, but acceptance still requires a genuine live detection-to-receiver event, duplicate-prevention evidence for that event, complete approved source coverage, and an operational CSC fallback path.
