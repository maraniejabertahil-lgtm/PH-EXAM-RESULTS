MASTER TECHNICAL BLUEPRINT

PH-EXAM-RESULTS
Python-First, Free-Only, High-Concurrency Architecture

Document purpose: Final approved architecture blueprint for the PH-EXAM-RESULTS platform, incorporating the Split Watcher/Worker Architecture and Greenlight Protocol.

⸻

PART 1 — PROJECT OBJECTIVES AND NON-NEGOTIABLE RULES

1.1 Main Objective

Build a reliable, automated examination results platform for the Philippine Regulatory Commission (PRC) and Civil Service Commission (CSC).

The platform must:

1. Monitor and attempt authorized official examination-result sources first. Use verified third-party websites only as a fallback after compliant official retrieval has been confirmed unavailable.
2. Acquire the official result CONTENTS in any compliant, publicly accessible format. The required information is each passer's name paired with the official sequence number. Downloading or storing a PDF is optional and is never a goal by itself.
3. Process and extract examination information using Python.
4. Validate extracted information before publication.
5. Detect duplicates and prevent incorrect records.
6. Maintain examination monitoring and historical release information.
7. Prepare and publish verified examination results.
8. Allow visitors to search by authority, examination, year, and name.
9. Support 30,000–59,000 simultaneous visitors through a static-first architecture.
10. Provide an owner control system (via GitOps) for monitoring automation and controlling publication.
11. Preserve previous working results if processing or publication fails.

1.2 Non-Negotiable Architecture Rules

• Use free services only. Do not introduce a paid subscription, server, API, database, or automation platform.
• Python must be the primary processing language.
• CONTENT-FIRST RULE: The system needs passer names and their corresponding official sequence numbers, not PDF files. Use the most reliable compliant official content source and format available. Do not block progress merely because a linked PDF cannot be downloaded. PDF parsing remains an optional acquisition method when it is the authorized practical route.
• Do not require a Cloudflare Worker or backend server for public searching.
• Do not expose database credentials, API tokens, or private records to the browser.
• Do not publish unverified examination results.
• Preserve the locked public page designs (Searching and Preparing pages).
• Every important process must have logging, validation, error handling, and recovery procedures.

⸻

PART 2 — TECHNOLOGY STACK AND RESPONSIBILITIES

|Technology                  |Primary Responsibility                                                                                      |
|:---------------------------|:-----------------------------------------------------------------------------------------------------------|
|**Cloudflare Workers (JS)** |“The Watcher”: 24/7 high-speed 30-second monitoring and preemptive URL guessing (Uses 0 GitHub minutes).    |
|**Python**                  |Main automation, processing, extraction (PDF/CSV), validation, and dataset generation.                      |
|**GitHub Actions**          |“The Worker”: Triggered by the Watcher via Webhook. Executes heavy Python extraction and deployments.       |
|**GitHub (GitOps)**         |Source-code management, Pull Request-based approval workflow, version history.                              |
|**Cloudflare Pages**        |Public website hosting, static asset delivery, and JSON dataset distribution.                               |
|**Cloudflare D1 / KV**      |Internal operational database (metadata, batch statuses) accessed via REST API. KV used for Peak Week flags.|
|**HTML/CSS**                |Website structure, visual design, and responsive layouts.                                                   |
|**JavaScript (Web Workers)**|Browser-side search, filtering, IndexedDB caching, and UI state management.                                 |
|**JSON**                    |Highly optimized, array-of-arrays public search-data format.                                                |

⸻

PART 3 — COMPLETE SYSTEM ARCHITECTURE

[ OFFICIAL PRC/CSC SOURCES FIRST ]
           ↓ (only after documented official retrieval failure)
[ VERIFIED THIRD-PARTY SOURCES / MIRRORS ]
           ↓
[ CLOUDFLARE WORKER (The Watcher) ] ── Runs 1-min cron (30-sec loop in Peak Week)
           ↓ (If new PDF / 200 OK detected)
[ WEBHOOK (repository_dispatch) ]
           ↓
[ GITHUB ACTIONS (The Worker) ] ── Wakes up Python Engine
           ↓
[ PYTHON ENGINE ] 
 ├─ 1. Acquire: Obtain official result contents from a compliant public source (page, portal data, embedded dataset, CSV, or PDF); downloading a PDF is optional.
 ├─ 2. Extract: Parses data (pdfplumber/pandas).
 ├─ 3. Validate (Greenlight Protocol): Calculates Confidence Score.
 ├─ 4. Store Metadata: Writes run status to CF D1 (via REST API).
 └─ 5. Propose: Generates JSON datasets and opens a GitHub Pull Request.
           ↓
