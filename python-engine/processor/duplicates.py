from bisect import bisect_right
from collections import defaultdict
from difflib import SequenceMatcher
from heapq import merge
from itertools import islice


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

        scope_blocks = scoped_blocks[_scope(record)]
        candidate_iterators = []
        for block in _blocking_keys(name):
            block_indexes = scope_blocks.get(block, ())
            start = bisect_right(block_indexes, index)
            if start < len(block_indexes):
                candidate_iterators.append(islice(block_indexes, start, None))

        # Each block is already sorted by record index. Merge lazily so a
        # common prefix cannot allocate and sort a huge candidate set per row.
        # Deduplicate overlapping blocks and stop as soon as the comparison cap
        # is reached; this keeps both memory and comparison work bounded.
        compared_count = 0
        previous_candidate = None
        for other_index in merge(*candidate_iterators):
            if other_index == previous_candidate:
                continue
            previous_candidate = other_index
            if compared_count >= max_candidates_per_record:
                break
            compared_count += 1
            other = records[other_index].get("search_key", "")
            if not other or name == other:
                continue
            ratio = SequenceMatcher(None, name, other).ratio()
            if ratio >= fuzzy_threshold:
                fuzzy.append({
                    "first_index": index,
                    "candidate_index": other_index,
                    "similarity": round(ratio, 4),
                })

    return {"exact_duplicates": exact, "fuzzy_candidates": fuzzy}
