# Project Progress & Phase Tracker

> **Active Phase:** Phase 2  
> **Status:** In Progress  

---

## Phase 1: The Watcher (Cloudflare Worker)
- [x] Initialize `watcher-bot/` directory and `wrangler.toml` config
- [x] Implement standard 1-minute cron check against approved official PRC/CSC sources (PRC monitored; CSC safely paused pending compliant access)
- [x] Implement Peak Week Mode (Cloudflare KV check, 30-sec loop)
- [x] Add Preemptive Strike logic (template-based HEAD requests; production URL templates remain empty until officially verified)
- [x] Configure `repository_dispatch` Webhook to wake GitHub Actions (receiver validation workflow configured; genuine production dispatch acceptance still pending)
- [x] Owner-approved phase transition: defer genuine PRC production acceptance until the official result release is available; live production acceptance remains unverified and must be revisited when available.

## Phase 2: The Extractor & Greenlight (Python & GitOps)
- [x] Build Python `extractor/` using `pdfplumber` and `pandas` (local raw extraction only; no OCR, normalization, Greenlight, or publication)
- [x] Implement Part 20 Official-First Policy (persist official-attempt evidence before fallback; block fallback on authentication/CAPTCHA; production acquisition integration remains pending)
- [x] Build `processor/` & Greenlight Protocol (100/0 fail-closed score; count, blanks, duplicates, anomalies, sequence coverage, and two-source fallback agreement)
- [x] Implement Array-of-Arrays JSON builder and sharding logic (each data shard strictly below 10 MiB; Greenlight fingerprint required)
- [ ] Integrate the GitOps Manager with the processing workflow so a 100/100 Greenlight batch opens a PR and auto-merges only after all GitHub checks pass (core manager and unit tests merged in PR #47; workflow invocation and end-to-end verification remain pending)

## Phase 3: Automated Broadcasting
- [ ] Build `broadcaster.py` inside Python Engine
- [ ] Connect and test Facebook Graph API integration
- [ ] Connect and test Telegram Bot API integration
- [ ] Ensure broadcasts only fire after successful PR merge/deployment

## Phase 4: Frontend Web Worker Search
- [ ] Build static HTML/CSS UI (including Peak Week "Preparing Mode" UI)
- [ ] Implement `storage.js` for IndexedDB dataset caching
- [ ] Implement `search.js` (Web Worker) to search 50,000+ array records without freezing UI
- [ ] Configure Cloudflare Pages deployment via `.github/workflows/deploy-pages.yml`

## Phase 5: End-to-End Simulation & Security
- [ ] Run Dummy Test: Drop PDF, verify Watcher detects in <30s and wakes Worker
- [ ] Run Safety Test: Feed a broken PDF (missing sequence numbers) to verify Greenlight Protocol aborts auto-merge
- [ ] Verify no secrets are exposed in public code or frontend
- [ ] Test the `/manual-drop/` GitHub override workflow
