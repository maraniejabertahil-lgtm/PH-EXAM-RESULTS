# Phase 1 — Official Source Coverage Map

**Audit date:** 2026-11-03  
**Base reviewed:** `main`

## Source matrix

| Authority | Official entry point | Configuration | Coverage decision |
|---|---|---|---|
| PRC | https://www.prc.gov.ph/articles/exam-results | Enabled and authorized. Maximum three listing pages; up to ten matching result articles per page; up to three new articles processed per scan. Attachment label filter: “List of Successful Examinees”. | Bounded listing integration only; not comprehensive coverage of every PRC examination. |
| CSC Region V | https://csc.gov.ph/regional-offices/region-v/examination | Disabled; `manual_drop_required: true`; two owner-approved Drive IDs preserved; prior direct requests returned HTTP 403 security verification. | Keep paused. No CSC live request was made in this audit. Do not bypass security verification. |

## PRC implementation facts

Current `python-engine/config/sources.json` sets `discover_official_result_articles`, `allow_linked_drive_documents`, and `track_new_articles_only` to true. It configures three listing pages, ten matching articles per page, three new articles per scan, and `preemptive_url_templates: []`.

The Worker builds the base listing URL plus `?page=1` and `?page=2`, validates same-origin HTTPS article URLs under `/article/` or numeric `/node/{id}`, and checks the linked document's PDF byte signature before dispatch. Initial snapshot creation skips historical articles. This does not guarantee detection of edits to already-listed articles while the listing fingerprint remains unchanged.

## Latest production observation

Read-only diagnostics: https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/actions/runs/41566334357

At 2026-11-03 02:29:14 UTC, the Worker ran in Peak Week mode. Both PRC listing checks were `unchanged`; six outbound subrequests were used against a limit of 45; no exception appeared in the captured tail. This is baseline monitoring evidence, not a genuine new-result detection or dispatch.

## CPALE source note

At the recorded 2026-11-03 check, the PRC results listing showed the 26 October 2026 Metallurgical Engineers announcement as its newest entry; no October 2026 CPALE result announcement appeared. The official schedule's 3 November date is a target, not a guarantee. The October CPALE item in PRC Downloads is an examination program, not a results document.

## Gaps and restrictions

1. No claim is made that all PRC examinations or all CSC regions are covered.
2. CSC remains disabled; no CSC live request was made.
3. No preemptive URL template is configured. Do not enable guessed patterns.
4. Genuine new PRC result detection and receiver validation remain unproven.
5. Do not treat synthetic tests, historical announcements, third-party mirrors, or an examination program as genuine production result detection.

**Status: PRC listing integration is configured and bounded; CSC Region V is paused; complete source coverage and genuine live detection evidence are not established.**
