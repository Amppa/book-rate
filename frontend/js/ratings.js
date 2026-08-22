import { state } from './state.js';
import { STORAGE_KEYS, SOURCES, SOURCE_PREFIX, OPEN_LIBRARY_BASE_URL, STRATEGY_LABEL_MAP } from './constants.js';
import { displayRate, displayCount } from './utils.js';
import { getRatingCache, setRatingCache } from './cache.js';
import { streamWorkDetailsPost } from './api.js';
import {
  getStep3Metadata,
  getSelectedStrategies,
  getActiveRateSourcesList,
  getSourceDefaultStrat,
  goToStep
} from './wizard.js';


// DOM references injected at startup via initRatings()
let _resultBody, _step3Status, _tableWrap, _detailsHeading, _candidateList;

/**
 * Inject DOM references that ratings.js needs.
 * Called once from app.js before any user interaction.
 */
export function initRatings({ resultBody, step3Status, tableWrap, detailsHeading, candidateList }) {
  _resultBody = resultBody;
  _step3Status = step3Status;
  _tableWrap = tableWrap;
  _detailsHeading = detailsHeading;
  _candidateList = candidateList;

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

  // Listen to work selection event dispatched from wizard metadata panel
  window.addEventListener("bookrate:select-work", (e) => {
    if (e.detail) {
      selectWork(e.detail);
    }
  });
}

// ---------------------------------------------------------------------------
// Row / cell builders
// ---------------------------------------------------------------------------

export function renderCountCell(countEl, countVal) {
  countEl.textContent = displayCount(countVal);
}

/** Creates an empty <tr> with "Fetching…" placeholders for every source column. */
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
    strong.innerHTML = '<span class="fetching-tag">Fetching...</span>';

    const small = document.createElement("small");
    small.className = `${suffix}-count`;
    small.textContent = "讀取中...";

    td.appendChild(strong);
    td.appendChild(small);
    row.appendChild(td);
  });

  return row;
}

/**
 * Renders rating data into a single source column of a work row.
 * Handles multi-result, single-result, error, and quota-exceeded cases.
 */
