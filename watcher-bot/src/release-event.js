// Versioned PRC release-event contract. Ambiguous metadata is a hard stop.
const EXAMS = [
  { code: "LEPT", re: /\b(?:LEPT|licensure examination for professional teachers)\b/i },
  { code: "CPALE", re: /\b(?:CPALE|CPA|certified public accountants?)\b/i },
  { code: "NLE", re: /\b(?:nurse licensure|nursing)\b/i },
  { code: "CLE", re: /\b(?:criminology|criminologist)\b/i },
  { code: "ELE", re: /\b(?:engineers? licensure|engineering licensure)\b/i },
  { code: "VET", re: /\b(?:veterinarians?|veterinary medicine)\b/i },
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

function inferExamIdentity(title) {
  const known = EXAMS.filter((exam) => exam.re.test(title));
  if (known.length === 1) return { code: known[0].code, known: true };
  if (known.length > 1) return null;
  const normalized = title.replace(/^\s*(?:(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+)?20\d{2}\s+/i, '').replace(/\s+results?\b[\s\S]*$/i, '').replace(/\s+released\b[\s\S]*$/i, '').replace(/\s+announced\b[\s\S]*$/i, '').trim();
  const match = normalized.match(/^(.{2,100}?\b(?:computer-based\s+)?(?:licensure\s+)?examination)\b/i);
  if (!match) return null;
  const candidate = match[1].replace(/\s+/g, ' ').trim();
  if (/\band\b|&|\//i.test(candidate)) return null;
  const words = candidate.replace(/\b(?:computer-based|licensure|examination)\b/gi, ' ').replace(/[^\p{L}\p{N}]+/gu, ' ').trim().split(/\s+/).filter(Boolean);
  if (!words.length) return null;
  const slug = words.join('-').toUpperCase().replace(/[^A-Z0-9-]/g, '').slice(0, 26).replace(/-+$/g, '');
  return slug.length >= 2 ? { code: `EXAM-${slug}`, known: false, candidate } : null;
}
function cleanContentUrls(links, articleUrl) {
  const seen = new Set();
  const out = [];
  for (const l of links) {
    let u;
    try { u = new URL(l.url, articleUrl); } catch { continue; }
    if (u.protocol !== "https:") continue;
    u.hash = "";
    if (u.href === new URL(articleUrl).href) continue;
    const isDrive = u.hostname === "drive.google.com" && /^\/file\/d\/[^/]+\/view$/.test(u.pathname);
    const isPdf = u.pathname.toLowerCase().endsWith(".pdf");
    if (!isDrive && !isPdf) continue;
    if (seen.has(u.href)) continue;
    seen.add(u.href);
    out.push({
      format: isPdf ? "pdf" : l.format,
      url: u.href,
      label: typeof l.label === "string" ? l.label.replace(/\s+/g, " ").trim() : ""
    });
  }
  return out;
}

export function buildReleaseEvent(source, article, options = {}) {
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
  const identity = inferExamIdentity(title);
  if (!identity) return review("exam name is ambiguous or could not be safely identified");
  const codes = [identity.code];

  const years = [...new Set(title.match(/\b20\d{2}\b/g) || [])];
  if (years.length !== 1) return review(`exam year ambiguous or missing: [${years.join(",")}]`);

  const titleLevels = Object.entries(LEVELS)
    .filter(([, pattern]) => pattern.test(title))
    .map(([level]) => level);
  const requestedLevel = options.resultLevel || (titleLevels.length === 1 ? titleLevels[0] : null);
  if (codes[0] === "LEPT" && !["elementary", "secondary"].includes(requestedLevel)) {
    return review("LEPT result level is ambiguous; select the Elementary or Secondary roster");
  }
  if (codes[0] === "LEPT" && titleLevels.length === 1 && titleLevels[0] !== requestedLevel) {
    return review("requested LEPT result level conflicts with the official article title");
  }

  let links = cleanContentUrls(Array.isArray(article.links) ? article.links : [], articleUrl.href)
    .map((link) => ({ ...link, format: guessFormat(link.url) }))
    .filter((link) => link.format);
  if (!links.length) return review("no supported official linked content found");
  const rosterLinks = links.filter((link) =>
    /\b(?:list|roll)\s+of\s+successful\s+examinees\b/i.test(link.label) ||
    /\bsuccessful\s+examinees\s+(?:list|roll)\b/i.test(link.label)
  );
  if (codes[0] === "LEPT") {
    links = rosterLinks.filter((link) => new RegExp("\\b" + requestedLevel + "\\b", "i").test(link.label));
    if (links.length !== 1) {
      return review("expected exactly one official " + requestedLevel + " successful-examinee roster link; found " + links.length);
    }
  } else if (links.length > 1) {
    if (rosterLinks.length !== 1) {
      return review("multiple official content links and no unique labelled successful-examinee list");
    }
    links = rosterLinks;
  }
  if (!links.length) return review("no supported official linked content found");
  links = links.map(({ url, format }) => ({ url, format }));
  const countPatterns = codes[0] === "LEPT"
    ? [new RegExp("\\b([\\d,]{3,})\\s+" + requestedLevel + "\\s+teachers?\\s+out of\\b", "i")]
    : [
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
  if (codes[0] === "LEPT" && announcedCount === null) {
    return review("official article does not state an announced passer count for " + requestedLevel);
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
      result_level: codes[0] === "LEPT" ? requestedLevel : (titleLevels[0] || null),
      list_type: "successful_examinees",
      announced_count: announcedCount,
      content_urls: links,
      detected_at: new Date().toISOString(),
    },
  };
}
