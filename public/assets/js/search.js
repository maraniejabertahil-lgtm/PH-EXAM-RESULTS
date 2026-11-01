let activeColumns = null;
let activeRows = null;

function normalize(value) {
  return String(value ?? "")
    .normalize("NFKC")
    .toLocaleLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

self.onmessage = event => {
  const message = event.data || {};

  if (message.type === "load") {
    if (!Array.isArray(message.columns) || !Array.isArray(message.rows)) {
      self.postMessage({ type: "loaded", datasetKey: message.datasetKey, error: "Invalid dataset." });
      return;
    }
    activeColumns = message.columns;
    activeRows = message.rows;
    self.postMessage({ type: "loaded", datasetKey: message.datasetKey });
    return;
  }

  if (message.type !== "search") return;
  const { requestId, query } = message;
  const nameIndex = Array.isArray(activeColumns) ? activeColumns.indexOf("name") : -1;
  if (nameIndex < 0 || !Array.isArray(activeRows)) {
    self.postMessage({ type: "results", requestId, error: "The search dataset is not loaded." });
    return;
  }

  const needle = normalize(query);
  const matches = [];
  if (needle) {
    for (const row of activeRows) {
      if (normalize(row[nameIndex]).includes(needle)) matches.push(row);
    }
  }
  self.postMessage({ type: "results", requestId, matches });
};
