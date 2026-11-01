import hashlib
import json
from pathlib import Path


COLUMNS = ["name", "rating", "region", "seq"]
MAX_SHARD_BYTES = 10 * 1024 * 1024


def _initial_letter(name: str) -> str | None:
    for character in (name or "").upper():
        if "A" <= character <= "Z":
            return character
    return None


def _encode(records: list[dict]) -> bytes:
    payload = {
        "columns": COLUMNS,
        "data": [
            [
                record.get("name", ""),
                record.get("rating"),
                record.get("region"),
                record.get("seq"),
            ]
            for record in records
        ],
    }
    return (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _split_range(records: list[dict], start: str, end: str) -> list[tuple[str, list[dict]]]:
    if len(_encode(records)) <= MAX_SHARD_BYTES:
        return [(f"{start}-{end}", records)]
    if start == end:
        raise ValueError(
            f"Alphabetical shard {start}-{end} exceeds 10 MiB. "
            "It needs a finer-grained partition before publication."
        )
    midpoint = (ord(start) + ord(end)) // 2
    left_end = chr(midpoint)
    right_start = chr(midpoint + 1)
    left = [record for record in records if (letter := _initial_letter(record.get("name"))) and start <= letter <= left_end]
    right = [record for record in records if (letter := _initial_letter(record.get("name"))) and right_start <= letter <= end]
    return (
        _split_range(left, start, left_end)
        + _split_range(right, right_start, end)
    )


def build_public_datasets(
    records: list[dict],
    output_root: str | Path,
    authority: str,
    examination: str,
    year: int,
    replace_existing: bool = False,
) -> list[dict]:
    """Write compact array-of-arrays JSON shards, capped at 10 MiB each."""
    authority_key = authority.lower()
    exam_key = examination.lower().replace(" ", "-")
    base = Path(output_root) / authority_key / exam_key
    if replace_existing:
        for old_file in base.glob(f"{int(year)}-*.json") if base.exists() else []:
            old_file.unlink()

    letter_buckets = {chr(code): [] for code in range(ord("A"), ord("Z") + 1)}
    other_records = []

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
        letter = _initial_letter(name)
        if letter:
            letter_buckets[letter].append(record)
        else:
            other_records.append(record)

    groups = []
    left = [record for letter in "ABCDEFGHIJKLM" for record in letter_buckets[letter]]
    right = [record for letter in "NOPQRSTUVWXYZ" for record in letter_buckets[letter]]
    if left:
        groups.extend(_split_range(left, "A", "M"))
    if right:
        groups.extend(_split_range(right, "N", "Z"))
    if other_records:
        if len(_encode(other_records)) > MAX_SHARD_BYTES:
            raise ValueError("The OTHER alphabetical shard exceeds 10 MiB and requires review.")
        groups.append(("OTHER", other_records))

    entries = []
    for shard, shard_records in groups:
        shard_records.sort(key=lambda item: (item.get("search_key", ""), item["name"]))
        encoded = _encode(shard_records)
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
