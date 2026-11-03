# PRC Sequence-Number / Name Pairing Engine
Status: design specification; private PRC staging only; not approved for publication.

## Objective
Extract each officially printed sequence number and its corresponding passer name as one indivisible record. Preserve the source PDF's page, physical column, within-column row order, and bounding-box evidence. Never infer a missing sequence number, name, or pair.

## Scope and invariants
- PRC sources only. Do not change, inspect, or process CSC data in this implementation.
- Use the approved public source registry and existing strict Google Drive URL / PDF signature checks.
- Python is the primary parser, pairing, validation, and report engine.
- Keep all PDFs, page renders, OCR text, candidate records, and reports in private, short-retention CI artifacts.
- No public dataset, PR, auto-merge, announcement, or live-site change from this extraction experiment.
- Expected passer count is a validation reference, never a value used to create, pad, truncate, or repair records.
- A sequence number must be physically present in the source and geometrically paired with a name.

## Technology-neutral discovery and proof rule
- No parser, OCR engine, library, model, framework, runtime, or custom/invented technology is preselected or approved by this specification.
- Do not add a technology to the approved architecture, dependency files, workflows, or long-term documentation merely because it is popular, available, open-source, or theoretically suitable.
- First establish the actual PDF characteristics and failure mode from authorized real PRC input. Then investigate and prototype the strongest compliant approaches, including a newly invented method where useful.
- A prototype may use temporary isolated dependencies and code on a private experimental branch. Keep experiments disposable until they pass the proof gates below.
- Compare alternatives on the same real PRC pages and, where possible, against independently reviewed ground truth. Synthetic fixtures may test logic but cannot prove real-document extraction accuracy.
- Approve and retain only the smallest method or combination that demonstrably meets the acceptance criteria, works within the $0 budget, and complies with source authorization, robots.txt, rate limits, privacy, and security rules.
- If no candidate passes, do not designate a winner. Record the measured failure and continue research or require manual review.

### Proof gates before adoption
1. **Input proof:** Successfully acquire the authorized original PDF and verify its signature, page count, byte size, and SHA-256.
2. **Layout proof:** Demonstrate correct page, physical-column, row, and reading-order reconstruction against the actual rendered pages.
3. **Pairing proof:** Demonstrate exact printed sequence-number-to-name pairing, including leading zeroes, either-side number placement, multi-column pages, and any wrapped names present.
4. **Accuracy proof:** Reconcile every record against the official expected passer count and independently reviewed page/row evidence; report omissions, extras, duplicates, and unresolved records separately.
5. **Reliability proof:** Repeat the run and confirm deterministic output, explainable exceptions, and no silent guesses.
6. **Efficiency proof:** Measure runtime and peak memory on the free CI runner; remain within the project budget and execution limits.
7. **Compliance proof:** Confirm the method uses only authorized public results and permitted access; no CAPTCHA, access-control, rate-limit, or privacy bypass.
8. **Retention decision:** Only after all applicable gates pass may the proven implementation and its exact dependencies be recorded as adopted. Otherwise keep it experimental or discard it.

## Pipeline

### A. Acquisition and immutable source evidence
- Resolve exactly one enabled, authorized PRC source by registry ID.
- Download only through the existing allow-listed HTTPS Drive path and exact file ID checks.
- Verify PDF signature, byte limit, page count, and SHA-256.
- Keep the source PDF unchanged for the duration of the run.
- Choose rendering resolution experimentally from the actual document. Record the resolution and prove that it is sufficient without wasting CI time or memory.

### B. Layout and column segmentation
- Inspect whether each page contains selectable text, embedded images, vector glyphs, or a mixture. Any prototype must retain word-level or region-level coordinates; do not flatten the page to a text string.
- Detect page content bounds and exclude repeated headers/footers only when confirmed by page-position and repetition analysis. Keep excluded text in diagnostics.
- Identify physical columns from measurable page geometry and validate the result against rendered page evidence. Do not rely on one global threshold unless real-page tests prove it is reliable.
- Assign every word/block a page ID, column ID, bounding box, baseline, and source-engine ID.
- Preserve physical layout. Reading order is page ascending, then columns left-to-right, then rows top-to-bottom, unless visual inspection proves the PDF's actual order differs. Record the selected rule in the report.

### C. Row and sequence-number detection
- Detect sequence tokens using a configurable numeric grammar, initially digits only with optional separators only when visibly printed. Do not assume sequence numbers start at 1, are contiguous, or equal the record index.
- Detect candidate name spans using text geometry and name-like typography/shape. Do not discard names solely because punctuation, accents, suffixes, or initials are present.
- Establish row bands from text baselines and vertical overlap. Estimate row height per column from robust median spacing; allow wrapped names only when adjacent lines are geometrically connected and no competing sequence token intervenes.
- Locate the sequence token and name in the same row band. Permit sequence token on either side of the name, because layout can vary.
- Pair by same page + same column + overlapping row baseline / row band. Never pair by nearest text in a flattened page string.
- If two sequence tokens or two plausible names compete for one row, if a row spans columns, or if geometry is ambiguous, emit an unresolved candidate rather than guessing.
- A sequence token without a name and a name without a sequence token are separate unresolved records, not silently dropped.

