# Phase 1 Official Source Coverage Map

**Audit date:** 2026-11-03  
**Repository branch reviewed:** `main`  
**Scope:** Public, official PRC and CSC result-discovery entry points. This is a read-only source-coverage assessment; it does not authorize new scraping behavior or change production configuration.

## Executive finding

The production Watcher registry is not yet a complete PRC/CSC source map. It currently contains one enabled PRC record whose configured URL is the general homepage, and one disabled CSC Region V record. The official PRC result listing and the official CSC examination portal provide stronger source candidates, but neither is yet proven end-to-end from the deployed Watcher.

## Evidence-based source matrix

| Authority | Official entry point | What the public page establishes | Watcher compatibility | Current decision |
|---|---|---|---|---|
| PRC | `https://www.prc.gov.ph/articles/exam-results` | Official, dated exam-result announcements; the listing has pagination (for example, `?page=1`). Result detail pages expose separate links including “List of Successful Examinees”. | Strong candidate. Existing discovery code recognizes same-origin `/article/` and numeric `/node/{id}` links, and filters Drive attachment labels. However, the production registry currently points at `https://www.prc.gov.ph/`, not this dedicated listing. The crawler follows at most three matching article links from one page and rejects query-string article links; it does not crawl listing pagination. | Prefer the dedicated listing as the PRC monitoring entry point, after isolated tests and bounded-request analysis. Do not claim full PRC coverage yet. |
| CSC | `https://exam.csc.gov.ph/list_passers.php` | The official CSC portal exposes sections for CSE Pen and Paper, Computer Examination, CS Digital Exam, FOE, POE, BCLTE, CSE-FSO, MISE, and non-CSE tests. CSE search uses exam date and region filters. CSC official release/advisory pages direct examinees to this portal and warn against unofficial copies. | Candidate only. Public browser/search visibility does not prove that Cloudflare Worker requests can retrieve the page or any underlying result records. The page appears to be a filter/search interface, not a verified bulk PDF feed. No request should be sent to guessed internal endpoints. | Conduct one compliant, low-rate, read-only availability/content-type check through an authorized diagnostic path. If blocked, stop and retain manual fallback. |
| CSC regional pages | Example: `https://csc.gov.ph/regional-offices/region-v/examination` | Official regional information pages exist and may link to result announcements/documents. | Production and GitHub-runner diagnostics previously received HTTP 403 security verification on CSC regional URLs and canonical/www variants. | Keep CSC automated regional polling disabled. Do not bypass CAPTCHA, Cloudflare, or other access controls. |

## Relevant official evidence

### PRC

- Official listing: https://www.prc.gov.ph/articles/exam-results
- The current listing shows dated announcements for multiple professions and examination types.
- A paginated listing page is also publicly exposed at: https://www.prc.gov.ph/articles/exam-results?page=1
- Example official result detail page: https://www.prc.gov.ph/node/9450
- PRC result detail pages expose distinct result-document labels, including “List of Successful Examinees”.

### CSC

- Official CSC portal: https://exam.csc.gov.ph/list_passers.php
- The portal presents exam-type categories and, for CSE, date and region filters.
- Official CSC release page: https://www.csc.gov.ph/csc-releases-results-of-8-march-2026-civil-service-exam
- Official CSC advisory example: https://www.csc.gov.ph/examination-advisories/examination-advisory-no-17-s-2026-update-on-the-release-of-examination-results-for-the-09-august-2026-career-service-examination-pen-and-paper-test
- CSC states that only its own List of Passers is official and cautions against unauthorized reposts.

## Implementation findings from current `main`

1. `python-engine/config/sources.json` currently has exactly two records: CSC Region V (disabled) and PRC homepage (enabled).
2. PRC is configured with `discover_official_result_articles: true`, `allow_linked_drive_documents: true`, and the “list of successful examinees” attachment-label filter.
3. `findOfficialResultArticleLinks()` in `watcher-bot/src/index.js`:
   - searches only the supplied page;
   - accepts same-origin `/article/` or numeric `/node/{id}` paths;
   - stops after three matching links;
   - rejects links containing a query string or fragment.
4. Consequently, the dedicated PRC listing's `?page=1` pagination is not traversed by the current discovery routine. The current production source URL is also the general homepage rather than the dedicated result listing.
5. The current audit evidence confirms a live scheduled PRC baseline check, not a genuine newly announced result PDF detection or dispatch.
6. No official CSC portal request from the deployed Worker has been verified in this audit. A page appearing in a public search result is not proof of Worker access or a machine-readable result endpoint.

## Safe next implementation sequence

1. Add focused tests for the dedicated PRC listing page, including pagination links, article discovery, result-label filtering, duplicate article URLs, and bounded page/article counts.
2. Design the PRC crawler budget against the existing hard limits: 10 targets and 45 outbound subrequests per invocation, with both Peak Week scans sharing the invocation budget. Avoid unbounded pagination or broad link crawling.
3. On an isolated branch, update the PRC source entry to the dedicated official result listing only after tests prove the discovery path and baseline behavior. Preserve the existing source identity/deduplication behavior or provide an explicit migration strategy so historical dispatch keys are not accidentally reset.
4. For CSC, test only the public portal's documented landing page with a disclosed User-Agent and a single low-rate request from the authorized diagnostic environment. Do not reverse-engineer or call undocumented search endpoints. If a security challenge or 403 appears, stop automated access and keep the source disabled.
5. Do not enable guessed preemptive URL templates. CSC's region/date result pages and PRC's descriptive article slugs do not establish stable future PDF URL patterns.
6. Acceptance still requires a genuine new official result detection-to-receiver event, duplicate-suppression evidence, and approved coverage across the intended PRC exam catalogue and CSC examination types/regions.

## Explicit non-claims

- This document does not claim all PRC examination categories are covered.
- This document does not claim all 16 CSC regions or all CSC examination types are monitored.
- It does not claim that the CSC portal is accessible from Cloudflare Workers.
- It does not claim that the PRC crawler has dispatched a new result PDF in production.
- It does not authorize CAPTCHA/anti-bot bypass, undocumented endpoint use, or guessed URL probing.
- It does not change production Worker code, source registry, KV, secrets, or deployment.

**Status: source mapping advanced; Phase 1 remains NOT ACCEPTED.**
