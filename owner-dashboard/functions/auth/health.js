- name: Sync Owner auth secrets to Pages
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_PAGES_API_TOKEN }}
    CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
    PROJECT_NAME: ${{ secrets.CF_OWNER_PAGES_PROJECT_NAME }}
    GITHUB_OAUTH_CLIENT_SECRET: ${{ secrets.GITHUB_OAUTH_CLIENT_SECRET_OWNER }}
    SESSION_SIGNING_KEY: ${{ secrets.SESSION_SIGNING_KEY }}
    CF_D1_READ_API_TOKEN: ${{ secrets.CF_D1_READ_API_TOKEN }}
  run: |
    for n in GITHUB_OAUTH_CLIENT_SECRET SESSION_SIGNING_KEY CF_D1_READ_API_TOKEN; do
      printf '%s' "${!n}" | npx --yes wrangler@4.156.2 pages secret put "$n" --project-name "$PROJECT_NAME"
    done
