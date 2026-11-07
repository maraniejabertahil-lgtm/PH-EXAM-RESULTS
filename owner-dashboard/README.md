# Private Owner Dashboard

This is a separate Cloudflare Pages project. Never deploy this folder to the public search site's Pages project.

## Two-step Owner authentication

The dashboard requires **both** identity systems before granting access. Firebase is the first authorization gate; GitHub OAuth remains the second independent identity check. Neither provider alone can create a dashboard session.

### 1. Firebase email/password + Firestore Owner role

The dedicated Firebase project is `ph-exam-results-dd94a`.

Configure these production Pages variables:

- `FIREBASE_PROJECT_ID` — `ph-exam-results-dd94a`
- `FIREBASE_API_KEY` — Firebase Web App API key (public Firebase client configuration value; not an Admin SDK credential)
- `FIREBASE_OWNER_UID` — optional additional exact UID pin; if set, it must match the Owner Auth UID
- `OWNER_EMAIL` — the same exact verified email used by GitHub OAuth

Enable Email/Password in Firebase Authentication. The Owner must have a Firebase Authentication user and a Firestore document at `users/{Firebase Auth UID}` with:
- `role`: string `owner`
- `active`: boolean `true`
- `email`: the exact Owner email (recommended; when omitted, the verified Firebase Auth email is used)

The Firebase Auth email must be verified and must exactly match `OWNER_EMAIL`. The server verifies the ID token with Firebase Identity Toolkit, then reads the Owner's own Firestore profile using that ID token. The Firestore rules must allow an authenticated user to read only their own `users/{uid}` document and must not allow that user to write or promote their own role. Merge the following behavior into the existing rules; do not replace unrelated application rules:

```javascript
match /users/{userId} {
  allow read: if request.auth != null && request.auth.uid == userId;
  allow create, update, delete: if false;
}
```

If existing rules intentionally allow trusted administrative writes, preserve those trusted server-side paths while keeping client self-promotion impossible.

### 2. Existing GitHub OAuth identity check

Register or retain the GitHub OAuth App at https://github.com/settings/developers. Callback URL:

`https://ph-exam-results-owner.pages.dev/auth/callback`

The configured GitHub account ID is `338246827`. Configure:

- `GITHUB_OAUTH_CLIENT_ID` — variable
- `GITHUB_OAUTH_CLIENT_SECRET` — secret
- `OWNER_GITHUB_ID` — `338246827`
- `OWNER_EMAIL` — exact verified Owner email, identical to Firebase
- `SESSION_SIGNING_KEY` — secret, at least 32 characters of random material

The GitHub access token is used only server-side for identity lookup and is never stored in the browser or session. OAuth uses authorization-code flow with PKCE S256 and a one-time state cookie.

### 3. Session and route protection

1. Firebase email/password login obtains an ID token directly from Firebase over HTTPS.
2. The dashboard server validates the token, exact Owner email, email verification, Firestore `role=owner`, `active=true`, and optional exact UID pin.
3. A 10-minute HttpOnly Firebase proof cookie permits the second step only.
4. GitHub OAuth verifies the configured numeric GitHub account ID and the exact verified Owner email.
5. Only then does the server issue an eight-hour signed HttpOnly session.
6. A Pages Functions middleware protects the dashboard root, scripts, styles other than the public login assets, and every private route. Direct URL entry without a valid dual-proof session redirects to `/login.html`.
7. The activity API independently verifies the signed session and uses a D1 Read-only token. Logout requires same-origin plus a CSRF token and clears both session cookies.

The public login page is `/login.html`. The public examination search remains independent and read-only.

## Cloudflare resources and GitHub Actions

1. Create the separate Pages project `ph-exam-results-owner`, production branch `main`. Never reuse the public search Pages project.
2. Create D1 database `ph-exam-results-operations` and retain its database ID.
3. Create narrowly scoped Cloudflare tokens: D1 Edit for trusted migration/writers, D1 Read for dashboard reads, Pages Edit for deployment.
4. Add repository Actions secrets: `CF_ACCOUNT_ID`, `CF_D1_DATABASE_ID`, `CF_D1_API_TOKEN` (D1 Edit), `CF_PAGES_API_TOKEN` (Pages Edit), and `CF_OWNER_PAGES_PROJECT_NAME` (`ph-exam-results-owner`).
5. Set repository variable `CF_OWNER_DASHBOARD_ENABLED=true` only after OAuth, Pages configuration, and D1 migration are ready.
6. Configure the production Watcher Worker with `CF_D1_API_TOKEN`, `CF_ACCOUNT_ID`, and `CF_D1_DATABASE_ID`.
7. Add the Pages production variables/secrets from sections 1–2 plus `CF_D1_READ_API_TOKEN` (secret), `CF_ACCOUNT_ID`, and `CF_D1_DATABASE_ID`.
8. Run **Actions → Migrate Private Activity Monitor D1 → Run workflow** on `main`.
9. After migration and auth configuration, run **Deploy Private Owner Dashboard** on `main`.

Generate a session signing key locally in Codespaces with:

`python -c "import secrets; print(secrets.token_urlsafe(48))"`

Do not paste the generated value into chat or commit it. Do not configure Cloudflare Access for this project.

## Routes

- `/login.html` — Firebase email/password sign-in
- `/auth/firebase/config` — public Firebase client configuration only
- `/auth/firebase` — server-side Firebase ID-token and Firestore Owner-role verification
- `/auth/login` — begin GitHub OAuth only after Firebase proof
- `/auth/callback` — validate state, PKCE, Firebase proof, GitHub Owner ID and verified email
- `/auth/session` — return dual-proof session status and CSRF token (no OAuth token)
- `/auth/logout` — CSRF-protected logout; clears both session cookies
- `/api/activity` — signed dual-proof session-protected D1 activity API

No OAuth token, Cloudflare token, D1 credential, Firebase Admin credential, or session signing key is exposed in frontend code.
