"""Apply the versioned D1 schema using the Cloudflare D1 REST API."""
from __future__ import annotations

from pathlib import Path

from database.d1_client import D1Client


def apply_migrations(client: D1Client, directory: str | Path | None = None) -> int:
    migration_dir = Path(directory) if directory else Path(__file__).with_name("migrations")
    statements = []
    for path in sorted(migration_dir.glob("*.sql")):
        source = path.read_text(encoding="utf-8")
        statements.extend(statement.strip() for statement in source.split(";") if statement.strip())
    for statement in statements:
        client.query(statement)
    return len(statements)


if __name__ == "__main__":
    client = D1Client.from_env()
    if client is None:
        raise SystemExit("D1 configuration is not set; no migration was applied.")
    print(f"Applied {apply_migrations(client)} D1 schema statements.")