export function renderSourceCell(row, prefix, data, maxRate = 5) {
  const rateEl = row.querySelector(`.${prefix}-rate`);
  const countEl = row.querySelector(`.${prefix}-count`);
  if (!rateEl || !countEl) return;
  if (!data || Object.keys(data).length === 0) return;

  const hasScore = typeof data.average === "number" && data.average > 0;
  const hasUrl = Boolean(data.url);
  const status = data.status || (hasScore ? "MATCH" : "NO_MATCH");
  const isNetworkError = status
    && status !== "MATCH"
    && status !== "CURL_MATCH"
    && status !== "NO_MATCH"
    && status !== "QUOTA_EXCEEDED"
    && status !== "ERROR";

  rateEl.replaceChildren();

  const cell = rateEl.closest("td");
  if (cell) {
    const oldTitles = cell.querySelectorAll(".source-book-title");
    oldTitles.forEach(el => el.remove());

    const oldDirectTags = cell.querySelectorAll(":scope > .search-status-tag, :scope > .source-status-row");
    oldDirectTags.forEach(el => el.remove());

    // In single-result mode, display the matched title above the rating (as link if url exists)
    if (data.title && (!data.results || data.results.length === 0)) {
      const titleEl = document.createElement(data.url ? "a" : "div");
      titleEl.className = "source-book-title";
      titleEl.textContent = data.url ? `${data.title} ↗` : data.title;
      if (data.url) {
        titleEl.href = data.url;
        titleEl.target = "_blank";
        titleEl.rel = "noreferrer";
      }
      cell.insertBefore(titleEl, rateEl);
    }
  }

  // --- Multi-result mode ---
  if (data.results && data.results.length > 0) {
    const listContainer = document.createElement("div");
    listContainer.className = "multi-result-list";

    data.results.forEach((res) => {
      const item = document.createElement("div");
      item.className = "multi-result-item";
      item.title = `查詢: ${res.query || "N/A"}\n書名: ${res.title || "N/A"}`;

      if (res.title) {
        const titleEl = document.createElement(res.url ? "a" : "div");
        titleEl.className = "source-book-title";
        titleEl.textContent = res.url ? `${res.title} ↗` : res.title;
        if (res.url) {
          titleEl.href = res.url;
          titleEl.target = "_blank";
          titleEl.rel = "noreferrer";
        }
        item.appendChild(titleEl);
      }

      const strong = document.createElement("strong");
      const small = document.createElement("small");

      const rScore = typeof res.average === "number" && res.average > 0;
      let resStatus = res.status || (rScore ? "MATCH" : (res.url ? "UNRATED" : "NOT_FOUND"));

      const isResNetworkError = resStatus
        && resStatus !== "MATCH"
        && resStatus !== "CURL_MATCH"
        && resStatus !== "UNRATED"
        && resStatus !== "NO_MATCH"
        && resStatus !== "NOT_FOUND"
        && resStatus !== "QUOTA_EXCEEDED"
        && resStatus !== "ERROR";

      const badge = _buildStatusTag(resStatus, res);

      if (resStatus === "QUOTA_EXCEEDED") {
        badge.textContent = "429 額度";
        strong.innerHTML = '<span class="error">額度超限 ⚠️</span>';
        small.textContent = "請設定 API Key";
      } else if (resStatus === "RATE_LIMITED" || resStatus === "RATE_LIMIT") {
        badge.textContent = "風控(429/403)";
        strong.innerHTML = '<span class="error">連線異常(風控) ⚠️</span>';
        small.textContent = "請求過密或遭阻擋";
      } else if (resStatus === "ERROR") {
        badge.textContent = "錯誤";
        strong.innerHTML = '<span class="error">讀取錯誤 ⚠️</span>';
        small.textContent = "請檢查主機連線";
      } else if (isResNetworkError) {
        badge.textContent = "連線異常";
        strong.innerHTML = '<span class="error">連線異常 ⚠️</span>';
        small.textContent = resStatus;
      } else if (rScore) {
        const rateText = displayRate(res.average, res.count, maxRate);
        strong.textContent = rateText;
        renderCountCell(small, res.count);
      } else if (res.url || resStatus === "UNRATED") {
        strong.textContent = "暫無評分";
        small.textContent = res.count ? displayCount(res.count) : "-";
      } else {
        strong.textContent = "無此書籍";
        small.textContent = "-";
      }

      item.appendChild(strong);
      item.appendChild(small);
      item.appendChild(badge);
      listContainer.appendChild(item);
    });

    rateEl.appendChild(listContainer);
    countEl.replaceChildren();
    return;
  }


  // --- Single-result mode ---
  if (data.quota_exceeded || status === "QUOTA_EXCEEDED") {
    rateEl.innerHTML = '<span class="error">額度超限 (429) ⚠️</span>';
    countEl.textContent = "請在上方設定個人 API Key，或設定環境變數。";
  } else if (status === "RATE_LIMITED" || status === "RATE_LIMIT") {
    rateEl.innerHTML = '<span class="error">連線異常 (風控/429) ⚠️</span>';
    countEl.textContent = "請求過密或遭阻擋";
  } else if (status === "ERROR") {
    rateEl.innerHTML = '<span class="error">讀取錯誤 ⚠️</span>';
    countEl.textContent = "請檢查主機連線。";
  } else if (isNetworkError) {
    rateEl.innerHTML = '<span class="error">連線異常 ⚠️</span>';
    countEl.textContent = status;
  } else if (hasScore) {
    const rateText = displayRate(data.average, data.count, maxRate);
    rateEl.textContent = rateText;
    renderCountCell(countEl, data.count);
  } else if (hasUrl || status === "UNRATED") {
    rateEl.textContent = "暫無評分";
    countEl.textContent = data.count ? displayCount(data.count) : "-";
  } else {
    rateEl.textContent = "無此書籍";
    countEl.textContent = "-";
  }

  if (cell) {
    const oldDirectTags = cell.querySelectorAll(":scope > .search-status-tag, :scope > .source-status-row");
    oldDirectTags.forEach(el => el.remove());
    const tag = _buildStatusTag(status, data);
    cell.appendChild(tag);
  }
}

