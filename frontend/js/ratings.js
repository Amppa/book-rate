/**
 * Ratings Comparison Table Orchestrator (Step 3)
 * Coordinates work selection, local rating caching, SSE streaming, and UI table updates.
 */

import { state } from './state.js';
import { STORAGE_KEYS, SOURCES, SOURCE_PREFIX } from './constants.js';
import { displayCount, getSourceSearchUrl } from './utils.js';
import { getRatingCache, setRatingCache } from './cache.js';
import { streamWorkDetailsPost } from './api.js';
import {
  getStep3Metadata,
  getSelectedStrategies,
  getActiveRateSourcesList,
  getSourceDefaultStrat,
  goToStep
} from './wizard.js';
import { renderSourceCell } from './rating-renderer.js';
import { initAllDetailsToggle, syncAllDetailsButton } from './result-details.js';

// Re-export renderSourceCell and syncAllDetailsButton for external module compatibility
export { renderSourceCell, syncAllDetailsButton, syncAllDetailsButton as updateFloatingDetailsBtn };

// DOM references injected at startup via initRatings()
let _resultBody, _step3Status, _tableWrap, _detailsHeading;

/**
 * Resolves source metadata, prefix, and maximum rating scale.
 * @param {string} sourceId - The engine identifier (e.g. 'douban', 'google_books')
 * @returns {Object} { sourceId, prefix, maxRate, label }
 */
export function getSourceDisplayConfig(sourceId) {
  const source = SOURCES.find((s) => s.id === sourceId);
  const prefix = SOURCE_PREFIX[sourceId] || sourceId;
  const maxRate = (prefix === "db" || prefix === "dbapi") ? 10 : 5;
  return {
    sourceId,
    prefix,
    maxRate,
    label: source ? source.label : sourceId
  };
}

/**
 * Inject DOM references that ratings.js needs.
 * Called once from app.js before any user interaction.
 */
export function initRatings({ resultBody, step3Status, tableWrap, detailsHeading }) {
  _resultBody = resultBody;
  _step3Status = step3Status;
  _tableWrap = tableWrap;
  _detailsHeading = detailsHeading;

  // Collapse/Expand functionality for Step 3 Metadata
  const btnCollapse = document.querySelector("#btn-collapse-s3-meta");
  const btnExpand = document.querySelector("#btn-expand-s3-meta");
  const splitLayout = document.querySelector(".step3-split-layout");

  if (btnCollapse && btnExpand && splitLayout) {
    btnCollapse.addEventListener("click", () => {
      splitLayout.classList.add("s3-meta-collapsed");
    });
    btnExpand.addEventListener("click", () => {
      splitLayout.classList.remove("s3-meta-collapsed");
    });
  }

  // Initialize global [全部 details] toggle button
  initAllDetailsToggle(document.querySelector("#btn-toggle-all-details"));

  // Listen to work selection event dispatched from wizard metadata panel
  window.addEventListener("bookrate:select-work", (e) => {
    if (e.detail) {
      selectWork(e.detail);
    }
  });
}

// ---------------------------------------------------------------------------
// Row / cell lifecycle builders
// ---------------------------------------------------------------------------

export function renderCountCell(countEl, countVal) {
  countEl.textContent = displayCount(countVal);
}

/** Creates an empty <tr> with "Fetching…" placeholders for every active source column. */
export function renderInitialWorkRow(work) {
  const row = document.createElement("tr");
  row.className = "work-row";

  SOURCES.forEach((source) => {
    if (source.id === "douban_api") return;
    const suffix = SOURCE_PREFIX[source.id];
    const td = document.createElement("td");
    td.className = `col-${suffix}`;

    const strong = document.createElement("strong");
    strong.className = `${suffix}-rate`;

    const small = document.createElement("small");
    small.className = `${suffix}-count`;

    // Sources whose toggle is off never get fetched — show a static
    // "Disable Source" placeholder instead of a perpetual Fetching state.
    const checkbox = document.querySelector(`#score-${suffix}`);
    if (checkbox && !checkbox.checked) {
      strong.innerHTML = '<span class="disabled-tag">Disable Source</span>';
      small.textContent = "-";
    } else {
      strong.innerHTML = '<span class="fetching-tag">Fetching...</span>';
      small.textContent = "讀取中...";
    }

    td.appendChild(strong);
    td.appendChild(small);
    row.appendChild(td);
  });

  return row;
}

