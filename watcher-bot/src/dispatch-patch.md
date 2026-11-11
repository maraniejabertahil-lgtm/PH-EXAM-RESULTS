# Watcher integration

The release-event builder is imported by `watcher-bot/src/index.js` and invoked only for a PRC article that is discovered from the approved PRC listing page.

- The Watcher fetches the article with the existing same-origin redirect and response-size guards.
- It extracts the article heading, visible text, and HTTPS links, then classifies supported attachments with `discoverArticleAttachments`.
- `buildReleaseEvents` identifies every main passer attachment for any PRC examination and creates an independent job per list. Elementary/Secondary labels are not tied to LEPT.
- Topnotchers, school-performance summaries, and full-text result documents are classified and logged, but only main passer lists are queued for extraction.
- Each accepted passer list becomes a separate `prc-release-detected` repository dispatch with one content URL, one result level, and one announced count. The dispatch idempotency key includes the result level and roster URL.
- A failed or unclear attachment does not stop other valid jobs. Unresolved attachments remain eligible for automatic retry; successful jobs are recognized as already dispatched. Duplicate same-level attachments are isolated rather than guessed.
- Each event is received and validated independently by the existing `process-import.yml` workflow and Python orchestrator. Exam-specific sources that remain disabled continue to block acquisition.
- Non-PRC source-detection behavior remains unchanged.

This integration does not deploy the production Worker. Deployment is a separate, verified step after branch tests and merge.
