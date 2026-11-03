# ADR: Accepted PRC Dual-Source Sequence/Name Extraction Method

- **Status:** Owner accepted; method validated for the defined extraction scope
- **Authority:** PRC only
- **Decision date:** 2026-11-03
- **Decision branch:** `docs/accept-prc-mirror-pairing-method`
- **Production / publication:** Not approved by this record

## Owner decision

The owner explicitly accepted this technology and authorized it to be retained as an approved method for PRC sequence-number/name-pair extraction.

## Accepted method

When an official PRC result PDF is unavailable through authorized download, use two independently published, publicly accessible transcription sources as a cross-checking fallback:

1. Check each source's `robots.txt` and comply with its access rules.
2. Fetch the required alphabetic result pages using polite request delays and lightweight requests.
3. Parse each record as its original sequence number paired with its passer name.
4. Preserve the source text and non-ASCII characters; do not invent, normalize away, pad, truncate, or silently repair names.
5. Validate complete sequence coverage, missing/extra/duplicate sequence numbers, blank names, and exact sequence/name agreement between both sources.
6. Compare the extracted total against the official PRC-announced passer count.
7. Retain source evidence, machine-readable output, hashes, and a validation report.

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

- This method is proven for **sequence-number/name pairing against two public transcriptions**. It is not evidence that the inaccessible official PDF itself was downloaded or OCR-extracted.
- The official Drive PDF download returned an owner-permission restriction. Do not bypass that restriction, sign-in requirements, CAPTCHA, or any other access control.
- Original PDF page geometry, physical column positions, and physical layout have **not** been verified by this method.
- A successful two-source match and count match do not, by themselves, satisfy the project's full Greenlight Protocol or authorize publication.
- Keep `greenlight=false` whenever required official-source or layout checks remain unverified.
- Any result that fails a check must be held for review; never guess, fill gaps, or auto-publish uncertain data.
- This acceptance does not authorize changes to CSC sources, datasets, workflows, or code.
- This acceptance does not authorize deployment, publication, merging into `main`, or promotion of the experimental extraction workflow to production.

## Reuse rule

The method may be reused for future **PRC-only** extraction attempts when official source acquisition is blocked or unavailable, subject to the checks and limitations above. For each new examination, independently verify the official announced count, the identity and accessibility of both transcription sources, robots/rate-limit compliance, and exact record-level agreement. Record a new evidence package and validation report for each run.

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
