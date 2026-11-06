function isHttpsUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password;
  } catch {
    return false;
  }
}

function validSourceUrls(value) {
  const article = new URL(value.official_article_url);
  const content = new URL(value.official_content_url);
  const preview = new URL(value.public_preview_url);
  return (article.hostname === "prc.gov.ph" || article.hostname.endsWith(".prc.gov.ph"))
    && content.hostname === "drive.google.com"
    && preview.hostname === "drive.google.com"
    && content.pathname.endsWith("/view")
    && preview.pathname === `${content.pathname.slice(0, content.pathname.lastIndexOf("/"))}/preview`;
}

function bytesToHex(bytes) {
  return [...new Uint8Array(bytes)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function sha256(bytes) {
  return bytesToHex(await crypto.subtle.digest("SHA-256", bytes));
}

export async function validateReviewBundle(value) {
  if (!value || value.schema_version !== 1 || typeof value.authority !== "string"
      || typeof value.exam !== "string" || !Number.isInteger(value.year)
      || !Number.isSafeInteger(value.announced_count) || !Array.isArray(value.records)
      || value.record_count !== value.records.length || value.record_count !== value.announced_count
      || !/^[a-f0-9]{64}$/.test(value.candidate_sha256)
      || !/^[a-f0-9]{64}$/.test(value.capture_manifest_sha256)
      || !["official_article_url", "official_content_url", "public_preview_url"].every((key) => isHttpsUrl(value[key]))
      || !validSourceUrls(value)
      || !Array.isArray(value.evidence) || value.evidence.length === 0) {
    throw new Error("Review bundle metadata is incomplete or invalid.");
  }
  if (value.records.some((record) => !record || typeof record.name !== "string" || !record.name.trim()
      || typeof record.sequence_number !== "string" || !/^[0-9]+$/.test(record.sequence_number))) {
    throw new Error("Review bundle contains an invalid name/sequence record.");
  }
  if (new Set(value.records.map((record) => record.sequence_number)).size !== value.records.length) {
    throw new Error("Review bundle contains duplicate sequence numbers.");
  }
  const canonicalRecords = value.records.map((record) => ({
    name: record.name,
    sequence_number: record.sequence_number,
  }));
  if (await sha256(new TextEncoder().encode(JSON.stringify(canonicalRecords))) !== value.candidate_sha256) {
    throw new Error("Review bundle record fingerprint does not match its records.");
  }
  const coveredSequences = new Set();
  for (const item of value.evidence) {
    const sequences = Array.isArray(item?.sequence_numbers)
      ? item.sequence_numbers
      : [item?.sequence_number];
    if (!item || item.viewer_text_confirmed !== true
        || sequences.length === 0
        || new Set(sequences).size !== sequences.length
        || sequences.some((sequence) => typeof sequence !== "string"
          || !value.records.some((record) => record.sequence_number === sequence)
          || coveredSequences.has(sequence))
        || typeof item.expected_visible_text !== "string"
        || !item.expected_visible_text.trim()
        || !/^[a-f0-9]{64}$/.test(item.sha256)
        || typeof item.image_data !== "string"
        || !/^data:image\/(?:png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}$/.test(item.image_data)) {
      throw new Error("Review bundle contains invalid visual evidence.");
    }
    const [, mime, encoded] = item.image_data.match(/^data:(image\/(?:png|jpeg|webp));base64,(.+)$/);
    const bytes = Uint8Array.from(atob(encoded), (character) => character.charCodeAt(0));
    if (await sha256(bytes) !== item.sha256 || !mime.startsWith("image/")) {
      throw new Error("Visual evidence integrity check failed.");
    }
    for (const sequence of sequences) coveredSequences.add(sequence);
  }
  if (coveredSequences.size !== value.records.length) {
    throw new Error("Visual evidence does not cover every candidate record.");
  }
  return value;
}
