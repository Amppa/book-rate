/**
 * Result Details Component for Step 3 Comparison Table
 * Renders collapsible metadata panel (<details>) dynamically for all valid metadata keys.
 */

import { getWorkExternalUrl, isSafeUrl } from './utils.js';

export const KNOWN_FIELD_ORDER = [
  "author",
  "translator",
  "publisher",
  "publish_date",
  "series",
  "language",
  "original_title",
  "edition_count",
  "isbn",
  "asin",
  "work_id"
];

export const FIELD_LABEL_MAP = {
  author: "作者:",
  translator: "譯者:",
  publisher: "出版社:",
  publish_date: "出版日期:",
  series: "叢書:",
  language: "語言:",
  original_title: "原作名:",
  edition_count: "版本數:",
  isbn: "ISBN:",
  asin: "ASIN:",
  work_id: "ID:"
};

// Export DETAIL_FIELD_DEFINITIONS for backward compatibility with existing tests
export const DETAIL_FIELD_DEFINITIONS = KNOWN_FIELD_ORDER.map((key) => ({
  key,
  label: FIELD_LABEL_MAP[key] || `${key}:`
}));

const INVALID_METADATA_VALUES = new Set(["", "none", "unknown", "null", "undefined", "n/a"]);
const INTERNAL_SKIP_KEYS = new Set([
  "url",
  "results",
  "crawler_status",
  "format",
  "binding",
  "pages",
  "price",
  "isbn10",
  "isbn13",
  "editions_count",
  "pub_year",
  "rate",
  "rating",
  "rating_count",
  "ratings_count",
  "average",
  "avg_rating",
  "score",
  "scores",
  "count",
  "votes"
]);

export const DETAILS_EXPANDED_TEXT = "details [-]";
export const DETAILS_COLLAPSED_TEXT = "details [+]";
export const ALL_DETAILS_EXPANDED_TEXT = "全部 details [-]";
export const ALL_DETAILS_COLLAPSED_TEXT = "全部 details [+]";

export const MAX_DETAIL_VALUE_LENGTH = 50;

/**
 * Truncates a detail field value to at most 50 characters with ellipsis.
 * @param {*} str
 * @returns {string}
 */
export function truncateDetailValue(str) {
  if (!str) return "";
  const s = String(str).trim();
  if (s.length > MAX_DETAIL_VALUE_LENGTH) {
    return s.slice(0, MAX_DETAIL_VALUE_LENGTH) + "...";
  }
  return s;
}

let _allDetailsBtn = null;
let _isBatchUpdating = false;

/**
 * Initializes and binds the global [全部 details] toggle button.
 * @param {HTMLButtonElement|null} btnEl
 */
export function initAllDetailsToggle(btnEl) {
  _allDetailsBtn = btnEl;
  if (!_allDetailsBtn) return;

  _allDetailsBtn.addEventListener("click", () => {
    const allDetails = document.querySelectorAll(".source-book-details");
    if (allDetails.length === 0) return;

    const hasClosed = Array.from(allDetails).some((d) => !d.open);
    const targetState = hasClosed;

    _isBatchUpdating = true;
    allDetails.forEach((d) => {
      d.open = targetState;
      const summary = d.querySelector(".source-details-summary");
      if (summary) {
        summary.textContent = targetState ? DETAILS_EXPANDED_TEXT : DETAILS_COLLAPSED_TEXT;
      }
    });
    _isBatchUpdating = false;

    syncAllDetailsButton();
  });

  window.addEventListener("bookrate:details-toggle", () => {
    if (!_isBatchUpdating) {
      syncAllDetailsButton();
    }
  });
}

/**
 * Synchronizes visibility and [+] / [-] text of the [全部 details] button based on current DOM state.
 */
