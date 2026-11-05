let activeColumns = null;
let activeRows = null;
const MAX_RETURNED_RESULTS = 100;

function normalize(value) {
  return String(value ?? "")
    .normalize("NFKC")
    .toLowerCase()
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
  let totalMatches = 0;
  if (needle) {
    for (const row of activeRows) {
      if (normalize(row[nameIndex]).includes(needle)) {
        totalMatches += 1;
        if (matches.length < MAX_RETURNED_RESULTS) matches.push(row);
      }
    }
  }
  self.postMessage({ type: "results", requestId, matches, totalMatches });
};
