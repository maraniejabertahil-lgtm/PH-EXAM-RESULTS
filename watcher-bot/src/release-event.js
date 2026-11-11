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
const LEVEL_NAMES = ["elementary", "secondary"];

function findLevelAnnouncedCount(text, level) {
  if (!LEVEL_NAMES.includes(level)) return null;
  const patterns = [
    new RegExp("(\\\\d[\\\\d,]{2,})\\\\s+" + level + "\\\\b(?:\\\\s+[a-z]{2,18}){0,3}\\\\s+(?:out of|passed|passers|successful examinees|examinees|candidates)\\\\b", "i"),
    new RegExp("\\\\b" + level + "\\\\b[^\\\\d]{0,40}(\\\\d[\\\\d,]{2,})\\\\s+(?:passers|successful examinees|examinees|candidates|teachers)\\\\b", "i"),
    new RegExp("(\\\\d[\\\\d,]{2,})\\\\s+(?:passers|successful examinees|examinees|candidates)\\\\s+(?:for|in)\\\\s+\\\\b" + level + "\\\\b", "i")
  ];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (!match) continue;
    const count = Number(match[1].replace(/,/g, ""));
    if (Number.isSafeInteger(count) && count > 0) return count;
  }
  return null;
}


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
  if (requestedLevel && !LEVEL_NAMES.includes(requestedLevel)) {
    return review("unsupported result level");
  }

  let links = cleanContentUrls(Array.isArray(article.links) ? article.links : [], articleUrl.href)
    .map((link) => ({ ...link, format: guessFormat(link.url) }))
    .filter((link) => link.format);
  if (options.contentUrl) {
    links = links.filter((link) => link.url === options.contentUrl);
    if (links.length !== 1) return review("selected official passer-list attachment was not found exactly once");
  }
  if (!links.length) return review("no supported official linked content found");
  const rosterLinks = links.filter((link) =>
    /\b(?:list|roll)\s+of\s+successful\s+examinees\b/i.test(link.label) ||
    /\bsuccessful\s+examinees\s+(?:list|roll)\b/i.test(link.label)
  );
  if (codes[0] === "LEPT") {
    const levelLabelLinks = rosterLinks.filter((link) => new RegExp("\\b" + requestedLevel + "\\b", "i").test(link.label));
    if (levelLabelLinks.length > 0) {
      links = levelLabelLinks;
    } else if (titleLevels.length === 1 && rosterLinks.length === 1) {
      // Older PRC articles put the level in the title and use a generic roster label.
      links = rosterLinks;
    } else {
      links = [];
    }
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

  let announcedCount = Number.isSafeInteger(options.announcedCount) && options.announcedCount > 0
    ? options.announcedCount
    : null;
  if (announcedCount === null && requestedLevel) {
    announcedCount = findLevelAnnouncedCount(hay, requestedLevel);
  }
  if (announcedCount === null && codes[0] !== "LEPT") {
    const countPatterns = [
      /\\b([\\d,]{3,})\\s+(?:(?:elementary|secondary)\\s+)?(?:teachers?\\s+)?(?:out of|successfully passed|passed)\\b/i,
      /\\b([\\d,]{3,})\\s+(?:successful examinees|passers|examinees)\\b/i,
    ];
    for (const pattern of countPatterns) {
      const match = hay.match(pattern);
      if (!match) continue;
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
  if (options.requireAnnouncedCount === true && announcedCount === null) {
    return review("official article does not state a separate announced passer count for " + requestedLevel);
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
      result_level: requestedLevel || (titleLevels.length === 1 ? titleLevels[0] : null),
      list_type: "successful_examinees",
      announced_count: announcedCount,
      content_urls: links,
      detected_at: new Date().toISOString(),
    },
  };
}

// Classify every supported official attachment before deciding which links can
// become independent passer-list jobs. Non-passer attachments are recorded for
// visibility but are never sent to the roster extractor.
export function discoverArticleAttachments(article) {
  if (!article || typeof article.url !== "string" || !Array.isArray(article.links)) return [];
  let articleUrl;
  try { articleUrl = new URL(article.url); } catch { return []; }
  return cleanContentUrls(article.links, articleUrl.href)
    .map((link) => ({ ...link, format: guessFormat(link.url) }))
    .filter((link) => link.format)
    .map((link) => {
      const label = link.label || "";
      let classification = "other";
      if (/\bperformance of schools?\b/i.test(label)) {
        classification = "school_summary";
      } else if (/\btop\s*10\b|\bgarnered\b[\s\S]*\btop\b/i.test(label)) {
        classification = "topnotchers";
      } else if (/\bfull\s+text\b[\s\S]*\bofficial\s+result\b/i.test(label)) {
        classification = "press_release";
      } else if (
        /\b(?:list|roll)\s+of\s+successful\s+examinees\b/i.test(label) ||
        /\bsuccessful\s+examinees\s+(?:list|roll)\b/i.test(label)
      ) {
        classification = "main_passers_list";
      }
      const levels = Object.entries(LEVELS)
        .filter(([, pattern]) => pattern.test(label))
        .map(([level]) => level);
      return {
        url: link.url,
        format: link.format,
        label,
        classification,
        result_level: levels.length === 1 ? levels[0] : null,
        ambiguous_result_level: levels.length > 1,
      };
    });
}

// A PRC article may announce several LEPT cohorts. Build and validate every
// cohort first, then let the Watcher dispatch each one as its own event.
export function buildReleaseEvents(source, article) {
  const attachments = discoverArticleAttachments(article);
  const rosterLinks = attachments.filter((item) => item.classification === "main_passers_list");
  const isLept = typeof article?.title === "string" &&
    /\b(?:LEPT|licensure examination for professional teachers)\b/i.test(article.title);

  if (!isLept) {
    const built = buildReleaseEvent(source, article);
    return built.ok
      ? { ok: true, events: [built.event], attachments }
      : { ...built, events: [], attachments };
  }

  if (rosterLinks.length > 1) {
    const seenLevels = new Set();
    for (const item of rosterLinks) {
      if (!item.result_level || item.ambiguous_result_level) {
        return { ok: false, reason: "multiple LEPT passer lists were found but every list must have one clear supported level", events: [], attachments };
      }
      if (seenLevels.has(item.result_level)) {
        return { ok: false, reason: "multiple official LEPT passer lists claim the same " + item.result_level + " level", events: [], attachments };
      }
      seenLevels.add(item.result_level);
    }

    const events = [];
    for (const item of rosterLinks) {
      const built = buildReleaseEvent(source, article, { resultLevel: item.result_level });
      if (!built.ok) return { ...built, events: [], attachments };
      if (built.event.content_urls.length !== 1 || built.event.content_urls[0].url !== item.url) {
        return { ok: false, reason: "LEPT " + item.result_level + " event did not resolve to its exact labelled official roster link", events: [], attachments };
      }
      events.push(built.event);
    }
    return { ok: true, events, attachments };
  }

  const onlyRoster = rosterLinks[0];
  const requestedLevel = onlyRoster?.result_level || undefined;
  const built = buildReleaseEvent(source, article, requestedLevel ? { resultLevel: requestedLevel } : {});
  return built.ok
    ? { ok: true, events: [built.event], attachments }
    : { ...built, events: [], attachments };
}