[ PUBLICATION LOGIC ]
 ├─ IF Score == 100%: Python AUTO-MERGES the PR. 
 └─ IF Score < 100%: Aborts auto-merge. Sends alert to Owner for manual PR review.
           ↓
[ CLOUDFLARE PAGES (Edge Network) ]
 ├─ Hosts HTML, JS, CSS, and static JSON datasets globally.
 └─ Python automatically blasts Facebook/Telegram API: "Results are Live!"
           ↓
[ VISITOR BROWSER ]
 └─ Downloads UI -> Fetches specific JSON -> JS Web Worker searches locally.

⸻

PART 4 — PYTHON ENGINE: INTERNAL MODULE ARCHITECTURE

python-engine/
│
├── requirements.txt
├── main.py                 # CLI entry point (process, publish)
│
├── extractor/              # File parsing and data extraction
│   ├── pdf_parser.py       # High-accuracy PDF extraction (e.g., pdfplumber)
│   └── text_cleaner.py     # OCR fallback and text sanitization
│
├── processor/              # Data normalization and validation
│   ├── normalizer.py       # Name, date, and exam standardization
│   ├── duplicates.py       # Fuzzy and exact duplicate detection
│   └── validator.py        # GREENLIGHT PROTOCOL: Confidence Scoring
│
├── database/               # State management and history
│   └── d1_client.py        # Cloudflare D1 REST API client
│
└── publisher/              # Dataset generation for deployment
    ├── json_builder.py     # Compiles array-of-arrays JSON chunks
    ├── manifest.py         # Generates manifest.json with hashes
    ├── broadcaster.py      # Triggers Facebook/Telegram API updates
    └── gitops_manager.py   # Handles PR creation and Auto-Merge logic

⸻

PART 5 — AUTOMATION AND GITOPS APPROVAL WORKFLOW

5.1 The Greenlight Protocol (Conditional Auto-Publish)

To beat competitors, Python must grade its own extraction. During the processor/validator.py step, Python calculates a Confidence Score. To score 100%, the batch MUST meet ALL the following criteria:

1. Count Match: Total extracted names perfectly match the announced number of passers.
2. Zero Blanks: No records have empty name fields.
3. Zero Duplicates: No exact duplicate names or sequence numbers.
4. Zero Anomalies: No unexpected alien characters or unparseable symbols.

5.2 The GitOps Approval Flow

1. Python successfully parses a new batch of results.
2. Python commits the JSON datasets to a new branch and opens a Pull Request.
3. IF Score == 100%: Python uses the GITHUB_TOKEN to automatically merge the Pull Request it just created. Cloudflare Pages begins deployment instantly. (Zero human intervention).
4. IF Score < 100%: Auto-merge is aborted. The PR remains open. The system sends an urgent alert (via Telegram/Email) to the Owner stating: “Extraction Confidence [X]%. Manual PR Review Required.”

⸻

PART 6 — INTERNAL DATABASE DESIGN (CLOUDFLARE D1 & KV)

• Cloudflare KV: Stores a simple boolean { "PEAK_WEEK": true } so the Cloudflare Worker can check its mode in 1 millisecond.
• Cloudflare D1: monitoring_logs, import_batches, and release_predictions.
• D1 is strictly accessed via Cloudflare REST API. No direct SQL drivers inside GitHub Actions. No database queries from the public frontend.

⸻

PART 7 — PUBLIC DATASET AND SEARCH ARCHITECTURE

7.1 Array-of-Arrays JSON Format

Datasets will use an Array of Arrays format to drastically reduce file sizes.

{
  "columns": ["name", "rating", "region", "seq"],
  "data": [
    ["DELA CRUZ, JUAN A", 85.5, "NCR", 145],
    ["SANTOS, MARIA B", 88.0, "REGION III", 146]
  ]
}

7.2 Dataset Sharding & Manifest

• Datasets are split by Authority → Exam → Year.
• If a JSON file exceeds 10MB (e.g., PRC LET), Python shards it alphabetically (2026-A-M.json, 2026-N-Z.json).
• manifest.json acts as the router, providing cache-busting hashes to the frontend.

⸻

PART 8 — HIGH-CONCURRENCY DESIGN

Target: 30,000–59,000 simultaneous visitors.

1. Zero Backend Queries: The search bar does not send HTTP requests.
2. IndexedDB Caching: Downloaded JSON datasets are stored in the browser’s IndexedDB. Subsequent searches load instantly from local storage.
3. Web Worker Offloading: Searching an array of 50,000+ strings runs inside a JavaScript Web Worker (search.js), ensuring the phone’s UI does not freeze.

