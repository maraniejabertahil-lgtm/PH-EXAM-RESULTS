# Private operational metadata

This package writes metadata to Cloudflare D1 using the Cloudflare REST API only. It does not use a SQL driver, and it must never store examinee names, search terms, result rows, passwords, tokens, or raw exception details.

## Environment (GitHub Actions secrets)

- CF_ACCOUNT_ID
- CF_D1_DATABASE_ID
- CF_D1_API_TOKEN — scoped to the required D1 database operations only

When none of these variables is configured, the optional activity integration is disabled. Partial configuration is an error for the caller to report safely.

## Schema setup

After creating a D1 database in the Cloudflare dashboard, apply the versioned schema through the REST API:

~~~bash
PYTHONPATH=python-engine python -m database.apply_migrations
~~~

The migration creates only monitoring_logs, import_batches, and release_predictions. Do not add public result records to these tables.

## Private dashboard

Cloudflare Access must protect both /owner/* and /api/owner/* on the Pages hostname. Configure the Pages Function environment variables CF_ACCESS_TEAM_DOMAIN and CF_ACCESS_AUD, plus the D1 REST API credentials. The function independently verifies the Access JWT signature, issuer, audience, and expiry before querying D1. Configure an Access policy that permits only the Owner identity. Do not expose any of these values in public/.
