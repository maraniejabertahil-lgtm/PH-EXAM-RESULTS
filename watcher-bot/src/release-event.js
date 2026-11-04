// Versioned PRC release-event contract. Ambiguous metadata is a hard stop.
const EXAMS = [
  { code: "LEPT", re: /\b(?:LEPT|licensure examination for professional teachers)\b/i },
  { code: "CPALE", re: /\b(?:CPALE|CPA|certified public accountants?)\b/i },
  { code: "NLE", re: /\b(?:nurse licensure|nursing)\b/i },
  { code: "CLE", re: /\b(?:criminology|criminologist)\b/i },
  { code: "ELE", re: /\b(?:engineers? licensure|engineering licensure)\b/i },
];
const LEVELS = {
  elementary: /\belementary\b/i,
  secondary: /\bsecondary\b/i,
};
const ALLOWED_LINK_HOSTS = new Set([
  "www.prc.gov.ph", "prc.gov.ph", "drive.google.com", "docs.google.com",
]);
const review = (reason) => ({ ok: false, reason });

function guessFormat(value) {
  let url;
  try { url = new URL(value); } catch { return null; }
  const host = url.hostname.toLowerCase();
  if (!ALLOWED_LINK_HOSTS.has(host)) return null;
  if (/\.pdf$/i.test(url.pathname) || (host === "drive.google.com" && /\/file\/d\//i.test(url.pathname))) return "pdf";
  if (/\.csv$/i.test(url.pathname)) return "csv";
  if (/\.json$/i.test(url.pathname)) return "json";
  if (host === "www.prc.gov.ph" || host === "prc.gov.ph") return "html";
  return null;
}

export function buildReleaseEvent(source, article) {
  if (!source || typeof source.id !== "string" || !article ||
      typeof article.title !== "string" || typeof article.url !== "string") {
    return review("source/article metadata is incomplete");
  }
  let articleUrl;
  try { articleUrl = new URL(article.url); } catch { return review("article URL is invalid"); }
  if (articleUrl.protocol !== "https:" || !["www.prc.gov.ph", "prc.gov.ph"].includes(articleUrl.hostname.toLowerCase()) ||
      articleUrl.username || articleUrl.password) {
    return review("article is not on an approved official PRC HTTPS host");
  }

  const title = article.title.trim();
  const text = typeof article.text === "string" ? article.text : "";
  const hay = `${title} ${text}`;
  const codes = EXAMS.filter((exam) => exam.re.test(title)).map((exam) => exam.code);
  if (codes.length !== 1) return review(`exam code ambiguous or missing: [${codes.join(",")}]`);

  const years = [...new Set(title.match(/\b20\d{2}\b/g) || [])];
  if (years.length !== 1) return review(`exam year ambiguous or missing: [${years.join(",")}]`);

  const levels = Object.entries(LEVELS)
    .filter(([, pattern]) => pattern.test(title))
    .map(([level]) => level);
  if (codes[0] === "LEPT" && levels.length !== 1) {
    return review("LEPT level ambiguous or missing in the article title");
  }

  const candidates = (Array.isArray(article.links) ? article.links : [])
    .filter((link) => link && typeof link.url === "string" && /^https:\/\//i.test(link.url))
    .map((link) => ({
      url: link.url,
      format: guessFormat(link.url),
      label: typeof link.label === "string" ? link.label.replace(/\s+/g, " ").trim() : ""
    }))
    .filter((link) => link.format);
  if (!candidates.length) return review("no supported official linked content found");

  // When an announcement links several documents, dispatch only the uniquely
  // labelled passer list. Topnotcher/ranking documents are never substitutes.
  const excludedLabel = /\b(?:top\s*10|top\s*ten|topnotchers?|highest\s+places?|top\s+places?)\b/i;
  const configuredPatterns = Array.isArray(source.successful_examinees_link_patterns)
    ? source.successful_examinees_link_patterns
        .filter((value) => typeof value === "string" && value.trim())
        .map((value) => value.trim().toLowerCase())
    : ["list of successful examinees", "list of passers", "successful examinees list"];
  let links = candidates;
  if (candidates.length > 1) {
    const matches = candidates.filter((link) =>
      link.label && !excludedLabel.test(link.label) &&
      configuredPatterns.some((pattern) => link.label.toLowerCase().includes(pattern))
    );
    if (matches.length !== 1) {
      return review("multiple linked documents require one uniquely labelled successful-examinees list");
    }
    links = matches;
  }

  const countPatterns = [
    /\b([\d,]{3,})\s+(?:(?:elementary|secondary)\s+)?(?:teachers?\s+)?(?:out of|successfully passed|passed)\b/i,
    /\b([\d,]{3,})\s+(?:successful examinees|passers|examinees)\b/i,
  ];
  let announcedCount = null;
  for (const pattern of countPatterns) {
    const match = hay.match(pattern);
    if (match) {
      const parsed = Number(match[1].replace(/,/g, ""));
      if (Number.isSafeInteger(parsed) && parsed > 0) {
        announcedCount = parsed;
        break;
      }
    }
  }

  return {
    ok: true,
    event: {
      schema_version: "1",
      source_id: source.id,
      article_url: articleUrl.href,
      exam_code: codes[0],
      exam_title: title,
      exam_year: Number(years[0]),
      exam_date: null,
      result_level: levels[0] || null,
      list_type: "successful_examinees",
      announced_count: announcedCount,
      content_urls: links,
      detected_at: new Date().toISOString(),
    },
  };
}
