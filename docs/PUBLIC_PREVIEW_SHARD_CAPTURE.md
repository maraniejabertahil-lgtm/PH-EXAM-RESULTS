# Public Preview Shard Capture

## Purpose

The Python Engine now has a reusable capture component for large, publicly accessible, page-based result previews. It divides viewer pages into contiguous ranges, captures those ranges in parallel GitHub Actions jobs, then merges visible-text snapshots only after checking exact page coverage and SHA-256 hashes.

This is **page-capture sharding**. It is separate from the existing public-dataset sharding that splits generated JSON files to stay below the 10 MiB file-size limit.

## Proven baseline

The March 2026 LEPT Secondary trial (Actions run #36) used 16 parallel shards to capture 901 public-preview pages. Shards 0–14 captured 57 pages each and shard 15 captured 46 pages. All 16 completed; two shards succeeded after retrying stale viewer pages. The merge reported 901/901 pages.

The separate exam-specific extraction report recorded 45,001 unique sequence/name pairs and zero reported missing sequences, conflicts, duplicate sequences, out-of-range records, duplicate names, blank names, or unresolved target records. That is automated extraction evidence. It is not human visual-review approval and did not publish the dataset.

The reusable component has now passed a live PRC public-preview capture on 2026-11-04. Actions run [#41851646784](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/actions/runs/41851646784) completed all 16 shards, captured 901/901 pages, and passed exact-coverage and SHA-256 merge verification. The measured capture span was 64.427 seconds; individual shard loops ranged from 19.2 to 29.2 seconds. No whole-shard or page-level retry was needed in this final run. Regression run [#41851789181](https://github.com/maraniejabertahil-lgtm/PH-EXAM-RESULTS/actions/runs/41851789181) passed the 9-test suite before the additional explicit challenge-stop test was added. The final code also adds page-level retries so a stale viewer page is retried in place rather than restarting the entire shard.

## Live acceptance and benchmark\n\nThe earlier exam-specific trial's measured capture span was approximately 77.45 seconds for the same 901-page source and 16-shard layout. The final reusable-workflow run measured 64.427 seconds (about 17% faster by observed capture-span measurement). This is a single-run comparison, not a controlled statistical benchmark; GitHub runner scheduling and transient viewer latency vary between runs. Two earlier reusable-workflow trials exposed retry overhead: run #41849915419 measured 162.334 seconds with five whole-shard retries; run #41851203320 measured 94.074 seconds with one in-place page retry but included an experimental 250 ms delay on every successful page. That unnecessary per-page delay was removed before the final run.\n\nThe live test captured viewer text only. It did not parse passer records, run Greenlight, or publish a dataset. The source remains subject to the existing DRAFT-watermark caveat and pending human review. The generic capture manifest is not yet the Python Engine record-ingestion manifest: a separate bridge is still required to convert the page snapshots into the hash-bound JSONL/provenance/extraction evidence expected by `load_public_preview_capture()`.\n\n## Reuse

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
- Shard starts are staggered by two seconds; each shard retries up to three times with increasing waits. A page that does not stabilize is retried in place up to three times before the workflow restarts a shard.
- The capture reads the ordinary visible preview UI only. It does not download the PDF, call private endpoints, use OCR, or attempt to defeat access controls.
- Authentication, CAPTCHA, human-verification, permission, or access-denied screens stop the run immediately. The workflow does not retry an access challenge; use only an authorized manual handoff.
- Lower the shard count when source policy, capacity, or observed stability requires it. Sixteen is a proven baseline for the tested public preview, not a universal safe setting for every source.
- Merge fails closed on missing artifacts, inconsistent page counts, gaps, overlaps, page-order errors, blank snapshots, or SHA-256 mismatches.
- Successful page capture is not proof that names are accurate. Exam-specific parsing, sequence/name validation, Greenlight, and any required owner review remain separate gates.
- The reusable workflow creates capture evidence only. It does not create a GitOps PR, merge data, publish results, or change the current review state.

## Human review and publication

The Owner deferred manual visual review of the March 2026 LEPT Secondary candidate to a future website review experience. The candidate remains unpublished. Automated capture and Greenlight do not certify human visual review or grant publication approval.
