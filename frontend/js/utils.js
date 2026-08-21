import { OPEN_LIBRARY_BASE_URL } from './constants.js';
import { toSimplified } from './t2s.js';

export function fetchJson(url) {
  return fetch(url).then(async (response) => {
    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const body = await response.json();
        if (body && body.detail) detail = body.detail;
      } catch (_) {}
      const err = new Error(detail);
      err.status = response.status;
      throw err;
    }
    return response.json();
  });
}

export function getSourceSearchUrl(sourceId, query) {
  const q = encodeURIComponent(query || "");
  switch (sourceId) {
    case "amazon":
      return `https://www.amazon.com/s?k=${q}&i=stripbooks`;
    case "amazon_jp":
      return `https://www.amazon.co.jp/s?k=${q}&i=stripbooks`;
    case "douban":
    case "douban_api":
      return `https://search.douban.com/book/subject_search?search_text=${q}`;
    case "goodreads":
      return `https://www.goodreads.com/search?q=${q}`;
    case "storygraph":
      return `https://app.thestorygraph.com/browse?search_term=${q}`;
    case "books_tw":
      return `https://search.books.com.tw/search/query/key/${q}`;
    case "readmoo":
      return `https://readmoo.com/search/keyword?q=${q}`;
    case "google_books":
      return `https://books.google.com/books?q=${q}`;
    case "google_play":
      return `https://play.google.com/store/search?q=${q}&c=books`;
    case "open_library":
    default:
      return `https://openlibrary.org/search?q=${q}`;
  }
}

export function displayRate(average, count, maxScore = 5) {
  return Number(average) > 0
    ? `${Number(average).toFixed(1)} / ${maxScore}`
    : "暫無評分";
}

export function formatCompact(n) {
  return new Intl.NumberFormat("en", {
    notation: "compact",
    maximumFractionDigits: 1
  }).format(n);
}

export function displayCount(count) {
  const cVal = Number(count);
  if (count !== null && count !== undefined && !isNaN(cVal) && cVal > 0) {
    let fire = "";

    if (cVal > 2000) {
      fire = " 🔥🔥🔥🔥";
    } else if (cVal > 1000) {
      fire = " 🔥🔥🔥";
    } else if (cVal > 500) {
      fire = " 🔥🔥";
    } else if (cVal > 100) {
      fire = " 🔥";
    }
    return `${formatCompact(cVal)} 人評價${fire}`;
  }
  return "連結";
}

export function getWorkExternalUrl(key) {
  if (!key) return null;
  if (key.startsWith("/works/")) return `${OPEN_LIBRARY_BASE_URL}${key}`;
  if (key.startsWith("gb:")) return `https://books.google.com/books?id=${key.slice(3)}`;
  if (key.startsWith("gr:")) {
    const rawId = key.slice(3);
    const bookIndex = rawId.indexOf("/book/");
    if (bookIndex !== -1) {
      const bookSlug = rawId.substring(bookIndex + 6);
      return `https://www.goodreads.com/book/show/${bookSlug}`;
    }
    if (rawId.startsWith("work/")) {
      return `https://www.goodreads.com/work/editions/${rawId.slice(5)}`;
    } else if (rawId.startsWith("book/")) {
      return `https://www.goodreads.com/book/show/${rawId.slice(5)}`;
    }
    return `https://www.goodreads.com/book/show/${rawId}`;
  }
  if (key.startsWith("db:")) return `https://book.douban.com/subject/${key.slice(3)}/`;
  if (key.startsWith("dbapi:")) return `https://book.douban.com/subject/${key.slice(6)}/`;
  if (key.startsWith("am:")) return `https://www.amazon.com/dp/${key.slice(3)}`;
  if (key.startsWith("amjp:")) return `https://www.amazon.co.jp/dp/${key.slice(5)}`;
  if (key.startsWith("sg:")) return `https://app.thestorygraph.com/books/${key.slice(3)}`;
  if (key.startsWith("rm:")) return `https://readmoo.com/book/${key.slice(3)}`;
  if (key.startsWith("bk:")) return `https://www.books.com.tw/products/${key.slice(3)}`;
  if (key.startsWith("play:")) return `https://play.google.com/store/books/details?id=${key.slice(5)}`;
  return null;
}

