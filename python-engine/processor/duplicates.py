from difflib import SequenceMatcher


def find_duplicates(records: list[dict], fuzzy_threshold: float = 0.94) -> dict:
    """
    Identify exact duplicates and possible fuzzy matches.

    Records are never deleted or merged here. Fuzzy matches are review candidates.
    """
    exact = []
    fuzzy = []
    seen = {}

    for index, record in enumerate(records):
        scope = (
            record.get("authority"),
            record.get("examination"),
            record.get("year"),
        )
        key = (scope, record.get("search_key", ""))
        if key[1] and key in seen:
            exact.append({"first_index": seen[key], "duplicate_index": index})
        elif key[1]:
            seen[key] = index

    for left in range(len(records)):
        a = records[left]
        for right in range(left + 1, len(records)):
            b = records[right]
            if (
                a.get("authority"),
                a.get("examination"),
                a.get("year"),
            ) != (
                b.get("authority"),
                b.get("examination"),
                b.get("year"),
            ):
                continue
            first = a.get("search_key", "")
            second = b.get("search_key", "")
            if not first or not second or first == second:
                continue
            ratio = SequenceMatcher(None, first, second).ratio()
            if ratio >= fuzzy_threshold:
                fuzzy.append({
                    "first_index": left,
                    "candidate_index": right,
                    "similarity": round(ratio, 4),
                })

    return {"exact_duplicates": exact, "fuzzy_candidates": fuzzy}
