# Private Owner Activity Dashboard

The Owner signs in from the public website using **Firebase Authentication email/password only**. The password is the one already created for the Owner account in Firebase Authentication. No email code, OTP, or GitHub OAuth step is required.

## 1. Owner account requirements

The dedicated Firebase project is `ph-exam-results-dd94a`.

- Enable Authentication → Sign-in method → Email/Password.
- The Owner account must exist in Firebase Authentication and its email must be verified in Firebase.
- Firestore must contain `users/{Firebase Auth UID}` with:
  - `email`: exact Owner email (string)
  - `role`: `owner` (string, lowercase)
  - `active`: `true` (Boolean, not the text string `"true"`)
- The email entered on the public login form must match both the Firebase Authentication email and the Firestore profile email.
- The Owner's Firebase UID must match `FIREBASE_OWNER_UID` when that optional pin is configured.

Merge this Firestore rule behavior into existing rules; do not replace unrelated application rules:

```javascript
match /users/{userId} {
  allow read: if request.auth != null && request.auth.uid == userId;
  allow create, update, delete: if false;
}
```

Trusted Firebase Admin operations bypass Firestore rules. Never put an Admin SDK credential in the browser or repository.

## 2. Password-only sign-in flow

1. The Owner opens the public website and selects Owner Login.
2. The Owner enters the Firebase Authentication email and password.
3. The public page sends the credentials over HTTPS to the private dashboard's CORS-restricted `/auth/firebase` endpoint. The password is not logged or stored.
4. The server signs in through Firebase Identity Toolkit using its server-side `FIREBASE_API_KEY`, verifies the Firebase ID token's RS256 signature and claims, and requires a verified email.
5. The server reads `users/{uid}` from Firestore and requires the exact Firestore email, `role: "owner"`, and `active: true`. If configured, `FIREBASE_OWNER_UID` must also match.
6. The server returns a short-lived signed proof. The browser carries it in a URL fragment to `/continue.html`; fragments are not sent in HTTP requests.
7. The handoff page immediately removes the fragment from browser history and posts the proof to the dashboard's same-origin `/auth/firebase/complete` endpoint.
8. The endpoint exchanges the proof for an eight-hour signed, Secure, HttpOnly, SameSite=Lax session cookie. The browser opens the private dashboard directly.

There is no email code, OTP, GitHub sign-in, or second identity-provider prompt in this flow. Firebase's verified-email claim is checked as an account property; it does not send a code on each login.

## 3. Production Pages settings

Use the separate Cloudflare Pages project `ph-exam-results-owner`, with production branch `main`. Never deploy this folder to the public search site's Pages project.

Required production environment variables:

- `FIREBASE_PROJECT_ID` — `ph-exam-results-dd94a`
- `FIREBASE_API_KEY` — Firebase Web App API key, stored as a private Pages secret
- `FIREBASE_OWNER_UID` — exact Firebase Owner UID (optional additional pin; recommended)
- `PUBLIC_SITE_ORIGIN` — `https://ph-exam-results.pages.dev`
- `OWNER_EMAIL` — exact verified Owner email, matching Firebase Authentication and Firestore
- `SESSION_SIGNING_KEY` — secret, at least 32 characters of random material
- `CF_ACCOUNT_ID` — Cloudflare account ID
- `CF_D1_DATABASE_ID` — D1 database UUID
- `CF_D1_READ_API_TOKEN` — D1 Read-only API token

Legacy GitHub OAuth variables, if already present in Cloudflare Pages, are no longer used by Owner login and do not need to be changed for this flow.

Do not configure Cloudflare Access for this project. Do not expose Firebase API keys, ID tokens, D1 credentials, or session signing keys in public frontend assets.

## 4. D1 and GitHub Actions

1. Retain D1 database `ph-exam-results-operations` and its UUID.
2. Use narrowly scoped Cloudflare tokens: D1 Edit for trusted migration/writers, Pages Edit for deployment, and D1 Read for dashboard reads.
3. Add repository Actions secrets: `CF_ACCOUNT_ID`, `CF_D1_DATABASE_ID`, `CF_D1_API_TOKEN` (D1 Edit), `CF_PAGES_API_TOKEN` (Pages Edit), and `CF_OWNER_PAGES_PROJECT_NAME` (`ph-exam-results-owner`).
4. Set repository variable `CF_OWNER_DASHBOARD_ENABLED=true` only after the separate Pages project, Firebase settings, D1, and production variables are ready.
5. Run **Actions → Deploy Private Owner Dashboard → Run workflow** on `main`. The workflow applies the additive D1 migration, verifies required tables, deploys the isolated Pages project, and checks the production configuration health endpoint.

Generate the session signing key locally in Codespaces with:

`python -c "import secrets; print(secrets.token_urlsafe(48))"`

Do not paste the generated secret into chat or commit it.

## 5. Route protection

- `/continue.html`, `/continue`, `/continue.js`, and `/continue.css` — public, short-lived proof handoff only
- `/auth/firebase` — CORS-restricted Firebase email/password and Firestore Owner verification
- `/auth/firebase/complete` — same-origin proof validation and HttpOnly Owner session creation
- `/auth/session` — session status and CSRF token (no Firebase ID token)
- `/auth/logout` — same-origin CSRF-protected logout; clears the session cookie
- Dashboard HTML, scripts, styles, and private APIs — require the signed Firebase Owner session
- `/api/activity` — signed Owner-session-protected D1 activity API

The public search remains static-first and read-only. The dashboard stays isolated on its own Pages project.