export function getSourceDisplayName(key) {
  const names = {
    open_library: "Open Library",
    ol: "Open Library",
    google_books: "Google Books",
    gb: "Google Books",
    google_play: "Google Play",
    gp: "Google Play",
    google: "Google Books",
    goodreads: "Goodreads",
    gr: "Goodreads",
    douban: "豆瓣",
    db: "豆瓣",
    douban_api: "豆瓣 API",
    dbapi: "豆瓣 API",
    amazon: "Amazon",
    am: "Amazon",
    amazon_jp: "Amazon JP",
    amjp: "Amazon JP",
    storygraph: "StoryGraph",
    sg: "StoryGraph",
    readmoo: "Readmoo",
    rm: "Readmoo",
    books_tw: "博客來",
    bk: "博客來"
  };

  return names[key] || key;
}



const BRACKETS = [
  ['【', '】'],
  ['\\[', '\\]'],
  ['\\(', '\\)'],
  ['（', '）']
];

const bracketPattern = new RegExp(
  BRACKETS.map(([open, close]) => `${open}[^${open}${close}]*${close}`).join('|'),
  'g'
);

/**
 * Remove parenthesis and bracket content from a string.
 * @param {string} str
 * @returns {string}
 */
export function removeBrackets(str) {
  if (!str) return "";
  let res = str;
  let prev;
  do {
    prev = res;
    res = res.replace(bracketPattern, '');
  } while (res !== prev);
  return res.replace(/\s+/g, ' ').trim();
}

/**
 * Checks if a string contains CJK characters.
 * @param {string} str
 * @returns {boolean}
 */
export function hasCjk(str) {
  return /[\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff\uac00-\ud7a3]/.test(str);
}

/**
 * 基礎清理：移除括號內容並轉換為小寫
 * @param {string} str
 * @returns {string}
 */
function baseNormalize(str) {
  if (!str) return '';
  return removeBrackets(str).toLowerCase();
}

/**
 * Normalizes CJK string: removes brackets, punctuation, spaces, converts Trad-to-Simp, and lowercases.
 * @param {string} str
 * @returns {string}
 */
function normalizeCjk(str) {
  const base = baseNormalize(str);
  const simplified = toSimplified(base);
  // \p{P}: 所有標點符號, \p{S}: 所有數學與貨幣符號, \s: 空白
  return simplified.replace(/[\p{P}\p{S}\s]+/gu, '');
}

/**
 * Normalizes Latin string: removes brackets, punctuation, handles single spaces, and lowercases.
 * @param {string} str
 * @returns {string}
 */
function normalizeLatin(str) {
  const base = baseNormalize(str);
  const cleaned = base.replace(/[\p{P}\p{S}\s]/gu, (match) => {
    if ("'\"’”‘’“”".includes(match)) {
      return '';
    }
    return ' ';
  });
  return cleaned.replace(/\s+/g, ' ').trim();
}

/**
 * Generates character n-grams from a string.
 * @param {string} str
 * @param {number[]} sizes
 * @returns {Set<string>}
 */
function getNgrams(str, sizes) {
  const ngrams = new Set();
  for (const size of sizes) {
    if (str.length >= size) {
      for (let i = 0; i <= str.length - size; i++) {
        ngrams.add(str.substring(i, i + size));
      }
    }
  }
  return ngrams;
}

/**
 * Calculates Dice coefficient similarity between two n-gram sets.
 * @param {Set<string>} ngramsA
 * @param {Set<string>} ngramsB
 * @returns {number}
 */
function ngramSimilarity(ngramsA, ngramsB) {
  if (ngramsA.size === 0 && ngramsB.size === 0) return 0;
  let intersect = 0;
  for (const item of ngramsA) {
    if (ngramsB.has(item)) {
      intersect++;
    }
  }
  return (2 * intersect) / (ngramsA.size + ngramsB.size);
}

/**
 * Calculates normalized n-gram similarity based on CJK/Latin settings.
 * @param {string} strA
 * @param {string} strB
 * @param {boolean} isCjk
 * @returns {number}
 */
function calculateNgramSim(strA, strB, isCjk) {
  const minSize = isCjk ? 2 : 3;
  let sizes = isCjk ? [2, 3] : [3, 4];
  if (strA.length < minSize || strB.length < minSize) {
    sizes = isCjk ? [1] : [1, 2];
  }
  const ngramsA = getNgrams(strA, sizes);
  const ngramsB = getNgrams(strB, sizes);
  return ngramSimilarity(ngramsA, ngramsB);
}

