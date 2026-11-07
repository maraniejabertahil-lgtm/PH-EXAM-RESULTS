# Private Owner Dashboard

This is a separate Cloudflare Pages project. Never deploy this folder to the public search site's Pages project.

## Firebase Owner-role authentication

The public website at `https://ph-exam-results.pages.dev` signs the Owner in with Firebase Email/Password Authentication. The public browser obtains a short-lived Firebase ID token in memory and POSTs it to this project's `/auth/firebase/exchange` endpoint. The token is never placed in a URL or manually stored in localStorage.

The Pages Function verifies the Google Secure Token RS256 signature and Firebase token claims, then reads `users/{uid}` from Firestore using that ID token. Access is granted only when the Firestore document contains `role: "owner"` and `active: true`, and the verified email matches `OWNER_EMAIL`. The function then issues an eight-hour signed, HttpOnly, Secure, SameSite=Lax session cookie. The private dashboard page redirects unauthenticated visitors to the public login page; the activity API independently checks the signed session.

The existing GitHub OAuth endpoints are retained temporarily as a fallback during rollout. Do not remove their secrets or code until Firebase login has been tested end-to-end and the Owner approves cleanup.

## Required production Pages settings

Set these variables/secrets on the separate `ph-exam-results-owner` Pages project:

- `FIREBASE_PROJECT_ID` — variable: `ph-exam-results-dd94a`
- `PUBLIC_SITE_ORIGIN` — variable: `https://ph-exam-results.pages.dev` (origin only, no trailing slash)
- `OWNER_EMAIL` — variable: the exact verified Firebase Owner email
- `SESSION_SIGNING_KEY` — secret, at least 32 characters of random material
- Keep existing `CF_ACCOUNT_ID`, `CF_D1_DATABASE_ID`, and `CF_D1_READ_API_TOKEN` settings unchanged.

The Firestore `users/{uid}` document must have `role` string `owner`, `active` boolean `true`, and the matching Owner email. Firestore rules must permit an authenticated user to read only their own user document.

## Existing GitHub OAuth fallback

The current GitHub OAuth endpoints remain in place temporarily. Their existing settings may remain configured during validation. Do not delete or rotate existing credentials as part of this change.

## Routes

- `/` — private Owner activity timeline; unauthenticated requests redirect to the public login page
- `/auth/firebase/exchange` — validates Firebase ID token and Owner role, then issues the private session cookie
- `/auth/session` — returns session status and CSRF token (no provider token)
- `/auth/logout` — CSRF-protected logout
- `/api/activity` — signed-session-protected D1 activity API
- `/auth/login` and `/auth/callback` — retained GitHub OAuth fallback

No Firebase ID token, OAuth token, Cloudflare token, D1 credential, or session signing key is exposed in frontend code. Public examination search remains independent of the private activity API.
