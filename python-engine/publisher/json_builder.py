import hashlib
import json
from pathlib import Path


COLUMNS = ["name", "rating", "region", "seq"]
SHARDS = ("A-M", "N-Z", "OTHER")


def _shard_for(name: str) -> str:
    first = next((char.upper() for char in (name or "") if char.isalpha()), "")
    if "A" <= first <= "M":
        return "A-M"
    if "N" <= first <= "Z":
        return "N-Z"
    return "OTHER"


def _public_row(record: dict) -> list:
    return [
        record.get("name", ""),
        record.get("rating"),
        record.get("region"),
        record.get("seq"),
    ]


def build_public_datasets(
    records: list[dict],
    output_root: str | Path,
    authority: str,
    examination: str,
    year: int,
    replace_existing: bool = False,
) -> list[dict]:
    """Write compact array-of-arrays JSON shards and return manifest entries."""
    authority_key = authority.lower()
    exam_key = examination.lower().replace(" ", "-")
    base = Path(output_root) / authority_key / exam_key
    buckets = {shard: [] for shard in SHARDS}
    if replace_existing:
        for shard in SHARDS:
            (base / f"{int(year)}-{shard}.json").unlink(missing_ok=True)

    for record in records:
        if record.get("authority") != authority.upper():
            raise ValueError("Record authority does not match dataset authority")
        if record.get("examination") != examination:
            raise ValueError("Record examination does not match dataset examination")
        if record.get("year") != int(year):
            raise ValueError("Record year does not match dataset year")
        name = record.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Public records require a non-empty name")
        buckets[_shard_for(name)].append(record)

    entries = []
    for shard in SHARDS:
        shard_records = buckets[shard]
        if not shard_records:
            continue
        shard_records.sort(key=lambda item: (item.get("search_key", ""), item["name"]))
        payload = {
            "columns": COLUMNS,
            "data": [_public_row(record) for record in shard_records],
        }
        encoded = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        filename = f"{int(year)}-{shard}.json"
        destination = base / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(encoded)
        entries.append({
            "shard": shard,
            "path": "/data/" + destination.relative_to(Path(output_root)).as_posix(),
            "hash": hashlib.sha256(encoded).hexdigest(),
            "record_count": len(shard_records),
            "size_bytes": len(encoded),
        })

    return entries