/** Switches a single source column to the static "Disable Source" placeholder. */
export function markSourceCellDisabled(row, prefix) {
  const rateEl = row.querySelector(`.${prefix}-rate`);
  const countEl = row.querySelector(`.${prefix}-count`);
  if (!rateEl || !countEl) return;

  rateEl.innerHTML = '<span class="disabled-tag">Disable Source</span>';
  countEl.textContent = "-";

  const cell = rateEl.closest("td");
  if (cell) {
    cell.querySelectorAll(".source-book-title, :scope > .search-status-tag, .source-book-details, .search-meta-box").forEach(el => el.remove());
  }
}

// ---------------------------------------------------------------------------
// SSE orchestration & payload builder
// ---------------------------------------------------------------------------

/**
 * Builds the RatingRequestPayload object for work details retrieval.
 * Automatically retrieves metadata from Step 2/3 metadata editor.
 * 
 * @param {Object} work - The Work object containing key, title, and author.
 * @param {string[]} engines - List of source engine IDs to query.
 * @param {Object} strategies - Mapping of engines to search strategies.
 * @param {string} apiKey - Optional Google Books API Key.
 * @returns {Object} The payload object matching RatingRequestPayload schema.
 */
function buildWorkDetailsPayload(work, engines, strategies, apiKey) {
  const meta = getStep3Metadata();
  return {
    work_id: work.key,
    title: work.title || "",
    author: work.author || "",
    engines: engines,
    strategies: strategies,
    search_name: meta.searchName || "",
    title_list: meta.titleList || [],
    title_zh_list: meta.titleZhList || [],
    author_list: meta.authorList || [],
    isbn_list: meta.isbnList || [],
    google_key: apiKey || null
  };
}

// ---------------------------------------------------------------------------
// Table header source links
// ---------------------------------------------------------------------------

/**
 * Resolves the first search query of a source column under its current strategy.
 * Falls back to the user's raw search name when the preferred list is empty.
 * @param {string} sourceId
 * @param {Object} strategies - Mapping of engine IDs to search strategies.
 * @returns {string}
 */
function _resolveHeaderQuery(sourceId, strategies) {
  const meta = getStep3Metadata();
  const strategy = strategies[sourceId] || getSourceDefaultStrat(sourceId);

  let query = "";
  switch (strategy) {
    case "title_zh_list":
    case "title_zh_list_full":
      query = meta.titleZhList[0] || "";
      break;
    case "title_list":
    case "title_list_full":
      query = meta.titleList[0] || "";
      break;
    case "isbn":
      query = meta.isbnList[0] || "";
      break;
    case "search_name":
    default:
      query = "";
      break;
  }
  return query || meta.searchName || "";
}

/**
 * Updates each table-header source hyperlink so that it points to the
 * platform's title-search page using the column's current first query.
 * Called from selectWork() and the strategy-change listener in app.js.
 * @param {Object} strategies - Mapping of engine IDs to search strategies.
 */
export function updateTableHeaderLinks(strategies) {
  document.querySelectorAll("a.source-header-link[data-source-id]").forEach((link) => {
    const sourceId = link.dataset.sourceId;
    const source = SOURCES.find((s) => s.id === sourceId);
    if (!source) return;

    const query = _resolveHeaderQuery(sourceId, strategies);
    link.href = query ? getSourceSearchUrl(sourceId, query) : source.url;
    link.title = query ? `在 ${source.label} 搜尋：${query}` : `前往 ${source.label} 首頁`;
  });
}

