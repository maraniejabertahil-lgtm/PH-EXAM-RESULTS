import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


SHARD_PATTERN = re.compile(
    r"^(?P<year>\d{4})-(?P<shard>[A-Z]-[A-Z]|OTHER)(?:-(?P<content_hash>[a-f0-9]{12}))?\.json$"
)


def build_manifest(data_root: str | Path, output_path: str | Path) -> dict:
    root = Path(data_root)
    authorities = {}

    if root.exists():
        for authority_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            authority_key = authority_dir.name.upper()
            authority_entry = {"examinations": {}}

            for exam_dir in sorted(path for path in authority_dir.iterdir() if path.is_dir()):
                exam_entry = {"years": {}}
                by_year = {}

                for dataset in sorted(exam_dir.glob("*.json")):
                    match = SHARD_PATTERN.match(dataset.name)
                    if not match:
                        continue
                    year = match.group("year")
                    shard = match.group("shard")
                    raw = dataset.read_bytes()
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise ValueError(f"Invalid public dataset: {dataset}") from exc
                    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                        raise ValueError(f"Invalid dataset structure: {dataset}")

                    by_year.setdefault(year, {})[shard] = {
                        "path": "/" + dataset.as_posix().replace(
                            root.parent.as_posix().rstrip("/") + "/", ""
                        ),
                        "hash": hashlib.sha256(raw).hexdigest(),
                        "record_count": len(payload["data"]),
                        "size_bytes": len(raw),
                    }

                for year, shards in sorted(by_year.items()):
                    exam_entry["years"][year] = {
                        "sharded": len(shards) > 1,
                        "files": shards,
                    }

                if exam_entry["years"]:
                    authority_entry["examinations"][exam_dir.name.upper()] = exam_entry

            if authority_entry["examinations"]:
                authorities[authority_key] = authority_entry

    manifest = {
        "schema_version": 2,
        "last_updated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "authorities": authorities,
    }
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest
