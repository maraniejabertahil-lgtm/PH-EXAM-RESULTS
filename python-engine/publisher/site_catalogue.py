"""Build the static website catalogue from hash-bound per-exam dataset manifests."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any

class CatalogueError(ValueError):
    """Raised when a published dataset manifest cannot safely enter the site catalogue."""

def build_site_catalogue(data_root: str | Path, *, overlay: dict[str, Any] | None = None) -> dict[str, Any]:
    root = Path(data_root).resolve()
    manifests: dict[tuple[str, str, str], dict[str, Any]] = {}
    if root.exists():
        for path in root.glob("*/*/*/manifest.json"):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise CatalogueError(f"Cannot read dataset manifest {path}: {exc}") from exc
            manifests[(str(item.get("authority")), str(item.get("exam")), str(item.get("year")))] = item
    if overlay:
        manifests[(str(overlay.get("authority")), str(overlay.get("exam")), str(overlay.get("year")))] = overlay

    authorities: dict[str, Any] = {}
    for (authority, exam, year), item in sorted(manifests.items()):
        if authority not in {"PRC", "CSC"} or not exam or not year.isdigit():
            raise CatalogueError("Dataset manifest has an invalid authority, exam, or year.")
        shards = item.get("shards")
        if not isinstance(shards, list) or not shards:
            raise CatalogueError(f"{authority}/{exam}/{year} has no shard entries.")
        files: dict[str, Any] = {}
        for index, shard in enumerate(shards, start=1):
            name, digest = shard.get("file"), shard.get("sha256")
            count, size = shard.get("record_count"), shard.get("size_bytes")
            if (not isinstance(name, str) or Path(name).name != name or
                not name.startswith(year + "-") or not name.endswith(".json") or
                not isinstance(digest, str) or len(digest) != 64 or
                not isinstance(count, int) or count < 1 or
                not isinstance(size, int) or size < 1 or size > 10 * 1024 * 1024):
                raise CatalogueError(f"{authority}/{exam}/{year} has an invalid shard entry.")
            files[f"S{index:03d}"] = {
                "path": f"/data/{authority}/{exam}/{year}/{name}",
                "hash": digest, "record_count": count, "size_bytes": size,
            }
        authorities.setdefault(authority, {"examinations": {}})
        authorities[authority]["examinations"].setdefault(exam, {"years": {}})
        authorities[authority]["examinations"][exam]["years"][year] = {"files": files}
    revision_source = json.dumps(authorities, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    revision = hashlib.sha256(revision_source.encode("utf-8")).hexdigest()
    return {"schema_version": 2, "last_updated": revision, "authorities": authorities}

def serialize_site_catalogue(data_root: str | Path, *, overlay: dict[str, Any] | None = None) -> bytes:
    return (json.dumps(build_site_catalogue(data_root, overlay=overlay), ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
