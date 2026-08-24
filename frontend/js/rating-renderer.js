/**
 * Rating Renderer Component for Step 3 Comparison Table
 * Centralizes rating display state resolution, DOM building, status tags, and cell rendering.
 */

import { STRATEGY_LABEL_MAP } from './constants.js';
import { displayRate, displayCount } from './utils.js';
import { buildBookDetailsElement } from './result-details.js';

/**
 * Resolves display representation (rateText/rateHtml, countText, status, tagText) for a source rating.
 * @param {Object} itemData - Rating data item
 * @param {number} maxRate - Maximum rating scale (5 or 10)
 * @returns {Object} { rateText, rateHtml, countText, status, tagText, emptyTitle }
 */
export function resolveRatingDisplay(itemData, maxRate = 5) {
  if (!itemData || typeof itemData !== "object") {
    return {
      rateText: "無此書籍",
      countText: "-",
      status: "NO_MATCH"
    };
  }

  const hasScore = typeof itemData.average === "number" && itemData.average > 0;
  const status = itemData.status || (hasScore ? "MATCH" : (itemData.url ? "UNRATED" : "NO_MATCH"));
  const isNetworkError = status
    && !["MATCH", "CURL_MATCH", "UNRATED", "NO_MATCH", "NOT_FOUND", "QUOTA_EXCEEDED", "ERROR"].includes(status);

  if (itemData.quota_exceeded || status === "QUOTA_EXCEEDED") {
    return {
      rateHtml: '<span class="error">額度超限 (429)</span>',
      countText: "請設定 API Key",
      status: "QUOTA_EXCEEDED"
    };
  }
  if (status === "RATE_LIMITED" || status === "RATE_LIMIT") {
    return {
      rateHtml: '<span class="error">連線異常 (風控)</span>',
      countText: "請求過密或遭阻擋",
      status: "RATE_LIMITED"
    };
  }
  if (status === "ERROR") {
    return {
      rateHtml: '<span class="error">讀取錯誤</span>',
      countText: "請檢查主機連線",
      status: "ERROR"
    };
  }
  if (isNetworkError) {
    const shortStatus = status.length > 40 ? status.slice(0, 40) + "\u2026" : status;
    const friendlyCount = shortStatus.indexOf("Invalid API Key") !== -1
      ? "請檢查 API Key"
      : shortStatus;
    return {
      rateHtml: '<span class="error">連線異常</span>',
      countText: friendlyCount,
      status: shortStatus
    };
  }
  if (hasScore) {
    return {
      rateText: displayRate(itemData.average, itemData.count, maxRate),
      countText: displayCount(itemData.count),
      status: status || "MATCH"
    };
  }
  if (itemData.url || status === "UNRATED") {
    return {
      rateText: "暫無評分",
      countText: itemData.count ? displayCount(itemData.count) : "目前0評價",
      status: "UNRATED"
    };
  }
  // Strategy selected but no query executed (title/CJK/ISBN lists all empty)
  if (itemData.query === "") {
    return {
      rateText: "無清單輸入",
      countText: "-",
      status: "NO_MATCH",
      tagText: "NULL",
      emptyTitle: true
    };
  }
  return {
    rateText: "無此書籍",
    countText: "-",
    status: "NO_MATCH"
  };
}

/**
 * Builds a book title element (rendered as an external anchor if URL is present).
 * @param {string} title - Book title
 * @param {string|null} url - Book web link
 * @returns {HTMLElement|null}
 */
export function buildTitleElement(title, url) {
  if (!title) return null;
  const el = document.createElement(url ? "a" : "div");
  el.className = "source-book-title";
  el.textContent = title;
  if (url) {
    el.href = url;
    el.target = "_blank";
    el.rel = "noreferrer";
  }
  return el;
}

/**
 * Builds the strategy/status tooltip badge element.
 * @param {string} status - Rating status code
 * @param {Object} data - Rating data item
 * @param {string|null} tagText - Custom tag text
 * @returns {HTMLSpanElement}
 */
export function buildStatusTag(status, data, tagText) {
  const tag = document.createElement("span");
  const normStatusClass = (status || "").toLowerCase().replace(/[^a-z0-9_]/g, "-");
  tag.className = `search-status-tag status-${normStatusClass}`;
  const raw = tagText || status || "NO_MATCH";
  tag.textContent = raw;
  tag.dataset.strat = data?.strategy || "";
  tag.dataset.query = data?.query || "";
  const friendlyStrat = STRATEGY_LABEL_MAP[data?.strategy] || data?.strategy || "N/A";
  tag.title = `策略: ${friendlyStrat}, 查詢: ${data?.query || "N/A"}`;
  if (raw.length > 24) {
    tag.textContent = raw.slice(0, 24) + "\u2026";
    tag.title += ", 訊息: " + raw;
  }
  return tag;
}

