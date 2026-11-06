# Phase 1 Official Source Coverage Map

**Audit date:** 2026-11-03  
**Repository branch reviewed:** `main`  
**Scope:** Read-only assessment of the official PRC result-listing integration and CSC source state. This document does not authorize new scraping behavior or change production configuration.

## Executive finding

The production Watcher has one enabled official PRC source and one disabled official CSC source. The PRC source is configured to the **dedicated exam-results listing**, not the general PRC homepage. Its current implementation fetches up to three listing pages, discovers bounded batches of new result articles, and follows only approved result-document links. This is meaningful PRC monitoring coverage, but it is not complete coverage of every PRC examination or any claim of full CSC coverage.

## Evidence-based source matrix

| Authority | Configured official entry point | Current Watcher behavior | Current decision |
|---|---|---|---|
| PRC | `https://www.prc.gov.ph/articles/exam-results` | Enabled. Fetches the listing and up to two paginated pages (`?page=1`, `?page=2`); searches up to 10 matching result articles per page; tracks newly discovered article URLs; scans at most 3 new articles per invocation; filters article attachments for “List of Successful Examinees”; validates the linked file as a PDF before dispatch. | Keep enabled. Coverage is bounded to the configured listing pages and matching article titles/attachments; do not claim all PRC exams are covered. |
| CSC Region V | `https://csc.gov.ph/regional-offices/region-v/examination` | Disabled with `manual_drop_required: true`. The source record preserves two exact owner-approved Drive IDs. Prior diagnostics recorded HTTP 403 security verification. | Keep disabled. No CSC live request was made during this follow-up. Do not bypass access controls or infer coverage of other regions/exam types. |

## PRC implementation details verified in current `main`

1. `python-engine/config/sources.json` contains exactly two records: PRC (enabled) and CSC Region V (disabled).
2. The PRC source URL is the dedicated official result listing: `https://www.prc.gov.ph/articles/exam-results`.
3. PRC source settings include:
   - `discover_official_result_articles: true`
   - `allow_linked_drive_documents: true`
   - `drive_link_text_patterns: ["list of successful examinees"]`
   - `result_listing_page_count: 3`
   - `max_result_articles_per_page: 10`
   - `max_new_result_articles_per_scan: 3`
   - `track_new_articles_only: true`
4. `findOfficialResultArticleLinks()` builds the base listing URL plus `?page=1` and `?page=2`, with a hard maximum of three pages and ten matching articles per page.
5. Article URLs must be HTTPS, same-origin, and use `/article/` or a numeric `/node/{id}` path. Query strings and fragments on article URLs are rejected.
6. The article snapshot prevents historical announcements from being imported during initial baseline creation. New articles are processed in batches of at most three per invocation; articles are only marked processed after their matching document reaches a terminal successful dispatch state.
7. The Worker validates the linked document as a real PDF (including the PDF byte signature) before dispatch. A Drive viewer/sign-in page or non-PDF response is not accepted as a result PDF.
8. The two Peak Week scans share the invocation's outbound-subrequest budget. The configured hard safety limit is 45 subrequests per invocation.

## Official PRC checks relevant to the CPALE watch

- The official result listing currently shows 26 October 2026 Metallurgical Engineers as its newest result announcement; no October 2026 CPALE result announcement appears in the listing at this check.
- The official 2026 examination schedule lists 3 November 2026 as the *target* CPALE result-release date. A target date is not a guarantee that results will be published that day.
- The official PRC Downloads page contains an “October 2026 Certified Public Accountants Licensure Examination” PDF in its Board Programs section. Opening it identifies it as the **examination program**, not the results or list of passers. It must not be mistaken for a result document.
- The official result listing and official downloads catalogue are different resources. The current Watcher monitors the result listing; it does not treat every newly listed board-program PDF as an examination result.

## CSC status and test boundary

- CSC Region V remains disabled because earlier direct requests encountered HTTP 403 security verification.
- This follow-up performed no CSC-side live request, in accordance with the owner’s exclusion of CSC live testing.
- No undocumented CSC endpoints, guessed URLs, CAPTCHA workarounds, or security-verification bypasses are authorized.
- The two existing owner-approved Drive IDs remain preserved in the disabled source record.

## Remaining Phase 1 evidence gaps

1. **Complete approved source coverage:** The current PRC listing path is bounded and does not establish coverage of every PRC exam category. CSC remains disabled, and no all-region coverage is claimed.
2. **Genuine detection-to-receiver proof:** A newly published official PRC result article/PDF must be observed by the production Watcher and accepted by the production receiver. Preserve evidence of the real event and duplicate suppression.
3. **Genuine preemptive proof:** No official future-PDF URL template is currently configured. Do not enable guessed templates; first establish a stable official pattern from historical evidence and then observe a genuine pre-announcement PDF.
4. **Peak Week behavior:** The production log evidence already records both scans with `mode=peak_week` and `PEAK_WEEK=true`. The implementation waits 30 seconds between the two scans. This proves execution of the two-scan path, not a genuine preemptive PDF hit.

## Explicit non-claims

- This document does not claim complete coverage of all PRC examinations.
- It does not claim coverage of all CSC regions or examination types.
- It does not claim a genuine new PRC result PDF has been dispatched in production.
- It does not claim a preemptive official PDF has been detected.
- It does not authorize CAPTCHA/anti-bot bypass, undocumented endpoint use, or guessed URL probing.
- It does not change production Worker code, source registry, KV, secrets, or deployment.

**Status: PRC official listing integration verified; Phase 1 remains NOT ACCEPTED pending genuine live detection-to-receiver and preemptive evidence plus complete owner-approved coverage.**