export function syncAllDetailsButton() {
  if (!_allDetailsBtn) return;
  const tableWrap = document.querySelector(".table-wrap");
  const allDetails = document.querySelectorAll(".source-book-details");

  if (allDetails.length === 0 || (tableWrap && tableWrap.hidden)) {
    _allDetailsBtn.style.display = "none";
    return;
  }

  _allDetailsBtn.style.display = "inline-flex";
  const hasClosed = Array.from(allDetails).some((d) => !d.open);
  _allDetailsBtn.textContent = hasClosed ? ALL_DETAILS_COLLAPSED_TEXT : ALL_DETAILS_EXPANDED_TEXT;
  _allDetailsBtn.title = hasClosed ? "展開全部 Details" : "收合全部 Details";
}

/**
 * Checks whether a metadata field value is valid and displayable.
 * @param {*} val
 * @returns {boolean}
 */
export function isValidDetailValue(val) {
  if (val === null || val === undefined) return false;
  const str = String(val).trim();
  if (str === "") return false;
  return !INVALID_METADATA_VALUES.has(str.toLowerCase());
}

/**
 * Builds a collapsible book details DOM element.
 * Renders all valid metadata fields (known order first, then custom dynamic fields).
 * @param {Object|null} bookInfo - Flexible metadata dictionary
 * @returns {HTMLDetailsElement|null}
 */
export function buildBookDetailsElement(bookInfo) {
  if (!bookInfo || typeof bookInfo !== "object") return null;

  // 1. Gather all valid keys in preferred display order
  const validKeys = [];
  const seenKeys = new Set();

  for (const k of KNOWN_FIELD_ORDER) {
    if (k in bookInfo && isValidDetailValue(bookInfo[k])) {
      validKeys.push(k);
      seenKeys.add(k);
    }
  }

  for (const k of Object.keys(bookInfo)) {
    if (!seenKeys.has(k) && !INTERNAL_SKIP_KEYS.has(k) && isValidDetailValue(bookInfo[k])) {
      validKeys.push(k);
      seenKeys.add(k);
    }
  }

  if (validKeys.length === 0) return null;

  const details = document.createElement("details");
  details.className = "source-book-details";

  const summary = document.createElement("summary");
  summary.className = "source-details-summary";
  summary.textContent = DETAILS_COLLAPSED_TEXT;

  details.addEventListener("toggle", () => {
    summary.textContent = details.open ? DETAILS_EXPANDED_TEXT : DETAILS_COLLAPSED_TEXT;
    if (details.open) {
      content.animate(
        [
          { transform: "translateY(-4px)" },
          { transform: "translateY(0)" }
        ],
        { duration: 200, easing: "ease" }
      );
    }
    if (!_isBatchUpdating) {
      window.dispatchEvent(new CustomEvent("bookrate:details-toggle"));
    }
  });

  details.appendChild(summary);

  const content = document.createElement("div");
  content.className = "source-details-content";

  validKeys.forEach((key) => {
    const row = document.createElement("div");
    row.className = "source-detail-row";

    const label = document.createElement("span");
    label.className = "source-detail-label";
    label.textContent = FIELD_LABEL_MAP[key] || `${key.replace(/_/g, " ")}:`;

    const val = document.createElement("span");
    val.className = "source-detail-value";
    const rawVal = String(bookInfo[key]).trim();
    const displayVal = truncateDetailValue(rawVal);
    if (rawVal.length > MAX_DETAIL_VALUE_LENGTH) {
      val.title = rawVal;
    }

    if (key === "work_id") {
      const rawUrl = bookInfo.url || getWorkExternalUrl(rawVal);
      const url = isSafeUrl(rawUrl) ? rawUrl : null;
      if (url) {
        const link = document.createElement("a");
        link.href = url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.className = "source-detail-link";
        link.textContent = displayVal;
        val.appendChild(link);
      } else {
        val.textContent = displayVal;
      }
    } else {
      val.textContent = displayVal;
    }

    row.appendChild(label);
    row.appendChild(val);
    content.appendChild(row);
  });

  details.appendChild(content);
  return details;
}
