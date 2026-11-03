# PH-EXAM-RESULTS — Phase 1 Watcher Acceptance Audit

**Audit date:** 2026-11-03  
**Audited base:** `main`  
**Decision:** **NOT ACCEPTED**

This report distinguishes verified production monitoring from unproven live detection. It does not authorize changes to production Worker code, KV, secrets, schedules, or CSC access.

## 1. Current production source registry

The current `python-engine/config/sources.json` contains two records:

- **PRC — enabled and owner-authorized.** Dedicated official listing: `https://www.prc.gov.ph/articles/exam-results`.
- **CSC Region V — disabled.** Direct access previously returned HTTP 403 security verification. The two owner-approved Drive IDs remain preserved. No CSC live request was made for this audit.

PRC listing limits:
- Three listing pages maximum: base listing, `?page=1`, and `?page=2`.
- Up to ten matching result articles per page.
- Up to three newly discovered articles processed per scan.
- Historical articles are skipped when the initial snapshot is created.
- Attachment label filter: “List of Successful Examinees”.

This is bounded PRC listing coverage, not comprehensive coverage of every PRC examination.

## 2. Production runtime evidence

Read-only diagnostics: https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/actions/runs/41566334357

The captured production observation at 2026-11-03 02:29:14 UTC recorded:
- Active Worker version `017cbb5d-94db-4804-a3bd-f95a72d3f353`, at 100% traffic.
- Production Cron: `* * * * *`.
- Peak Week mode enabled in the observed runtime.
- Two PRC listing checks, both `unchanged`.
- Two configured sources; one approved enabled source.
- Six outbound subrequests against the safety limit of 45.
- No exceptions in the captured tail.

This proves scheduled baseline checking and the two-scan Peak Week path for that invocation. It does **not** prove a new result detection, genuine PDF dispatch, receiver acceptance, live duplicate suppression, or preemptive PDF discovery.

## 3. Phase 1 boundary

Phase 1 covers scheduled source monitoring, bounded official listing discovery, preemptive checks where an official URL pattern is proven, safe event dispatch, and receiver-side provenance/authorization validation.

The receiver in `.github/workflows/process-import.yml` is validation-only. Its report records that PDF acquisition, extraction, and publication did not occur. The `manual-drop/` push path currently acknowledges a file change only; it is not a working extraction/import pipeline. These are downstream processing/integration dependencies and must not be misclassified as standalone Watcher acceptance tests.

## 4. Acceptance evidence matrix

| Requirement | Status | Evidence / gap |
|---|---|---|
| Production deployment and one-minute cron | Verified | Read-only Cloudflare diagnostics |
| PRC dedicated listing and bounded pagination | Verified in current `main` | Source registry and Worker implementation |
| Peak Week two-scan execution | Verified for captured invocation | Both scans reported `unchanged` |
| Genuine new official result detection | Not demonstrated | No genuine new article/PDF observed |
| Production dispatch and receiver acceptance | Not demonstrated | No genuine production event evidence |
| Live duplicate suppression | Not demonstrated | Automated tests are not live event proof |
| Genuine preemptive PDF detection | Not demonstrated | No verified official template is configured |
| Complete owner-approved source coverage | Not established | PRC coverage is bounded; CSC Region V paused; no all-region claim |

## 5. Outstanding Phase 1 work

1. Observe a genuinely new official PRC result article/PDF through production detection and receiver validation; retain the event and run evidence.
2. Verify duplicate suppression through a legitimate repeated event without creating duplicate processing.
3. Establish a future-PDF URL template only from sufficient official historical evidence, then prove it against a genuine pre-announcement PDF. Do not guess templates.
4. Expand source coverage only through owner-approved, official, compliant sources. CSC live testing remains excluded; do not bypass its security verification.
5. Keep extraction and publication disabled until their separate validation and Greenlight requirements are satisfied.

## 6. Safety statement

No production Worker code, source registry, KV value, secret, schedule, or deployment was changed by this audit. No CSC live request was made. No historical result was dispatched to simulate a new announcement.

**Final decision: PHASE 1 REMAINS NOT ACCEPTED.** Production scheduling, PRC baseline monitoring, and Peak Week two-scan execution are evidenced. Genuine live detection-to-receiver proof, live duplicate evidence, genuine preemptive proof, and complete approved source coverage remain outstanding.
