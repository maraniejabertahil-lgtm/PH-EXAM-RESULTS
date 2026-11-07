# Private Owner Dashboard

This folder is deployed as a **separate Cloudflare Pages project**. Never add it to the public search site's Pages project.

## One-time Cloudflare setup

1. From the Codespaces terminal, run:
   ```bash
   npx wrangler@4.156.2 login
   npx wrangler@4.156.2 pages project create ph-exam-results-owner --production-branch main
   ```
2. In the new Pages project, open **Settings → General → Enable access policy**. Open the generated application under Zero Trust → Access → Applications → Configure. Remove the wildcard subdomain and select the exact `ph-exam-results-owner.pages.dev` production hostname. Its Allow policy must contain only the Owner's exact email. Re-enable the Pages access policy if preview deployments are also used.
3. In the new Pages project's production Variables and Secrets, configure:
   - `CF_ACCESS_TEAM_DOMAIN`
   - `CF_ACCESS_AUD`
   - `OWNER_EMAIL` (exact Owner email)
   - `CF_ACCOUNT_ID`
   - `CF_D1_DATABASE_ID`
   - `CF_D1_READ_API_TOKEN` (separate D1 Read token)
4. Create the D1 database and configure the D1 Write token for trusted writers. Do not store examinee names, result rows, or raw search queries in operational logs.
5. Add GitHub Actions secrets:
   - `CF_ACCOUNT_ID`
   - `CF_D1_DATABASE_ID`
   - `CF_D1_API_TOKEN` (D1 Edit token)
   - `CF_PAGES_API_TOKEN` (Cloudflare Pages Edit token)
   - `CF_OWNER_PAGES_PROJECT_NAME` = `ph-exam-results-owner`
6. Set the repository variable `CF_OWNER_DASHBOARD_ENABLED=true` only after the Access application and private Pages project are ready.
7. Configure the production Watcher Worker with `CF_ACCOUNT_ID`, `CF_D1_DATABASE_ID`, and secret `CF_D1_API_TOKEN`.

Then run **Actions → Migrate Private Activity Monitor D1 → Run workflow** on `main`, followed by **Actions → Deploy Private Owner Dashboard → Run workflow**.

## Routes

- `/` — private Owner activity timeline
- `/api/activity` — Access-JWT-verified D1 activity API

The entire Pages project is protected by Cloudflare Access. The public PH Exam Results Pages project remains public and unchanged.
