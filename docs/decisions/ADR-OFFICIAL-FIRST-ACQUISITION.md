# ADR — Official-First Acquisition and Verified Third-Party Fallback

- **Status:** Accepted
- **Scope:** PRC and CSC result acquisition
- **Decision:** Official source first; third-party transcription only after documented official retrieval failure
- **Budget:** $0; existing free-tier architecture only

## Context

The platform must prioritize the original authority publication. A third-party transcription can be useful when an official document is genuinely unavailable, but it must never silently replace a retrievable official source or be misrepresented as an official extraction.

## Decision

1. For every release, attempt the official PRC/CSC announcement and its linked result document/data first.
2. Use only legitimate, authorized, low-impact retrieval. Respect robots.txt, rate limits, redirects, and access controls.
3. Verify the response is the expected document/data. HTML login/interstitial pages, error pages, unrelated files, and non-PDF responses are not accepted as official PDFs.
4. A single failed request is not enough. Record compliant retrieval attempts, timestamps, URLs, HTTP/content-type outcomes, final URL, document verification, and failure reason.
5. Only after official retrieval is confirmed unavailable may the system use two independent, publicly accessible, owner-approved/verified third-party transcriptions.
6. Third-party fallback passes only when every sequence-number/name pair agrees exactly across both sources, the total equals the official announced passer count, and sequence coverage has no gaps, extras, duplicates, blanks, or unresolved anomalies.
7. If any gate fails, stop publication. Do not auto-publish.
8. Preserve provenance:
   - `official_direct` means extracted from the official document/data.
   - `third_party_fallback` means transcribed from two independent third-party sources after documented official retrieval failure.
9. Never describe fallback data as extracted from an official PDF.
10. Never bypass permissions, sign-in, CAPTCHA, MFA, robots.txt, or other access controls. If human verification is required, stop automation and use the approved manual process.

## Required website/system behavior

- Show and retain the source/provenance classification in owner-facing processing reports and dataset metadata.
- Preserve official failure evidence and both fallback source references.
- Keep the prior known-good public dataset unchanged whenever acquisition or validation fails.
- Apply the same policy to PRC and CSC, while respecting the task's approved authority/examination scope.

## Acceptance criteria

- An available official document is selected ahead of third-party transcriptions.
- Third-party fallback is rejected when official-attempt evidence is absent or incomplete.
- A first failed request does not independently unlock fallback.
- Mismatching source pairs, count mismatch, gaps, duplicates, blanks, or anomalies block publication.
- The provenance label cannot misstate third-party data as official extraction.
