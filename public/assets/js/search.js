function normalize(value) {
  return String(value ?? "")
    .normalize("NFKC")
    .toLocaleLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

self.onmessage = event => {
  const { requestId, columns, rows, query } = event.data || {};
  const nameIndex = Array.isArray(columns) ? columns.indexOf("name") : -1;
  if (nameIndex < 0 || !Array.isArray(rows)) {
    self.postMessage({ requestId, error: "The search dataset is invalid." });
    return;
  }

  const needle = normalize(query);
  if (!needle) {
    self.postMessage({ requestId, matches: [] });
    return;
  }

  const matches = [];
  for (const row of rows) {
    if (normalize(row[nameIndex]).includes(needle)) {
      matches.push(row);
    }
  }
  self.postMessage({ requestId, matches });
};
