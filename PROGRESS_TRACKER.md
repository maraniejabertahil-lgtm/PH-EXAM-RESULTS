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
- [x] Build Python `extractor/` using `pdfplumber` and `pandas` (raw text/table extraction; explicit mapping-based normalization is tracked separately; OCR is not implemented)
- [x] Implement Part 20 Official-First Policy (persist official-attempt evidence before fallback; block fallback on authentication/CAPTCHA; same-origin official PDF acquisition is integrated; external Drive links remain manual pending access verification)
- [x] Build `processor/` & Greenlight Protocol (100/0 fail-closed score; count, blanks, duplicates, anomalies, sequence coverage, and two-source fallback agreement)
- [x] Implement Array-of-Arrays JSON builder and sharding logic (each data shard strictly below 10 MiB; Greenlight fingerprint required)
- [x] Integrate the GitOps Manager with the processing workflow so a 100/100 Greenlight batch opens a PR and auto-merges only after all GitHub checks pass (reviewed-batch workflow and Python entry point merged in PRs #48 and #50; exact-commit CI dispatch and fail-closed merge; 90 Python tests passed; live result publication not yet run)
- [x] Add explicit, reviewed PDF table-to-record normalization and connect it to Greenlight (PR #51 merged; 98 Python tests passed; mapping-driven, preserves sequence strings, never guesses or renumbers; real official PDF layout validation remains pending)
- [x] Integrate bounded same-origin official PDF acquisition into the Python pipeline with robots.txt checks, article-link verification, PDF signature checks, and persisted HEAD/GET evidence (PR #52 merged; 104 Python tests passed; external Drive links remain manual-drop until public access policy is verified)
- [ ] Verify whether official PRC/CSC linked Google Drive PDFs are publicly downloadable without authentication; the inspected official PRC sample link displayed Google's sign-in page, so no automated download or bypass was attempted; retain manual-drop until public access is verified
- [ ] Validate at least one approved table mapping against a representative publicly accessible official PDF before enabling automated normalization for that source (no PDF fixture is present in the repository; requires a publicly accessible sample or owner-supplied manual-drop PDF)
- [ ] Run a real, publicly released result batch through acquisition, extraction, Greenlight, dataset generation, GitOps PR, CI, and merge

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
