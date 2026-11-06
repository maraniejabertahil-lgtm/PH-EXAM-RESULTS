# Private Owner Dashboard

This is a separate Cloudflare Pages project. It must not be added to the public search site's Pages project.

## Cloudflare setup (one time)

1. In Cloudflare, open **Workers & Pages** and create a new Pages project named **ph-exam-results-owner**. Use the Direct Upload project option; do not connect this project to the public website's deployment.
2. Open the new private project's **Settings** and enable its **Access policy**. In Zero Trust, edit the generated Access application and make the Allow policy match only the Owner identity. Keep the default deny behavior. Protect the production pages.dev hostname and preview deployments.
3. In the private Pages project's **Settings → Variables and Secrets**, add these production variables:
   - CF_ACCESS_TEAM_DOMAIN
   - CF_ACCESS_AUD
   - CF_ACCOUNT_ID
   - CF_D1_DATABASE_ID
4. Add the production secret CF_D1_READ_TOKEN. This must be a separate Cloudflare API token with D1 Read permission for this database.
5. Create the D1 database for private operational metadata. Do not store examinee names or result rows in it.
6. In GitHub repository Settings → Secrets and variables → Actions, add:
   - CF_ACCOUNT_ID
   - CF_D1_DATABASE_ID
   - CF_D1_API_TOKEN (D1 Edit permission for the database)
   - CF_OWNER_PAGES_PROJECT_NAME = ph-exam-results-owner
7. In the existing production Watcher Worker settings, add variables CF_ACCOUNT_ID and CF_D1_DATABASE_ID, and secret CF_D1_API_TOKEN.

After PR #107 is merged, run **Actions → Initialize private D1 activity schema → Run workflow**. The dedicated deploy workflow will publish this folder to the private Pages project on later main-branch updates.

## Routes

- / — private Owner activity dashboard
- /api/activity — Access-JWT-verified API returning D1 operational metadata

The entire Pages project is private behind Cloudflare Access. The public PH Exam Results Pages project must remain public and must not have an Access policy enabled.
