# ADR: Accepted PRC Dual-Source Sequence/Name Extraction Method

- **Status:** Owner accepted; method validated for the defined extraction scope
- **Validated implementation scope:** PRC only
- **General acquisition policy:** PRC and CSC
- **Decision date:** 2026-11-03
- **Decision branch:** `docs/accept-prc-mirror-pairing-method`
- **Production / publication:** Not approved by this record

## Owner decision

The owner explicitly accepted this technology and authorized it to be retained as an approved method for PRC sequence-number/name-pair extraction.

## Accepted method

For every PRC or CSC result batch, the normal first action is to attempt downloading the official PDF through its ordinary, authorized download link. Official-PDF acquisition is preferred, but it is optional and is not a hard dependency for a valid extraction. If the official PDF cannot be downloaded through the normal authorized route, proceed with two independently published, publicly accessible transcription sources as the approved fallback:

1. Check each source's `robots.txt` and comply with its access rules.
2. Fetch the required alphabetic result pages using polite request delays and lightweight requests.
3. Parse each record as its original sequence number paired with its passer name.
4. Preserve the source text and non-ASCII characters; do not invent, normalize away, pad, truncate, or silently repair names.
5. Validate complete sequence coverage, missing/extra/duplicate sequence numbers, blank names, and exact sequence/name agreement between both sources.
6. Compare the extracted total against the passer count stated in the relevant official PRC or CSC announcement.
7. Retain source evidence, machine-readable output, hashes, and a validation report.

## Acquisition and Greenlight decision rule

1. **Default:** Attempt the official PRC/CSC PDF download through the normal authorized download option.
2. **Fallback:** If the download fails, continue with two independent, publicly accessible transcription sources. The PDF is preferred evidence, not a mandatory prerequisite.
3. **Pass condition:** Require exact 100% sequence-number/name agreement between the two sources and all completeness, count, blank, duplicate, and anomaly checks described above.
4. **Decision:** If every check passes, the batch may satisfy Greenlight without physical PDF layout verification. If any check fails, hold the batch for review.

## Proof already completed

For the August and September 2026 Nurses Licensure Examination:

- Official PRC announced **28,652 passers**.
- Board Exams PH transcription: **28,652** sequence/name records.
- PRC Board transcription: **28,652** sequence/name records.
- Both datasets covered sequence numbers **1–28,652**.
- Missing sequence numbers: **0** in either dataset.
- Duplicate sequence numbers: **0** in either dataset.
- Blank names: **0** in either dataset.
- Cross-source sequence/name mismatches: **0**.
- The two sources' complete sequence/name pairs matched exactly.

## Mandatory limitations and safety gates

- The official PDF should be attempted first using its normal download option. If that attempt fails, do not repeatedly retry indefinitely and do not treat the failure as an extraction failure.
- Never bypass a permission restriction, sign-in requirement, CAPTCHA, or any other access control. Use the authorized dual-source fallback instead.
- **Physical PDF page geometry, column positions, and layout verification are not mandatory Greenlight requirements** when the PDF cannot be obtained. Do not block a batch solely because those physical-layout properties cannot be inspected.
- The fallback is Greenlight-eligible when all required checks pass: the extracted passer count equals the count in the official PRC/CSC announcement; two independent permitted transcription sources match exactly for every sequence-number/name pair; sequence numbers are complete with no gaps, extras, or duplicates; there are no blank names; and there are no unresolved parsing anomalies.
- The cross-source pair agreement must be **100%**. Any mismatch or failed validation keeps `greenlight=false` and requires review.
- The official announcement remains the authority for the expected passer count; third-party transcriptions do not replace that count authority.
- Any result that fails a check must be held for review; never guess, fill gaps, or auto-publish uncertain data.
- This policy clarification applies to PRC and CSC acquisition decisions. The proven implementation and evidence documented in this ADR remain PRC-only; this record does not authorize making CSC code or dataset changes as part of the completed PRC task.
- This acceptance does not authorize deployment, publication, merging into `main`, or promotion of the experimental extraction workflow to production.

## Reuse rule

The acquisition policy applies to future **PRC and CSC** result batches: attempt the official PDF download first; if it fails, use the dual-source sequence/name fallback and apply the 100% validation gate above. The demonstrated implementation/evidence in this ADR is PRC-only. For each new batch, independently verify the official announcement and expected count, source identity and accessibility, robots/rate-limit compliance, and exact record-level agreement. Retain a separate evidence package and validation report. For each new examination, independently verify the official announced count, the identity and accessibility of both transcription sources, robots/rate-limit compliance, and exact record-level agreement. Record a new evidence package and validation report for each run.

## Evidence from the validated run

- Examination: August and September 2026 Nurses Licensure Examination
- Official announcement: https://www.prc.gov.ph/article/august-and-september-2026-nurses-licensure-examination-results-released-five-5-working-days
- Official PDF Drive file ID: `13u_FOsF3DxS7RvMOdMqsg4Q1HF2rKtvU` (download permission restricted during the run)
- Source 1: https://boardexams.ph/
- Source 2: https://prcboard.com/
- Validation report SHA-256: `4bac02e5eb35d4b467461623b6f62ad4442aa4190b01a3052f98916309f44c23`
- CSV SHA-256: `9a9d282fdef969b81dfa794611ffbe269edf61a4f98c37d69e7e27419993f06f`
- JSONL SHA-256: `1b35544540dd388bea25ce5bcc92d167a1ca7eadb178e3333cd12ce30b5ab0b1`

## Change control

This ADR records the owner's acceptance of the method within the scope stated above. Implementation changes, production integration, Greenlight policy changes, and publication remain governed by `AI_BLUEPRINT.md` and `Master_Technical_Blueprint.md`.
