import { OPEN_LIBRARY_BASE_URL } from './constants.js';

export function fetchJson(url) {
  return fetch(url).then(async (response) => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  });
}

export function displayRate(average, count, maxScore = 5) {
  return Number(count) > 0 && Number(average) > 0
    ? `${Number(average).toFixed(2)} / ${maxScore}`
    : "暫無評分";
}

export function formatCompact(n) {
  return new Intl.NumberFormat("en", {
    notation: "compact",
    maximumFractionDigits: 1
  }).format(n);
}

export function displayCount(count) {
  return Number(count) > 0
    ? `${formatCompact(Number(count))} 人評價`
    : "NULL";
}

export function getWorkExternalUrl(key) {
  if (!key) return null;
  if (key.startsWith("/works/")) return `${OPEN_LIBRARY_BASE_URL}${key}`;
  if (key.startsWith("gb:")) return `https://books.google.com/books?id=${key.slice(3)}`;
  if (key.startsWith("gr:")) return `https://www.goodreads.com/book/show/${key.slice(3)}`;
  if (key.startsWith("db:")) return `https://book.douban.com/subject/${key.slice(3)}/`;
  if (key.startsWith("amjp:")) return `https://www.amazon.co.jp/dp/${key.slice(5)}`;
  if (key.startsWith("sg:")) return `https://app.thestorygraph.com/books/${key.slice(3)}`;
  if (key.startsWith("rm:")) return `https://readmoo.com/book/${key.slice(3)}`;
  return null;
}

export function getSourceDisplayName(key) {
  const names = {
    open_library: "Open Library",
    ol: "Open Library",
    google_books: "Google Books",
    gb: "Google Books",
    google: "Google Books",
    goodreads: "Goodreads",
    gr: "Goodreads",
    douban: "豆瓣",
    db: "豆瓣",
    amazon: "Amazon",
    am: "Amazon",
    amazon_jp: "Amazon JP",
    amjp: "Amazon JP",
    storygraph: "StoryGraph",
    sg: "StoryGraph",
    readmoo: "Readmoo",
    rm: "Readmoo"
  };
  return names[key] || key;
}