/** Builds the strategy/status tooltip tag element. */
function _buildStatusTag(status, data) {
  const tag = document.createElement("span");
  const normStatusClass = (status || "").toLowerCase().replace(/[^a-z0-9_]/g, "-");
  tag.className = `search-status-tag status-${normStatusClass}`;
  tag.textContent = status || "NO_MATCH";
  tag.dataset.strat = data?.strategy || "";
  tag.dataset.query = data?.query || "";
  const friendlyStrat = STRATEGY_LABEL_MAP[data?.strategy] || data?.strategy || "N/A";
  tag.title = `策略: ${friendlyStrat}, 查詢: ${data?.query || "N/A"}`;
  return tag;
}

/** Renders the Open Library rating into the row after the "init" SSE event. */
export function updateWorkDetailRow(row, { work, ratings }, strategies) {
  if (!row) return;
  const olUrl = ratings?.url
    || ((work.key && work.key.startsWith("/works/")) ? `${OPEN_LIBRARY_BASE_URL}${work.key}` : null);
  const olData = {
    average: ratings?.average,
    count: ratings?.count,
    url: olUrl,
    status: (ratings?.average ? "MATCH" : "NO_MATCH")
  };
  renderSourceCell(row, "ol", olData, 5);

  if (strategies) {
    const olStrategy = strategies.open_library || getSourceDefaultStrat("open_library");
    setRatingCache(work.key, "open_library", olStrategy, olData);
  }
}

// ---------------------------------------------------------------------------
// SSE orchestration
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
    const prefix = SOURCE_PREFIX[source] || source;
    const maxRate = prefix === "db" ? 10 : 5;
    renderSourceCell(row, prefix, data, maxRate);
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
          updateWorkDetailRow(row, collectedDetails, strategies);
        } else if (data.type === "source") {
          const sourceKey = data.source;
          collectedDetails[sourceKey] = data.data;
          const prefix = SOURCE_PREFIX[sourceKey] || sourceKey;
          const maxRate = prefix === "db" ? 10 : 5;
          const strategy = strategies[sourceKey] || getSourceDefaultStrat(sourceKey);
          setRatingCache(work.key, sourceKey, strategy, data.data);
          renderSourceCell(row, prefix, data.data, maxRate);
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

  const prefix = SOURCE_PREFIX[sourceKey] || sourceKey;
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
    const maxRate = prefix === "db" ? 10 : 5;
    renderSourceCell(row, prefix, cachedData, maxRate);
    return;
  }

  const rateEl = row.querySelector(`.${prefix}-rate`);
  const countEl = row.querySelector(`.${prefix}-count`);
  if (rateEl && countEl) {
    rateEl.innerHTML = '<span class="fetching-tag">Fetching...</span>';
    countEl.textContent = "讀取中...";
    const cell = rateEl.closest("td");
    if (cell) {
      const metaBox = cell.querySelector(".search-meta-box");
      if (metaBox) metaBox.remove();
    }
  }

  const apiKey = localStorage.getItem(STORAGE_KEYS.GOOGLE_API_KEY) || "";
  const payload = buildWorkDetailsPayload(work, [sourceKey], strategies, apiKey);

  streamWorkDetailsPost(
    payload,
    (data) => {
      if (data.type === "source") {
        const maxRate = prefix === "db" ? 10 : 5;
        const strategy = strategies[sourceKey] || getSourceDefaultStrat(sourceKey);
        setRatingCache(work.key, sourceKey, strategy, data.data);
        renderSourceCell(row, prefix, data.data, maxRate);
      }
    },
    (err) => {
      console.error("Single source re-query failed:", err);
    },
    () => {}
  );
}
