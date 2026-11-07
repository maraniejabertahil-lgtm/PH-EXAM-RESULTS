# Private Owner Dashboard

This is a separate Cloudflare Pages project. Never deploy this folder to the public search site's Pages project.

## GitHub OAuth authentication

The dashboard uses GitHub OAuth authorization-code flow with PKCE (S256). The callback checks the configured numeric GitHub account ID and confirms that the exact configured Owner email appears in GitHub's verified email list. The GitHub access token is used only server-side for identity lookup and is never stored in the browser or session. The app issues an eight-hour signed, HttpOnly, Secure, SameSite=Lax session cookie. OAuth state and PKCE verifier are short-lived HttpOnly cookies. Logout requires same-origin plus a session CSRF token.

Register an OAuth App at https://github.com/settings/developers. Set the callback URL to:

`https://ph-exam-results-owner.pages.dev/auth/callback`

Configure these production Pages settings:

- `GITHUB_OAUTH_CLIENT_ID` — variable
- `GITHUB_OAUTH_CLIENT_SECRET` — secret
- `OWNER_GITHUB_ID` — numeric GitHub account ID variable
- `OWNER_EMAIL` — exact verified email variable
- `SESSION_SIGNING_KEY` — secret, at least 32 characters of random material
- `CF_ACCOUNT_ID` — variable
- `CF_D1_DATABASE_ID` — variable
- `CF_D1_READ_API_TOKEN` — secret (D1 Read only)

Generate a session signing key locally in Codespaces with:

`python -c "import secrets; print(secrets.token_urlsafe(48))"`

Do not paste the generated value into chat or commit it. Do not configure Cloudflare Access for this project.

## Cloudflare resources and GitHub Actions

1. Create the separate Pages project `ph-exam-results-owner`, production branch `main`.
2. Create D1 database `ph-exam-results-operations` and retain its database ID.
3. Create narrowly scoped Cloudflare tokens: D1 Edit for trusted migration/writers, D1 Read for dashboard reads, Pages Edit for deployment.
4. Add repository Actions secrets: `CF_ACCOUNT_ID`, `CF_D1_DATABASE_ID`, `CF_D1_API_TOKEN` (D1 Edit), `CF_PAGES_API_TOKEN` (Pages Edit), and `CF_OWNER_PAGES_PROJECT_NAME` (`ph-exam-results-owner`).
5. Set repository variable `CF_OWNER_DASHBOARD_ENABLED=true` only after OAuth, Pages configuration, and D1 migration are ready.
6. Configure the production Watcher Worker with `CF_ACCOUNT_ID`, `CF_D1_DATABASE_ID`, and `CF_D1_API_TOKEN`.
7. Run **Actions → Migrate Private Activity Monitor D1 → Run workflow** on `main`, then deploy only after auth validation passes.

## Routes

- `/` — private Owner activity timeline
- `/auth/login` — begin GitHub OAuth
- `/auth/callback` — validate state, PKCE, Owner GitHub ID and verified email
- `/auth/session` — return session status and CSRF token (no OAuth token)
- `/auth/logout` — CSRF-protected logout
- `/api/activity` — signed-session-protected D1 activity API

No OAuth token, Cloudflare token, D1 credential, or session signing key is exposed in frontend code. Public examination search remains independent and unchanged.
