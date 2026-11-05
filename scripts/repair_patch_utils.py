"""Strict normalization of model-generated unified diffs into git-apply format."""


def normalize_patch(raw):
    if not isinstance(raw, str):
        raise ValueError("Patch must be a string")
    text = raw.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff").strip()
    if not text:
        raise ValueError("Empty patch")
    lines = text.splitlines()
    # Models sometimes wrap the diff in Markdown despite being told not to.
    fence = chr(96) * 3
    if lines and lines[0].startswith(fence):
        lines = lines[1:]
    closing_fence = next((i for i, line in enumerate(lines) if line.startswith(fence)), None)
    if closing_fence is not None:
        lines = lines[:closing_fence]
    starts = [i for i, line in enumerate(lines) if line.startswith("diff --git ") or line.startswith("--- a/")]
    if not starts:
        raise ValueError("No recognized unified diff headers")
    lines = lines[starts[0]:]
    while lines and not lines[-1].strip():
        lines.pop()
    if lines[0].startswith("diff --git "):
        return "\n".join(lines) + "\n"

    # Accept standard unified diffs and add deterministic git file headers.
    output = []
    i = 0
    while i < len(lines):
        if not lines[i].startswith("--- a/"):
            raise ValueError("Unexpected content between unified diff file sections")
        old_header = lines[i]
        if i + 1 >= len(lines) or not lines[i + 1].startswith("+++ b/"):
            raise ValueError("Unified diff must contain matching --- a/ and +++ b/ headers")
        new_header = lines[i + 1]
        old_path = old_header[6:].split("\t", 1)[0]
        new_path = new_header[6:].split("\t", 1)[0]
        if not old_path or old_path != new_path:
            raise ValueError("Only in-place modifications are supported")
        output.append("diff --git a/" + old_path + " b/" + new_path)
        output.extend((old_header, new_header))
        i += 2
        while i < len(lines) and not lines[i].startswith("--- a/"):
            output.append(lines[i])
            i += 1
    normalized = "\n".join(output) + "\n"
    if "@@" not in normalized:
        raise ValueError("Unified diff contains no hunks")
    return normalized
