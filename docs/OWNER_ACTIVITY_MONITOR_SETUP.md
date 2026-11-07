# Private Owner Activity Dashboard — Production Setup

The private Owner dashboard is an isolated Cloudflare Pages project named `ph-exam-results-owner`. It must never be deployed to the public examination search Pages project.

The Owner starts from the public search page's bilingual Owner Login icon. Access requires both:
1. Firebase email/password authentication plus a verified email and Firestore `users/{uid}` profile with `role: "owner"` and `active: true`.
2. The existing GitHub OAuth account ID `338246827` and the same exact verified Owner email.

The public and private Pages hostnames are separate sites. The Firebase proof handoff uses a short-lived signed token in a URL fragment, immediately removed by the private handoff page, then exchanged for a first-party HttpOnly cookie. This avoids reliance on third-party cookies on iOS/Safari. No Cloudflare Access / Zero Trust dependency is used.

## A. Firebase prerequisites

Firebase project: `ph-exam-results-dd94a`.

- Enable Authentication → Sign-in method → Email/Password.
- Ensure the Owner Auth user exists and its email is verified.
- Ensure Firestore has `users/{Firebase Auth UID}` with `role: "owner"`, `active: true`, and preferably `email: "<exact Owner email>"`.
- Firestore rules must permit an authenticated user to read only their own profile document, but must not permit that user to create, update, or delete their role. Merge this behavior into existing rules; do not replace unrelated application rules:

```javascript
match /users/{userId} {
  allow read: if request.auth != null && request.auth.uid == userId;
  allow create, update, delete: if false;
}
```

The public page sends the Owner email/password over HTTPS only to the private dashboard endpoint. The dashboard uses the server-side `FIREBASE_API_KEY` Pages variable to obtain a Firebase ID token, verifies its RS256 signature and claims against Google's Secure Token public keys, and reads the Owner's own Firestore profile using that ID token. The password is not logged or stored; the API key and Firebase ID token are never sent to the public page or returned to the browser.

## B. Create the isolated Cloudflare resources

1. Create Pages project `ph-exam-results-owner` with production branch `main`.
2. Create D1 database `ph-exam-results-operations`; retain its UUID.
3. Configure dashboard Pages production variables/secrets:
   - `FIREBASE_PROJECT_ID` = `ph-exam-results-dd94a`
   - `FIREBASE_OWNER_UID` = exact Firebase Owner UID (optional additional pin; recommended)
   - `PUBLIC_SITE_ORIGIN` = `https://ph-exam-results.pages.dev`
   - `OWNER_GITHUB_ID` = `338246827`
   - `OWNER_EMAIL` = exact verified Owner email shared by Firebase and GitHub
   - `GITHUB_OAUTH_CLIENT_ID` = OAuth App client ID
   - `GITHUB_OAUTH_CLIENT_SECRET` = OAuth App secret
   - `SESSION_SIGNING_KEY` = random secret of at least 32 characters
   - `CF_ACCOUNT_ID` = Cloudflare account ID
   - `CF_D1_DATABASE_ID` = D1 database UUID
   - `CF_D1_READ_API_TOKEN` = D1 Read-only API token
4. Register/retain the GitHub OAuth App callback exactly as:
   `https://ph-exam-results-owner.pages.dev/auth/callback`
5. Do not configure Cloudflare Access for this project.

## C. GitHub Actions settings

Repository secrets:
- `CF_ACCOUNT_ID`
- `CF_D1_DATABASE_ID`
- `CF_D1_API_TOKEN` (D1 Edit for trusted writers/migration)
- `CF_PAGES_API_TOKEN` (Pages Edit)
- `CF_OWNER_PAGES_PROJECT_NAME` = `ph-exam-results-owner`

Repository variable:
- `CF_OWNER_DASHBOARD_ENABLED=true`, only after the isolated Pages project, OAuth, D1 and production variables are ready.

The production Watcher Worker also needs `CF_D1_API_TOKEN`, `CF_ACCOUNT_ID`, and `CF_D1_DATABASE_ID` for trusted activity writes.

## D. Migration, deployment and live acceptance

1. Run **Actions → Deploy Private Owner Dashboard → Run workflow** on `main`. Its deployment job applies the idempotent additive D1 migration, verifies all required tables, deploys the isolated Pages project, and checks the production configuration health endpoint. The separate **Migrate Private Activity Monitor D1** workflow remains available for manual schema maintenance.
3. Only after the private dashboard deploys and signed-out route checks succeed, set `owner_login_enabled: true` in `public/status.json` and deploy the public Pages site. The Owner Login icon is intentionally hidden until this flag is enabled.
3. Open `https://ph-exam-results.pages.dev/` and select the Owner Login icon at the top-left.
4. Sign in with the verified Firebase Owner email/password. The dashboard server must validate the token signature/claims, exact Owner email, Firestore role and active flag.
5. Verify the browser is redirected to the isolated dashboard and completes the GitHub OAuth check for ID `338246827` and the same exact verified email.
6. Verify the private activity timeline loads and shows recorded events.
7. Sign out. Verify the dashboard root redirects to the public login dialog and `/api/activity` returns 401.
8. Attempt Firebase sign-in with a non-owner, inactive, unverified, mismatched-email or wrong-UID account; it must be denied before GitHub OAuth.
9. Attempt GitHub OAuth using another GitHub account; it must be denied and no dashboard session may be issued.
10. Confirm logout clears both cookies and the public search page remains available without authentication.

Generate a session signing key locally in Codespaces with:

`python -c "import secrets; print(secrets.token_urlsafe(48))"`

Never paste the generated secret into chat or commit it. No OAuth token, Cloudflare token, D1 credential, Firebase Admin credential, or session signing key may be shipped to frontend assets.