/** Advances to Step 3, starts the SSE stream, and populates the rating table. */
export async function selectWork(work) {
  state.currentSelectedWork = work;

  _detailsHeading.hidden = false;
  goToStep(3);
  _resultBody.replaceChildren();

  const row = renderInitialWorkRow(work);
  _resultBody.append(row);
  _tableWrap.hidden = false;

  _step3Status.classList.remove("error");
  _step3Status.textContent = "";

  const activeRateSourcesList = getActiveRateSourcesList();
  const apiKey = localStorage.getItem(STORAGE_KEYS.GOOGLE_API_KEY) || "";
  let strategies = getSelectedStrategies();

  if (state.searchMode === "quick_search") {
    strategies = {};
    activeRateSourcesList.forEach((source) => {
      strategies[source] = "search_name";
    });
  }

  // Keep header source names linking to each column's current first query.
  updateTableHeaderLinks(strategies);

  // Separate cached vs pending sources
  const cachedRateSources = [];
  const pendingRateSources = [];
  activeRateSourcesList.forEach((source) => {
    const strategy = strategies[source] || getSourceDefaultStrat(source);
    const cachedData = getRatingCache(work.key, source, strategy);
    if (cachedData) {
      cachedRateSources.push({ source, data: cachedData });
    } else {
      pendingRateSources.push(source);
    }
  });

  // Immediately render cached sources
  cachedRateSources.forEach(({ source, data }) => {
    const config = getSourceDisplayConfig(source);
    renderSourceCell(row, {
      sourceId: config.sourceId,
      prefix: config.prefix,
      data,
      maxRate: config.maxRate
    });
  });

  try {
    const payload = buildWorkDetailsPayload(work, pendingRateSources, strategies, apiKey);

    const collectedDetails = { work, ratings: {}, editions: {} };
    SOURCES.forEach((source) => { collectedDetails[source.id] = {}; });

    streamWorkDetailsPost(
      payload,
      (data) => {
        if (data.type === "init") {
          collectedDetails.ratings = data.ratings;
          collectedDetails.editions = data.editions;
          collectedDetails.crawler_status = data.crawler_status;
        } else if (data.type === "source") {
          const sourceKey = data.source;
          collectedDetails[sourceKey] = data.data;
          const config = getSourceDisplayConfig(sourceKey);
          const strategy = strategies[sourceKey] || getSourceDefaultStrat(sourceKey);
          setRatingCache(work.key, sourceKey, strategy, data.data);
          renderSourceCell(row, {
            sourceId: config.sourceId,
            prefix: config.prefix,
            data: data.data,
            maxRate: config.maxRate
          });
        }
      },
      (err) => {
        console.error("POST Stream failed:", err);
        _step3Status.textContent = "";
      },
      () => {
        _step3Status.textContent = "";
      }
    );
  } catch (error) {
    console.error(error);
    _step3Status.classList.add("error");
    _step3Status.textContent = "取得作品詳細評分失敗，請確認網路連線後再試一次。";
  }
}

/** Re-queries a single rating source and updates its column in the existing row. */
export function reQuerySingleSource(work, sourceKey) {
  const row = _resultBody.querySelector(".work-row");
  if (!row) return;

  const config = getSourceDisplayConfig(sourceKey);
  let strategies = getSelectedStrategies();
  if (state.searchMode === "quick_search") {
    strategies = {};
    SOURCES.forEach((source) => {
      strategies[source.id] = "search_name";
    });
  }
  const strategy = strategies[sourceKey] || getSourceDefaultStrat(sourceKey);

  // Check cache first
  const cachedData = getRatingCache(work.key, sourceKey, strategy);
  if (cachedData) {
    renderSourceCell(row, {
      sourceId: config.sourceId,
      prefix: config.prefix,
      data: cachedData,
      maxRate: config.maxRate
    });
    return;
  }

  const rateEl = row.querySelector(`.${config.prefix}-rate`);
  const countEl = row.querySelector(`.${config.prefix}-count`);
  if (rateEl && countEl) {
    rateEl.innerHTML = '<span class="fetching-tag">Fetching...</span>';
    countEl.textContent = "讀取中...";
    const cell = rateEl.closest("td");
    if (cell) {
      cell.querySelectorAll(".source-book-title, :scope > .search-status-tag, .source-book-details, .search-meta-box").forEach(el => el.remove());
    }
  }

  const apiKey = localStorage.getItem(STORAGE_KEYS.GOOGLE_API_KEY) || "";
  const payload = buildWorkDetailsPayload(work, [sourceKey], strategies, apiKey);

  streamWorkDetailsPost(
    payload,
    (data) => {
      if (data.type === "source") {
        const strategy = strategies[sourceKey] || getSourceDefaultStrat(sourceKey);
        setRatingCache(work.key, sourceKey, strategy, data.data);
        renderSourceCell(row, {
          sourceId: config.sourceId,
          prefix: config.prefix,
          data: data.data,
          maxRate: config.maxRate
        });
      }
    },
    (err) => {
      console.error("Single source re-query failed:", err);
    },
    () => { }
  );
}
