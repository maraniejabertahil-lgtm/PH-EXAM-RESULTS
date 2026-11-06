import { normalizeSearchText } from "./storage.mjs";

export function searchRecords(rows, query, limit = 100) {
  const normalizedQuery = normalizeSearchText(query);
  if (normalizedQuery.length < 2) return { results: [], total: 0, truncated: false };
  const results = [];
  let total = 0;
  for (const row of rows) {
    if (normalizeSearchText(row[0]).includes(normalizedQuery)) {
      total += 1;
      if (results.length < limit) {
        results.push({
          name: row[0],
          rating: row[1],
          region: row[2],
          sequence_number: row[3],
        });
      }
    }
  }
  return { results, total, truncated: total > results.length };
}

if (typeof self !== "undefined" && typeof self.postMessage === "function") {
  self.onmessage = ({ data }) => {
    const { requestId, rows, query, limit } = data || {};
    try {
      self.postMessage({ requestId, ...searchRecords(rows || [], query || "", limit) });
    } catch {
      self.postMessage({ requestId, error: "Search could not be completed." });
    }
  };
}
