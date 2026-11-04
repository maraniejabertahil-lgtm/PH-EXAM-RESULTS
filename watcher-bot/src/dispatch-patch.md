# Watcher integration

The release-event builder is imported by `watcher-bot/src/index.js` and invoked only for a PRC article that is discovered from the approved PRC listing page.

- The Watcher fetches the article with the existing same-origin redirect and response-size guards.
- It extracts the article heading, visible text, and HTTPS links, then calls `buildReleaseEvent`.
- If exam code, year, LEPT level, or official content links are ambiguous, the Watcher logs a review reason and sends no ingestion dispatch.
- A valid event is sent as `repository_dispatch` type `prc-release-detected`.
- Non-PRC source-detection behavior remains unchanged.

This integration does not deploy the production Worker. Deployment is a separate, verified step after branch tests and merge.
