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

## Candidate engines
1. **Primary: PyMuPDF**. Read word/span text and exact page coordinates from native PDF text. Preserve font, baseline, bounding boxes, and block structure.
2. **Independent layout/OCR: PaddleOCR PP-StructureV3**. Detect text regions, table/layout regions, and reading order on rendered pages. Use as a separate candidate, not as an authority over native PDF text.
3. **Independent OCR cross-check: Surya**. Compare detected words, names, sequence tokens, regions, and reading order on pages where native text is missing or suspicious.
4. **Fallback: Tesseract TSV/hOCR**. Use word-level coordinates and confidence; do not rely on flattened PSM 6 output for final pairing.
5. **Optional table candidate: Camelot**. Evaluate only if the PDF contains stable table rules or regular whitespace columns. It must not replace geometry-based extraction if its table structure is wrong.

All engines must be evaluated on identical representative pages before selecting the final combination. Use CPU/free open-source execution in GitHub Actions. Avoid paid APIs and external services.

## Pipeline

### A. Acquisition and immutable source evidence
- Resolve exactly one enabled, authorized PRC source by registry ID.
- Download only through the existing allow-listed HTTPS Drive path and exact file ID checks.
- Verify PDF signature, byte limit, page count, and SHA-256.
- Keep the source PDF unchanged for the duration of the run.
- Render pages at a fixed 300 DPI for visual/OCR evidence; render at 400 DPI only for flagged difficult regions.

### B. Layout and column segmentation
- First extract native PDF words/spans with coordinates; do not flatten the page to a text string.
- Detect page content bounds and exclude repeated headers/footers only when confirmed by page-position and repetition analysis. Keep excluded text in diagnostics.
- Segment physical columns using x-coordinate whitespace valleys / stable left-edge clusters, validated against rendered page previews. Do not use a single global x threshold as the final decision.
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
- For native-text pages, compare native tokens with PaddleOCR and/or Surya on the same rendered regions.
- For image-only pages, require at least two independent OCR readings for sequence and name, then compare normalized token text and geometry. Agreement is supporting evidence, not proof.
- Re-run flagged crops at higher DPI and with a second OCR configuration; retain original and revised outputs.
- Never autocorrect a name using a dictionary, internet lookup, expected sequence, or another person's record.
- Keep raw text exactly as extracted; normalized comparison fields are additional fields only.

### E. Canonical record schema
Each candidate record must contain:
- source_id, source_pdf_sha256
- page_number, physical_column_number, row_order_in_column
- printed_sequence_raw, printed_sequence_normalized (string; preserve leading zeroes)
- passer_name_raw, passer_name_normalized
- sequence_bbox, name_bbox, row_bbox (PDF-point coordinates)
- extraction_engine(s), OCR_confidence(s), native_text_available
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
Use the same representative pages for each candidate engine: a typical page, a two-column page, a page with tight spacing, a page with long/wrapped names, and a difficult/scanned page if present.
Measure:
- exact sequence recognition rate
- exact full-name recognition rate
- exact sequence-to-name pair accuracy
- missing / extra / duplicate / unresolved rows
- column and reading-order accuracy
- runtime and peak memory in the free GitHub runner

Required acceptance for automated approval: 100% exact records and pairs across the full document, zero unresolved rows, zero duplicates, zero omissions/extras, exact official count, and verified original layout order. Otherwise manual review; never publish.

## Implementation order
1. Add a Python geometry extractor using PyMuPDF and unit fixtures for row/column pairing.
2. Add word-level PaddleOCR as an independent layout/OCR candidate.
3. Add Surya only if PaddleOCR/native extraction leaves unresolved pages or the benchmark shows meaningful improvement.
4. Keep Tesseract TSV as fallback; test Camelot only on table-like pages.
5. Run the private benchmark, inspect the generated overlays, and tune thresholds using the real PRC PDF.
6. Integrate the validated Python engine into the existing private PRC staging workflow. Do not modify main or CSC as part of this experiment.
