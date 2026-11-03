# Project Progress & Phase Tracker

> **Active Phase:** Phase 1  
> **Status:** Initializing  

---

## Phase 1: The Watcher (Cloudflare Worker)
- [ ] Initialize `watcher-bot/` directory and `wrangler.toml` config
- [ ] Implement standard 1-minute cron check against official PRC/CSC sources
- [ ] Implement Peak Week Mode (Cloudflare KV check, 30-sec loop)
- [ ] Add Preemptive Strike logic (HEAD requests predicting PDF URLs)
- [ ] Configure `repository_dispatch` Webhook to wake GitHub Actions

## Phase 2: The Extractor & Greenlight (Python & GitOps)
- [ ] Build Python `extractor/` using `pdfplumber` and `pandas`
- [ ] Implement Part 20 Official-First Policy (Log failures before 3rd-party fallback)
- [ ] Build `processor/` & Greenlight Protocol (Score 100% = Count match, 0 blanks, 0 dupes, 0 anomalies)
- [ ] Implement Array-of-Arrays JSON builder and sharding logic (files < 10MB)
- [ ] Set up GitOps Manager to open PRs and Auto-Merge if Score == 100%

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
