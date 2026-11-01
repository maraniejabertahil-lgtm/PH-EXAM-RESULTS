from collections import defaultdict
from difflib import SequenceMatcher


def _scope(record):
    return (
        record.get("authority"),
        record.get("examination"),
        record.get("year"),
    )


def _blocking_keys(name):
    """Return inexpensive candidate blocks for near-match comparison."""
    compact = "".join(character for character in name if character.isalnum())
    if len(compact) < 4:
        return set()
    tokens = [token for token in name.split() if token]
    keys = {
        ("prefix", compact[:2]),
        ("suffix", compact[-2:]),
        ("length", str(len(compact) // 3)),
    }
    if tokens:
        keys.add(("token", tokens[0][:3]))
    return keys


def find_duplicates(
    records: list[dict],
    fuzzy_threshold: float = 0.94,
    max_candidates_per_record: int = 50,
) -> dict:
    """
    Identify exact duplicates and possible fuzzy matches.

    Exact detection is linear. Fuzzy comparisons use bounded candidate blocks
    instead of comparing every record with every other record. Records are
    never deleted or merged; fuzzy matches are review candidates only.
    """
    exact = []
    fuzzy = []
    seen = {}
    scoped_blocks = defaultdict(lambda: defaultdict(list))

    for index, record in enumerate(records):
        scope = _scope(record)
        name = record.get("search_key", "")
        key = (scope, name)
        if name and key in seen:
            exact.append({"first_index": seen[key], "duplicate_index": index})
        elif name:
            seen[key] = index

        for block in _blocking_keys(name):
            scoped_blocks[scope][block].append(index)

    for index, record in enumerate(records):
        name = record.get("search_key", "")
        if not name:
            continue

        candidates = set()
        for block in _blocking_keys(name):
            candidates.update(scoped_blocks[_scope(record)].get(block, ()))
        candidates.discard(index)

        # Compare only later indexes, so each pair is visited at most once.
        # The cap prevents large common-name blocks from creating quadratic work.
        compared_count = 0
        for other_index in sorted(candidate for candidate in candidates if candidate > index):
            if compared_count >= max_candidates_per_record:
                break
            compared_count += 1
            pair = (index, other_index)
            other = records[other_index].get("search_key", "")
            if not other or name == other:
                continue
            ratio = SequenceMatcher(None, name, other).ratio()
            if ratio >= fuzzy_threshold:
                fuzzy.append({
                    "first_index": pair[0],
                    "candidate_index": pair[1],
                    "similarity": round(ratio, 4),
                })

    return {"exact_duplicates": exact, "fuzzy_candidates": fuzzy}
