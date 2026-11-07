# Private Owner Activity Dashboard — Production Setup

The private Owner dashboard is an isolated Cloudflare Pages project named `ph-exam-results-owner`. It must never be deployed to the public examination search Pages project.

The login requires two independent proofs:
1. Firebase email/password authentication plus an active Firestore `users/{uid}` profile with `role: "owner"` and `active: true`.
2. The existing GitHub OAuth account with numeric ID `338246827` and the same exact verified Owner email.

No Cloudflare Zero Trust / Access dependency is used. The dashboard hostname and every private route are protected by Pages Functions middleware and a signed dual-proof session.

## A. Firebase prerequisites

Firebase project: `ph-exam-results-dd94a`.

- Enable Authentication → Sign-in method → Email/Password.
- Ensure the Owner Auth user exists and its email is verified.
- Ensure Firestore has `users/{Firebase Auth UID}` with `role: "owner"`, `active: true`, and preferably `email: "<exact Owner email>"`.
- Firestore rules must permit an authenticated user to read only their own profile document, but must not permit that user to create, update, or delete their role. Merge the rule into existing rules; do not replace unrelated rules:

```javascript
match /users/{userId} {
  allow read: if request.auth != null && request.auth.uid == userId;
  allow create, update, delete: if false;
}
```

Trusted server-side Firebase Admin operations bypass Firestore rules. Do not place an Admin SDK key in the browser or repository.

## B. Create the isolated Cloudflare resources

1. Create Pages project `ph-exam-results-owner` with production branch `main`.
2. Create D1 database `ph-exam-results-operations`; retain its UUID.
3. Configure the dashboard Pages production environment variables:
   - `FIREBASE_PROJECT_ID` = `ph-exam-results-dd94a`
   - `FIREBASE_API_KEY` = Firebase Web App API key (public client configuration value)
   - `FIREBASE_OWNER_UID` = exact Firebase Owner UID (optional additional pin; recommended)
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
- `CF_OWNER_DASHBOARD_ENABLED` = `true`, only after the isolated Pages project, OAuth, D1 and production variables are ready.

The production Watcher Worker also needs `CF_D1_API_TOKEN`, `CF_ACCOUNT_ID`, and `CF_D1_DATABASE_ID` for trusted activity writes.

## D. Migration, deployment and live acceptance

1. Run **Actions → Migrate Private Activity Monitor D1 → Run workflow** on `main`.
2. Run **Actions → Deploy Private Owner Dashboard → Run workflow** on `main`.
3. Open `https://ph-exam-results.pages.dev/` and use the Owner Login icon in the header.
4. Sign in with the verified Firebase Owner email/password. The server must verify the ID token, exact email, Firestore role and active flag.
5. Complete the GitHub OAuth step. The server must verify account ID `338246827` and the same exact verified email.
6. Verify the private activity timeline loads and shows recorded events.
7. Sign out. Verify the dashboard root redirects to `/login.html` and `/api/activity` returns 401.
8. Attempt Firebase sign-in using a non-owner or inactive account; it must be denied before GitHub OAuth.
9. Attempt GitHub OAuth using another GitHub account; it must be denied and no dashboard session may be issued.
10. Confirm logout clears both cookies and the public search page remains available without authentication.

Generate a session signing key locally in Codespaces with:

`python -c "import secrets; print(secrets.token_urlsafe(48))"`

Never paste the generated secret into chat or commit it. The Firebase Web API key is public client configuration, not an Admin SDK credential. No OAuth token, Cloudflare token, D1 credential, Firebase Admin credential, or session signing key may be shipped to frontend assets.