/**
 * Calculates Levenshtein edit distance between two strings.
 * @param {string} str1
 * @param {string} str2
 * @returns {number}
 */
export function levenshteinDistance(str1, str2) {
  const m = str1.length;
  const n = str2.length;
  let prevRow = new Int32Array(n + 1);
  let currRow = new Int32Array(n + 1);
  for (let j = 0; j <= n; j++) prevRow[j] = j;
  for (let i = 1; i <= m; i++) {
    currRow[0] = i;
    for (let j = 1; j <= n; j++) {
      const cost = str1[i - 1] === str2[j - 1] ? 0 : 1;
      currRow[j] = Math.min(
        prevRow[j] + 1, // deletion
        currRow[j - 1] + 1, // insertion
        prevRow[j - 1] + cost // substitution
      );
    }
    const temp = prevRow;
    prevRow = currRow;
    currRow = temp;
  }
  return prevRow[n];
}

/**
 * Calculates the length of the Longest Common Subsequence between two strings.
 * @param {string} str1
 * @param {string} str2
 * @returns {number}
 */
export function lcsLength(str1, str2) {
  const m = str1.length;
  const n = str2.length;
  if (m === 0 || n === 0) return 0;
  const dp = Array.from({ length: m + 1 }, () => new Int32Array(n + 1));
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (str1[i - 1] === str2[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1] + 1;
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
      }
    }
  }
  return dp[m][n];
}

/**
 * Calculates combined weighted similarity between two book titles.
 * @param {string} titleA
 * @param {string} titleB
 * @returns {number}
 */
export function calculateSingleSimilarity(titleA, titleB) {
  if (!titleA || !titleB) return 0;

  const isCjkA = hasCjk(titleA);
  const isCjkB = hasCjk(titleB);

  // Cross-lingual matches are not allowed (0 score)
  if (isCjkA !== isCjkB) return 0;

  let normA, normB;
  if (isCjkA) {
    normA = normalizeCjk(titleA);
    normB = normalizeCjk(titleB);
  } else {
    normA = normalizeLatin(titleA);
    normB = normalizeLatin(titleB);
  }

  if (!normA || !normB) return 0;
  if (normA === normB) return 1;

  // 1. Character n-gram similarity (50%)
  const ngramSim = calculateNgramSim(normA, normB, isCjkA);

  // 2. Levenshtein edit distance similarity (20%)
  const dist = levenshteinDistance(normA, normB);
  const editSim = 1 - dist / Math.max(normA.length, normB.length);

  // 3. Containment similarity via LCS (30%)
  const lcs = lcsLength(normA, normB);
  const containSim = lcs / Math.min(normA.length, normB.length);

  // Weighted score
  return 0.5 * ngramSim + 0.3 * containSim + 0.2 * editSim;
}

/**
 * Calculates the maximum similarity score (0-100) between a source title
 * and a list of target reference titles.
 * @param {string} sourceTitle
 * @param {string[]} refTitles
 * @returns {number}
 */
export function calculateTitleConfidence(sourceTitle, refTitles) {
  if (!sourceTitle || !refTitles || refTitles.length === 0) return 0;
  let maxSim = 0;
  for (const ref of refTitles) {
    const sim = calculateSingleSimilarity(sourceTitle, ref);
    if (sim > maxSim) {
      maxSim = sim;
    }
  }
  return Math.round(maxSim * 100);
}

/**
 * Retrieves or creates a tracked asynchronous task.
 * Encapsulates status tracking (loading, success, error) and wraps the original promise.
 *
 * @param {Object} container - Object/container holding the task
 * @param {string} key - Key of the task within the container
 * @param {function(): Promise} promiseFactory - Function returning the promise to execute if task doesn't exist
 * @returns {{status: string, data: *, error: *, promise: Promise}} Tracked task object
 */
export function getOrCreateTask(container, key, promiseFactory) {
  if (!container[key]) {
    const task = {
      status: 'loading',
      data: null,
      error: null,
      promise: null
    };
    container[key] = task;
    task.promise = promiseFactory()
      .then((data) => {
        task.status = 'success';
        task.data = data;
        return data;
      })
      .catch((err) => {
        task.status = 'error';
        task.error = err.message || String(err);
        throw err;
      });
  }
  return container[key];
}

