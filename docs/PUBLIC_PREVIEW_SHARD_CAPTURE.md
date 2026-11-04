# Public Preview Shard Capture

## Purpose

The Python Engine now has a reusable capture component for large, publicly accessible, page-based result previews. It divides viewer pages into contiguous ranges, captures those ranges in parallel GitHub Actions jobs, then merges visible-text snapshots only after checking exact page coverage and SHA-256 hashes.

This is **page-capture sharding**. It is separate from the existing public-dataset sharding that splits generated JSON files to stay below the 10 MiB file-size limit.

## Proven baseline

The March 2026 LEPT Secondary trial (Actions run #36) used 16 parallel shards to capture 901 public-preview pages. Shards 0–14 captured 57 pages each and shard 15 captured 46 pages. All 16 completed; two shards succeeded after retrying stale viewer pages. The merge reported 901/901 pages.

The separate exam-specific extraction report recorded 45,001 unique sequence/name pairs and zero reported missing sequences, conflicts, duplicate sequences, out-of-range records, duplicate names, blank names, or unresolved target records. That is automated extraction evidence. It is not human visual-review approval and did not publish the dataset.

The reusable component passed live PRC public-preview capture on 2026-11-04. Final acceptance run [#41854972189](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/actions/runs/41854972189), using the exact official PRC article [March 2026 LEPT results](https://www.prc.gov.ph/index.php/article/march-2026-licensure-examination-professional-teachers-results-released-thirty-nine-39), completed all 16 shards, captured 901/901 pages, and passed exact-coverage and SHA-256 merge verification. Capture span was 61.228 seconds; shard loops ranged from 13.8 to 30.8 seconds. Three transient page-level retries occurred, with zero whole-shard restarts. The per-page stabilization deadline is configurable and defaults to 15 seconds. The final 10-test regression suite passed in [#41854448985](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/actions/runs/41854448985), including in-place retry of a stuck page and immediate access-challenge stop.

## Live acceptance and benchmark

The earlier exam-specific trial measured an approximately 77.45-second capture span for the same 901-page source and 16-shard layout. The final reusable-workflow run [#41854972189](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/actions/runs/41854972189) measured 61.228 seconds (about 21% faster by observed capture-span measurement). It used the exact official PRC LEPT Secondary article, a configurable 15-second per-page stabilization deadline, and three page-level retries; no whole-shard restart was required. Individual shard loops ranged from 13.8 to 30.8 seconds.

This is an observed benchmark, not a controlled statistical guarantee; GitHub runner scheduling and transient viewer latency vary. Earlier tuning runs showed the retry cost: run #41849915419 measured 162.334 seconds with five whole-shard retries; run #41851203320 measured 94.074 seconds with an experimental 250 ms delay on every successful page; run #41852967652 measured 140.876 seconds with a 35-second per-page deadline and six in-place page retries; run #41853845747 measured 66.042 seconds with a 15-second deadline and five in-place retries. The final run reduced the observed span to 61.228 seconds with three in-place retries while retaining exact coverage.

The live test captured viewer text only. It did not parse passer records, run Greenlight, or publish a dataset. The source remains subject to the existing DRAFT-watermark caveat and pending human review. The generic capture manifest is not yet the Python Engine record-ingestion manifest: a separate bridge is still required to convert the page snapshots into the hash-bound JSONL/provenance/extraction evidence expected by `load_public_preview_capture()`.

## Reuse

Call .github/workflows/reusable-public-preview-shards.yml from an exam-specific workflow. Supply:

- preview_url: ordinary public preview URL linked from the official source;
- allowed_hosts: exact hostnames allowed for the initial URL and redirects;
- shard_count: 1–16, selected according to source rules, capacity, and observed stability;
- optional viewer selectors/markers if the public viewer uses a different visible page control.

Example caller job:

~~~yaml
jobs:
  capture:
    uses: ./.github/workflows/reusable-public-preview-shards.yml
    with:
      preview_url: https://drive.google.com/file/d/REPLACE_WITH_OFFICIAL_FILE_ID/preview
      allowed_hosts: drive.google.com,docs.google.com
      shard_count: 16
~~~

Replace the example URL and host list with values verified from the specific official announcement. Do not run this workflow against a source unless public access and automation are authorized and consistent with robots.txt, published terms, and rate limits.

## Safety and operating limits

- HTTPS only; redirects must remain within the explicitly allowed host list.
- Maximum 16 shards and 2,000 viewer pages per run.
- Shard starts are staggered by two seconds; each shard retries up to three times with increasing waits. A page that does not stabilize is retried in place up to three times using a configurable per-page deadline (15 seconds by default) before the workflow restarts a shard.
- The capture reads the ordinary visible preview UI only. It does not download the PDF, call private endpoints, use OCR, or attempt to defeat access controls.
- Authentication, CAPTCHA, human-verification, permission, or access-denied screens stop the run immediately. The workflow does not retry an access challenge; use only an authorized manual handoff.
- Lower the shard count when source policy, capacity, or observed stability requires it. Sixteen is a proven baseline for the tested public preview, not a universal safe setting for every source.
- Merge fails closed on missing artifacts, inconsistent page counts, gaps, overlaps, page-order errors, blank snapshots, or SHA-256 mismatches.
- Successful page capture is not proof that names are accurate. Exam-specific parsing, sequence/name validation, Greenlight, and any required owner review remain separate gates.
- The reusable workflow creates capture evidence only. It does not create a GitOps PR, merge data, publish results, or change the current review state.

## Human review and publication

The Owner deferred manual visual review of the March 2026 LEPT Secondary candidate to a future website review experience. The candidate remains unpublished. Automated capture and Greenlight do not certify human visual review or grant publication approval.
