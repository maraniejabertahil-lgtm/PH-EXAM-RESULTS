# Watcher integration

The release-event builder is imported by `watcher-bot/src/index.js` and invoked only for a PRC article that is discovered from the approved PRC listing page.

- The Watcher fetches the article with the existing same-origin redirect and response-size guards.
- It extracts the article heading, visible text, and HTTPS links, then classifies supported attachments with `discoverArticleAttachments`.
- `buildReleaseEvents` pre-validates every target passer list. For multi-list LEPT articles, each list must have one unique supported level label and a matching level-specific announced count.
- Topnotchers, school-performance summaries, and full-text result documents are classified and logged, but only main passer lists are queued for extraction.
- Each accepted passer list becomes a separate `prc-release-detected` repository dispatch with one content URL, one result level, and one announced count. The dispatch idempotency key includes the result level and roster URL.
- A failed list dispatch does not undo a successful sibling dispatch. The failed list remains eligible for retry; successful lists are recognized as already dispatched. Ambiguous or duplicate categories stop the whole article before any list is dispatched.
- Each event is received and validated independently by the existing `process-import.yml` workflow and Python orchestrator. Exam-specific sources that remain disabled continue to block acquisition.
- Non-PRC source-detection behavior remains unchanged.

This integration does not deploy the production Worker. Deployment is a separate, verified step after branch tests and merge.