⸻

PART 9 — PREPARING PAGE & PREEMPTIVE STRIKE (PEAK WEEK)

9.1 Peak Week Mode Logic

• Activation: Starts exactly 7 days before the D1 historically predicted release date (or manually triggered by the Owner).
• Deactivation: Ends 2 days after the results are actually published. Rule: Peak Week only stops if the results really arrive and are caught.
• UI Change: The website reads a generated status.json and changes the UI to the “Preparing Mode” screen (navy/teal palette).

9.2 The Preemptive Strike

During Peak Week, the Cloudflare Worker does not just watch the official homepage. It actively guesses future PDF URLs using lightweight HEAD requests (e.g., csc.gov.ph/CSE_082026_passers.pdf). If it gets a 200 OK before the official announcement, it triggers the extraction immediately.

⸻

PART 10 — OWNER CONTROL CENTER

• Approvals: Messy data falls back to GitHub Pull Requests. Owner reviews the Validation Report in the PR description and clicks “Merge”.
• Overrides (Manual Drop): If the scraper is completely blocked, the Owner can manually drag and drop a PDF into the /manual-drop/ folder in GitHub. This instantly triggers the extraction workflow.

⸻

PART 11 — WATCHER & WORKER AUTOMATION DESIGN

We abandon GitHub Actions for monitoring. It is replaced by Cloudflare Workers.

11.1 The Watcher (Cloudflare Worker)

• Trigger: 1-minute cron (* * * * *).
• Standard Mode: Fetches the site once, terminates.
• Peak Week Mode: Fetches the site & guesses preemptive URLs. Waits 30 seconds (await new Promise(r => setTimeout(r, 30000))). Fetches again.
• Webhook: Upon detecting a change or a 200 OK, it sends a repository_dispatch webhook to GitHub containing the direct PDF URL.

11.2 The Worker (GitHub Actions)

• .github/workflows/process-import.yml: Triggered by repository_dispatch (from Worker) or push (to /manual-drop/).
• .github/workflows/deploy-pages.yml: Triggered by PR merge to main. Deploys the site.

⸻

PART 12 — PUBLICATION AND RECOVERY SAFETY

• Safe Deployment: Merging the PR (whether Auto or Manual) ensures only validated JSON enters the main branch.
• Rollback: If a published dataset contains errors, the Owner clicks “Revert” on the problematic Merge Commit in GitHub. Cloudflare Pages automatically redeploys the previous working state within 3 minutes.

⸻

PART 13 — SECURITY REQUIREMENTS

1. No Frontend Secrets: API keys and internal database IDs must NEVER exist in public code.
2. Cloudflare Worker Secrets: The GitHub PAT used by the Worker to fire the webhook must be stored securely using wrangler secret.
3. GitHub Secrets: All credentials (CF_API_TOKEN) are stored in GitHub Actions Secrets.
4. Read-Only Public Site: The Cloudflare Pages site has zero mechanism to write data.

⸻

PART 14 — FREE SERVICE LIMITS AND ARCHITECTURAL CONSEQUENCES

|Service               |Free Limit      |Architectural Protection                                                        |
|:---------------------|:---------------|:-------------------------------------------------------------------------------|
|**Cloudflare Workers**|100,000 reqs/day|1-min cron doing 2 checks = 2,880 requests/day. Safely uses < 3% of free tier.  |
|**Cloudflare Pages**  |500 builds/mo.  |Batch processing via PRs keeps usage well below 500.                            |
|**GitHub Actions**    |2,000 mins/mo.  |Removed monitoring duty from GitHub. Used strictly for fast data extraction.    |
|**Cloudflare D1**     |500 MB storage. |Passer datasets stored as JSON in repo/Pages; D1 strictly reserved for metadata.|

⸻

PART 15 — FINAL REPOSITORY STRUCTURE

PH-EXAM-RESULTS/
│
├── public/                 # Cloudflare Pages Root
│   ├── index.html          
│   ├── preparing.html      
│   ├── _headers            
│   ├── assets/js/
│   │   ├── search.js       # JS Web Worker (UI Thread Protection)
│   │   ├── storage.js      # IndexedDB management
│   │   └── loader.js       
│   └── data/               # Static JSON Output
│
├── watcher-bot/            # The Cloudflare Worker (JS)
│   ├── src/index.js        # 30-sec loop, Preemptive strike, Webhook logic
│   └── wrangler.toml       # CF config and 1-min cron trigger
│
├── python-engine/          # The Python App Structure (From Part 4)
│   ├── requirements.txt
│   ├── extractor/
│   ├── processor/
│   └── publisher/
│
├── manual-drop/            # Manual override folder for dragged-and-dropped PDFs
│
├── .github/workflows/      
│   ├── process-import.yml  
│   └── deploy-pages.yml    
│
└── docs/