### D. Independent recognition and reconciliation
- Compare independently produced readings of the same source regions wherever the page structure or recognition quality makes cross-checking necessary. The independent methods must not merely repeat the same underlying recognition pass.
- For image-only pages, require at least two genuinely independent readings for sequence and name, then compare normalized token text and geometry. Agreement is supporting evidence, not proof.
- Re-run flagged regions using a separately tested capture/recognition configuration; retain original and revised outputs.
- Never autocorrect a name using a dictionary, internet lookup, expected sequence, or another person's record.
- Keep raw text exactly as extracted; normalized comparison fields are additional fields only.

### E. Canonical record schema
Each candidate record must contain:
- source_id, source_pdf_sha256
- page_number, physical_column_number, row_order_in_column
- printed_sequence_raw, printed_sequence_normalized (string; preserve leading zeroes)
- passer_name_raw, passer_name_normalized
- sequence_bbox, name_bbox, row_bbox (PDF-point coordinates)
- extraction_method(s), recognition_confidence(s), source_text_availability
- pairing_method, pairing_confidence, review_flags
- source_snippet / crop reference (private artifact only)

Sequence numbers are strings, not integers, so leading zeroes and printed formatting are not lost. Public array data may later convert types only after the source's number format is proven and the schema is approved.

## Pairing confidence
Use an explainable rule-based score, not an opaque model:
- Same physical page and same segmented column: mandatory.
- Baseline / row-band overlap: mandatory for automatic pairing.
- One unambiguous sequence candidate and one unambiguous name candidate in the row: mandatory.
- OCR agreement and text-engine agreement: supporting evidence.
- Confidence below the configured threshold, competing candidates, split/wrapped ambiguity, or cross-column proximity: manual review.
A high score never overrides a hard failure.

## Validation / Greenlight gates
A batch is eligible for Greenlight only if all are true:
1. Extracted record count exactly equals the official expected passer count.
2. Every record has exactly one non-empty name and exactly one printed sequence number.
3. No duplicate normalized sequence numbers.
4. No duplicate full records; repeated names alone are flagged for review, not automatically deleted, because distinct people may share a name.
5. No missing sequence values among the sequence values actually expected by the source. Do not assume continuity unless the document or official instructions establish it.
6. No unresolved rows, OCR disagreements, low-confidence fields, or unreviewed crops.
7. Page/column/row order and column boundaries pass visual sampling and structural checks.
8. Independent full-document or page-batched reconciliation finds no omissions or extra records.
9. The exact source PDF hash and expected count are attached to the report.

Count equality alone is insufficient: a missing record and an extra record can cancel. The report must separately show missing, extra, duplicate, and unresolved counts.

## Private outputs
- source acquisition report with URL, Drive ID, hash, bytes, and page count
- per-engine raw word/box outputs
- canonical candidate JSONL (one record per line)
- side-by-side page/column text reconstruction
- page preview/contact sheets with candidate boxes and sequence/name pair connectors
- validation report with expected/actual counts and every exception
- no publication-ready dataset unless every gate passes and the normal project Greenlight process approves it

## Benchmark and acceptance
Use the same representative pages for every experimental approach: a typical page, a two-column page, a page with tight spacing, a page with long/wrapped names, and a difficult/scanned page if present.
Measure:
- exact sequence recognition rate
- exact full-name recognition rate
- exact sequence-to-name pair accuracy
- missing / extra / duplicate / unresolved rows
- column and reading-order accuracy
- runtime and peak memory in the free GitHub runner

Required acceptance for automated approval: 100% exact records and pairs across the full document, zero unresolved rows, zero duplicates, zero omissions/extras, exact official count, and verified original layout order. Otherwise manual review; never publish.

## Implementation sequence
1. Inspect the actual authorized PRC PDF and document its text/image structure, page geometry, column patterns, and difficult regions without assuming a parser or OCR engine.
2. Define a small, auditable benchmark and independently reviewable ground-truth sample from the real document. Keep synthetic fixtures for unit tests only.
3. Research and prototype at least two strongest compliant approaches, including a custom/invented approach if evidence suggests it may work better. Keep all prototypes isolated and temporary.
4. Run identical real-page tests, compare exact record/pair accuracy, layout/order fidelity, unresolved cases, runtime, and memory. Inspect visual overlays and raw evidence.
5. Apply the proof gates. If none passes, do not adopt any technology and do not integrate an unproven extractor.
6. Only after a method passes, retain the minimal implementation and exact dependencies, then integrate it into the private PRC staging workflow. Do not modify main or CSC as part of this experiment.
