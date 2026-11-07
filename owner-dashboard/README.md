# Private Owner Activity Dashboard

This is a separate Cloudflare Pages project. Never deploy this folder to the public search site's Pages project.

## Owner login: public page → Firebase → GitHub OAuth

The Owner starts on the public website. The Owner Login icon at the top-left opens a bilingual email/password dialog. The login is a two-proof authorization gate: Firebase Owner-role verification **AND** the existing GitHub OAuth identity check must both succeed. Neither provider alone can open the dashboard.

### 1. Firebase email/password and Firestore role

The dedicated Firebase project is `ph-exam-results-dd94a`.

- Enable Authentication → Sign-in method → Email/Password.
- The Owner Auth user must exist and have a verified email.
- Firestore must contain `users/{Firebase Auth UID}` with:
  - `role`: string `owner`
  - `active`: boolean `true`
  - `email`: the exact Owner email (recommended; if omitted, the verified Firebase Auth email is used)
- Configure the Firestore rules so an authenticated user can read only their own profile and cannot write/promote their own role. Merge the following behavior into existing rules; do not replace unrelated application rules:

```javascript
match /users/{userId} {
  allow read: if request.auth != null && request.auth.uid == userId;
  allow create, update, delete: if false;
}
```

Trusted Firebase Admin operations bypass Firestore rules. Never place an Admin SDK credential in the browser or repository.

The public page sends the Owner email/password over HTTPS only to the private dashboard endpoint. The dashboard uses its server-side `FIREBASE_API_KEY` Pages variable to request a Firebase ID token, verifies the token's RS256 signature and claims against Google's Secure Token public keys, then reads the Owner's own Firestore document using the ID token. The password is not logged or stored; the API key and Firebase ID token are never sent to the public page or returned to the browser.

### 2. Safe handoff between the two Pages sites

Because the public search site and private dashboard use separate `pages.dev` hostnames, the flow does not depend on third-party cookies:

1. The public login dialog signs in with Firebase using in-memory persistence only.
2. The public page sends the Firebase ID token to the private dashboard's CORS-restricted `/auth/firebase` endpoint.
3. The dashboard verifies the token, exact Owner email, optional exact UID, Firestore `role=owner`, and `active=true`.
4. The server returns a short-lived HMAC-signed proof. The browser carries it in a URL fragment to the dashboard's `/continue.html` page; fragments are not sent in HTTP requests.
5. The handoff page immediately removes the fragment from browser history and posts the proof to the dashboard's same-origin `/auth/firebase/complete` endpoint. That endpoint sets a Secure, HttpOnly, SameSite=Lax Firebase proof cookie.
6. The browser proceeds to GitHub OAuth. The proof is short-lived and no Firebase password or ID token is stored in the dashboard session.

### 3. Existing GitHub OAuth second check

Register or retain the GitHub OAuth App at https://github.com/settings/developers. Callback URL:

`https://ph-exam-results-owner.pages.dev/auth/callback`

The configured GitHub account ID is `338246827`. Configure:

- `GITHUB_OAUTH_CLIENT_ID` — variable
- `GITHUB_OAUTH_CLIENT_SECRET` — secret
- `OWNER_GITHUB_ID` — `338246827`
- `OWNER_EMAIL` — exact verified Owner email, identical to Firebase
- `SESSION_SIGNING_KEY` — secret, at least 32 characters of random material

GitHub OAuth uses authorization-code flow with PKCE S256 and a one-time state cookie. The server verifies both the numeric GitHub account ID and the exact verified Owner email. Only after both Firebase and GitHub checks pass is an eight-hour signed HttpOnly session issued.

### 4. Production Pages settings

Create the separate Pages project `ph-exam-results-owner`, production branch `main`. Never reuse the public search Pages project.

Configure these production environment variables:

- `FIREBASE_PROJECT_ID` — `ph-exam-results-dd94a`
- `FIREBASE_API_KEY` — Firebase Web App API key, configured only as a private Pages environment variable (not in public source)
- `FIREBASE_OWNER_UID` — exact Firebase Owner UID (optional additional pin; recommended)
- `PUBLIC_SITE_ORIGIN` — `https://ph-exam-results.pages.dev`
- `OWNER_GITHUB_ID` — `338246827`
- `OWNER_EMAIL` — exact verified Owner email
- `GITHUB_OAUTH_CLIENT_ID` — OAuth App client ID
- `GITHUB_OAUTH_CLIENT_SECRET` — secret
- `SESSION_SIGNING_KEY` — secret, at least 32 characters
- `CF_ACCOUNT_ID` — Cloudflare account ID
- `CF_D1_DATABASE_ID` — D1 database UUID
- `CF_D1_READ_API_TOKEN` — D1 Read-only API token

Do not configure Cloudflare Access for this project.

### 5. D1 and GitHub Actions

1. Create D1 database `ph-exam-results-operations` and retain its UUID.
2. Create narrowly scoped Cloudflare tokens: D1 Edit for trusted migration/writers, D1 Read for dashboard reads, Pages Edit for deployment.
3. Add repository Actions secrets: `CF_ACCOUNT_ID`, `CF_D1_DATABASE_ID`, `CF_D1_API_TOKEN` (D1 Edit), `CF_PAGES_API_TOKEN` (Pages Edit), and `CF_OWNER_PAGES_PROJECT_NAME` (`ph-exam-results-owner`).
4. Set repository variable `CF_OWNER_DASHBOARD_ENABLED=true` only after the separate Pages project, OAuth, D1, and production variables are ready.
5. Configure the production Watcher Worker with `CF_D1_API_TOKEN`, `CF_ACCOUNT_ID`, and `CF_D1_DATABASE_ID`.
6. Run **Actions → Deploy Private Owner Dashboard → Run workflow** on `main`. Its deployment job applies the idempotent additive D1 migration, verifies all required tables, deploys the isolated Pages project, and checks the production configuration health endpoint. The separate **Migrate Private Activity Monitor D1** workflow remains available for manual schema maintenance.

Generate the session signing key locally in Codespaces with:

`python -c "import secrets; print(secrets.token_urlsafe(48))"`

Do not paste the generated secret into chat or commit it.

## Route protection

- `/continue.html` and `/continue.js` — public, short-lived proof handoff only
- `/auth/firebase` — CORS-restricted Firebase ID-token + Firestore Owner verification
- `/auth/firebase/complete` — same-origin proof validation and HttpOnly Firebase cookie
- `/auth/login` and `/auth/callback` — existing GitHub OAuth PKCE flow, gated by Firebase proof
- `/auth/session` — return dual-proof session status and CSRF token (no OAuth token)
- `/auth/logout` — same-origin CSRF-protected logout; clears both proof/session cookies
- `/api/activity` — signed dual-proof session-protected D1 activity API
- All dashboard HTML, scripts, styles, and private APIs require the combined session.

No OAuth token, Cloudflare token, D1 credential, Firebase Admin credential, or session signing key is exposed in frontend assets. The public search remains static-first and read-only.