⸻

PART 16 — IMPLEMENTATION ROADMAP

1. Phase 1: The Watcher - Build watcher-bot/. Test the 30-sec loop, Peak Week KV check, Preemptive HEAD requests, and Webhook dispatch to GitHub.
2. Phase 2: The Extractor & Greenlight - Build Python logic. Must successfully grade messy vs clean PDFs. Build the GitOps PR creation and Auto-Merge logic.
3. Phase 3: Automated Broadcasting - Connect Python to Facebook Graph API and Telegram Bot API.
4. Phase 4: Frontend Web Worker Search - Build UI, IndexedDB caching, and Web Worker search processing Array-of-Arrays JSON.
5. Phase 5: End-to-End Simulation - Drop a dummy PDF on a target URL. Verify Worker detects it in <30s, wakes Python, auto-grades 100%, auto-merges, broadcasts, and deploys.

### Implementation status recorded from PROGRESS_TRACKER.md — 2026-11-03

This is an execution-status snapshot, not a change to the roadmap or its acceptance requirements.

- **Phase 1 — Watcher:** All six Phase 1 implementation items are checked in PROGRESS_TRACKER.md. The Owner confirms personally testing the completed Phase 1 work. The tracker still distinguishes implementation tests from genuine production acceptance: genuine PRC result-release detection/dispatch acceptance remains to be revisited when an official release is available, and production preemptive URL templates remain unverified.
- **Phase 2 — Extractor & Greenlight:** The tracker records the Python extractor, fail-closed Greenlight checks, Array-of-Arrays builder/sharding, GitOps integration, reviewed PDF normalization, and bounded same-origin PDF acquisition as implemented. PR #55 adds the missing-sequence publication-abort regression test; its merged main-branch CI run passed with 112 Python tests. Official-content access validation, representative official-content mapping validation, and a real released-result batch remain open.
- **Phases 3–5:** Remain unchecked in the progress tracker and are not represented as implemented or accepted here.

The live PROGRESS_TRACKER.md remains the operational source of truth for task completion. This snapshot must be reconciled when that tracker changes.

⸻

PART 17 — REQUIRED TESTING AND ACCEPTANCE CRITERIA

• Extraction Safety: The Greenlight Protocol MUST fail on a test PDF missing sequence numbers. Auto-publish must abort.
• Performance: 50,000-record dataset searchable in browser without dropping UI frames.
• Preemptive Test: Worker successfully identifies a PDF via HEAD request before the HTML page updates.

### Recorded test status — 2026-11-03

- **Extraction Safety:** Automated regression test added in PR #55 and merged to main. It supplies a simulated extracted-PDF-table fixture with a missing sequence (002), invokes the publication pipeline, and verifies Greenlight fails, GitOps is not initialized, no dataset manifest is produced, and the missing sequence is reported. Main-branch CI passed with 112 Python tests. **Status: PASS for the automated extracted-table safety test.** A real official PDF/layout validation remains separate and pending.
- **Performance:** No 50,000-record browser/Web Worker performance evidence is recorded yet. **Status: NOT RUN.**
- **Preemptive Test:** Phase 1 implementation work is checked in the progress tracker and the Owner confirms personally testing the Phase 1 work. However, the tracker and Phase 1 audit do not record a genuine result-resource HEAD success occurring before the official HTML announcement changed. **Status: implementation/owner-tested; formal Part 17 acceptance remains pending live evidence.**

These statuses report the evidence currently recorded in the progress tracker, merged test, and Phase 1 audit. They do not waive any Part 17 pass condition or convert an implementation checkbox into live acceptance.

⸻

PART 18 — RISKS AND HONEST LIMITATIONS

1. File Type Variations: If PRC switches from PDF to embedded images, the Watcher will catch it, but Python extraction will fail the Greenlight check. Manual review required.
2. Anti-Scraping Captchas: If the government puts the PDF behind a Cloudflare Turnstile CAPTCHA, the Worker cannot bypass it. The Owner must use the /manual-drop/ folder.

⸻

PART 19 — GOVERNING PRINCIPLES

1. Python does the heavy lifting; the Browser does the searching.
2. The Worker watches; GitHub processes.
3. Zero human intervention for clean data (Greenlight Protocol); strictly manual intervention for messy data.
4. No servers, no live database queries on the public route. Strictly $0.