/**
 * Standardized single result block renderer used by both single-cell and multi-result list flows.
 * @param {HTMLElement} container - Parent element (e.g. td or .multi-result-item)
 * @param {Object} result - Result data item
 * @param {Object} context - { maxRate, showTitle, titleBefore }
 */
export function renderRatingResult(container, result, context = {}) {
  const maxRate = context.maxRate || 5;
  const display = resolveRatingDisplay(result, maxRate);

  let titleLabel = result.title;
  if (!titleLabel || titleLabel === "Unknown") {
    titleLabel = (typeof result.query === "string" && result.query) ? result.query : "";
  }

  // 1. Build title if applicable
  if (titleLabel && !display.emptyTitle && context.showTitle !== false) {
    const titleEl = buildTitleElement(titleLabel, result.url);
    if (titleEl) {
      if (context.titleBefore && context.titleBefore.parentNode === container) {
        container.insertBefore(titleEl, context.titleBefore);
      } else {
        container.appendChild(titleEl);
      }
    }
  }

  // 2. Score and count display
  const strong = document.createElement("strong");
  strong.className = context.rateClass || "rating-score";
  if (display.rateHtml) {
    strong.innerHTML = display.rateHtml;
  } else {
    strong.textContent = display.rateText;
  }

  const small = document.createElement("small");
  small.className = context.countClass || "rating-count";
  small.textContent = display.countText;

  // 3. Status badge
  const badge = buildStatusTag(display.status, result, display.tagText);

  container.appendChild(strong);
  container.appendChild(small);
  container.appendChild(badge);

  // 4. Collapsible metadata details
  const detailsEl = buildBookDetailsElement(result.book_info);
  if (detailsEl) {
    container.appendChild(detailsEl);
  }
}

/**
 * Renders rating data into a single source column of a work row.
 * Supports both named object signature ({ sourceId, prefix, data, maxRate })
 * and positional backward-compatible signature (row, prefix, data, maxRate).
 * @param {HTMLTableRowElement} row
 * @param {Object|string} optionsOrPrefix
 * @param {Object} [legacyData]
 * @param {number} [legacyMaxRate]
 */
export function renderSourceCell(row, optionsOrPrefix, legacyData, legacyMaxRate = 5) {
  let prefix;
  let data;
  let maxRate = 5;

  if (typeof optionsOrPrefix === "object" && optionsOrPrefix !== null) {
    prefix = optionsOrPrefix.prefix;
    data = optionsOrPrefix.data;
    maxRate = optionsOrPrefix.maxRate || 5;
  } else {
    prefix = optionsOrPrefix;
    data = legacyData;
    maxRate = legacyMaxRate || 5;
  }

  if (!row || !prefix || !data || typeof data !== "object") return;

  const rateEl = row.querySelector(`.${prefix}-rate`);
  const countEl = row.querySelector(`.${prefix}-count`);
  if (!rateEl || !countEl) return;

  rateEl.replaceChildren();
  countEl.replaceChildren();

  const cell = rateEl.closest("td");
  if (cell) {
    const existingTitle = cell.querySelector(".source-book-title");
    if (existingTitle) existingTitle.remove();
    const existingTag = cell.querySelector(".search-status-tag");
    if (existingTag) existingTag.remove();
    const existingDetails = cell.querySelector(".source-book-details");
    if (existingDetails) existingDetails.remove();
  }

  // Multi-result list (Strategy 4/5)
  if (Array.isArray(data.results) && data.results.length > 0) {
    const listContainer = document.createElement("div");
    listContainer.className = "multi-result-list";

    data.results.forEach((res) => {
      const item = document.createElement("div");
      item.className = "multi-result-item";
      item.title = `查詢: ${res.query || "N/A"}\n書名: ${res.title || "N/A"}`;
      renderRatingResult(item, res, { maxRate, showTitle: true });
      listContainer.appendChild(item);
    });

    rateEl.appendChild(listContainer);
    countEl.replaceChildren();
    return;
  }

  // Single result
  const display = resolveRatingDisplay(data, maxRate);
  let titleLabel = data.title;
  if (!titleLabel || titleLabel === "Unknown") {
    titleLabel = (typeof data.query === "string" && data.query) ? data.query : "";
  }

  if (titleLabel && !display.emptyTitle && cell) {
    const titleEl = buildTitleElement(titleLabel, data.url);
    if (titleEl) cell.insertBefore(titleEl, rateEl);
  }

  if (display.rateHtml) {
    rateEl.innerHTML = display.rateHtml;
  } else {
    rateEl.textContent = display.rateText;
  }
  countEl.textContent = display.countText;

  const tag = buildStatusTag(display.status, data, display.tagText);
  if (cell) cell.appendChild(tag);

  const detailsEl = buildBookDetailsElement(data.book_info);
  if (detailsEl && cell) cell.appendChild(detailsEl);
}