⸻

PART 20 — OFFICIAL-FIRST SOURCE ACQUISITION POLICY (MANDATORY)

20.1 Source order

1. The system MUST attempt the official PRC or CSC result announcement/source first for every release.
2. It MUST identify and attempt to retrieve the result document or dataset linked by that official source.
3. The official attempt must use only legitimate, authorized, low-impact retrieval. Use bounded retries and normal HTTP methods; respect robots.txt, rate limits, redirects, and access controls.
4. A first failed request is not sufficient evidence that the official source is impossible to retrieve. Retry appropriate, compliant retrieval methods and verify the returned content.
5. The system MUST verify that a supposed PDF is actually a PDF (including response content type/signature where available), not an HTML login/interstitial page, error response, or unrelated file.
6. Only after the official source/document is confirmed unavailable through compliant attempts may the system enter third-party fallback.

20.2 Official failure evidence

Before fallback, retain a machine-readable official-attempt record containing:
- official source URL and, when different, official result-article/document URL;
- timestamp(s) and compliant retrieval method(s) attempted;
- HTTP status, content type, final URL, and PDF/signature verification outcome where available;
- concise failure classification and reason;
- whether access was blocked by robots policy, authentication, CAPTCHA/human verification, server response, missing document, or invalid/non-PDF content.

Do not store credentials, session cookies, private information, or unnecessary personal data in this evidence.

20.3 Third-party fallback requirements

When and only when the official-first gate passes:
- Use two independent, publicly accessible, owner-approved/verified third-party transcription sources.
- Extract and compare each sequence-number/name pair exactly. Do not compare names alone and do not silently renumber records.
- Require 100% exact pair agreement between both sources.
- Require total record count to equal the official authority's announced passer count.
- Require complete sequence coverage and zero gaps, extras, duplicates, blank names, or unresolved parsing anomalies.
- If any requirement fails, stop. Do not create a publication-ready dataset and do not auto-publish.

20.4 Provenance and website behavior

Every import and published dataset must carry an explicit provenance value:
- `official_direct`: names/data were extracted directly from the officially released document or dataset.
- `third_party_fallback`: official retrieval was confirmed unavailable and records were transcribed from the two independent verified sources.

The website, owner review report, logs, and any public source attribution must preserve this distinction. Never label a third-party transcription as an official PDF extraction. When provenance is fallback, retain the official failure evidence and both third-party source references with the validation report.

20.5 Safety and publication

- Never bypass sign-in, CAPTCHA, MFA, permissions, robots.txt, or other access restrictions.
- If human verification is required, stop automated retrieval and use only the authorized manual-drop/review route; do not attempt circumvention.
- A fallback batch that does not achieve every validation requirement remains unpublished.
- Preserve the last known-good public dataset whenever acquisition, extraction, comparison, or validation fails.

This policy governs PRC and CSC. It does not authorize processing an examination or authority outside the requested/approved task scope.


⸻

PART 21 — CONTENT-FIRST RESULT ACQUISITION (OWNER RULE)

21.1 Required output, not required file type

The system's objective is to obtain and publish accurate passer records, specifically:
- passer name; and
- the corresponding official sequence number.

A PDF file is NOT a required deliverable. Do not spend time trying to download, store, or validate a PDF merely for the sake of possessing the file. If the official result contents are available through a compliant public webpage, portal response, embedded/public dataset, CSV, or another readable official format, acquire and process those contents directly.

21.2 Preferred acquisition behavior

1. Check the official PRC/CSC announcement and its linked result destination.
2. Determine where the actual passer names and sequence numbers are exposed.
3. Use the simplest reliable, low-impact, authorized method to read those contents.
4. Preserve the exact name–sequence pair. Do not invent, infer, or renumber sequence values.
5. Validate announced totals, sequence coverage, blanks, duplicates, and anomalies before publication.
6. Use PDF download/parsing only when it is a practical and compliant way to obtain the required contents—not as a mandatory gate.

21.3 Access and provenance safeguards

This rule does not authorize bypassing login, CAPTCHA, MFA, permissions, robots.txt, rate limits, or other access restrictions. If a portal requires authentication or human verification that the system is not authorized to use, stop automated access and use an owner-authorized manual content handoff/review path. Record the source, access method, timestamp, and provenance. Continue to apply the official-first and third-party fallback requirements in Part 20.

21.4 Tracker interpretation

Any task phrased as “verify whether an official PDF is downloadable” must be interpreted as superseded by this content-first rule. The active task is to identify and validate a compliant way to obtain the official passer names and sequence numbers. PDF downloadability is not a project acceptance criterion.
