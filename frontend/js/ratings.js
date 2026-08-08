import { state } from './state.js';
import { SOURCES, SOURCE_PREFIX, OPEN_LIBRARY_BASE_URL, STRATEGY_LABEL_MAP } from './constants.js';
import { displayRate, displayCount, buildStreamUrl } from './utils.js';
import { getRatingCache, setRatingCache } from './cache.js';
import {
  getStep3Metadata,
  getSelectedStrategies,
  getActiveRateSourcesList,
  getSourceDefaultStrat,
  goToStep
} from './wizard.js';
import { markCandidateSelected } from './candidates.js';

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
}

// ---------------------------------------------------------------------------
// Row / cell builders
// ---------------------------------------------------------------------------

export function renderCountCell(countEl, countVal, url) {
  const countText = displayCount(countVal);
  if (url) {
    countEl.innerHTML = `<a href="${url}" target="_blank" rel="noreferrer">${countText} ↗</a>`;
  } else {
    countEl.textContent = countText;
  }
}

/** Creates an empty <tr> with "Fetching…" placeholders for every source column. */
export function renderInitialWorkRow(work) {
  const row = document.createElement("tr");
  row.className = "work-row";

  SOURCES.forEach((source) => {
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
    const oldTitle = cell.querySelector(".source-book-title");
    if (oldTitle) oldTitle.remove();

    // In single-result mode, display the matched title above the rating
    if (data.title && (!data.results || data.results.length === 0)) {
      const titleDiv = document.createElement("div");
      titleDiv.className = "source-book-title";
      titleDiv.textContent = data.title;
      cell.insertBefore(titleDiv, rateEl);
    }
  }

  // --- Multi-result mode ---
  if (data.results && data.results.length > 0) {
    const listContainer = document.createElement("div");
    listContainer.className = "multi-result-list";

    data.results.forEach((res, index) => {
      const item = document.createElement("div");
      item.className = "multi-result-item";
      item.title = `查詢: ${res.query || "N/A"}\n書名: ${res.title || "N/A"}`;

      const numSpan = document.createElement("span");
      numSpan.className = "multi-result-index";
      numSpan.textContent = `${index + 1}.`;
      item.appendChild(numSpan);

      const detailContainer = document.createElement("div");
      detailContainer.className = "multi-result-details";

      if (res.title) {
        const titleDiv = document.createElement("div");
        titleDiv.className = "multi-result-title";
        titleDiv.textContent = res.title;
        detailContainer.appendChild(titleDiv);
      }

      const valSpan = document.createElement("span");
      valSpan.className = "multi-result-value";
      const rScore = typeof res.average === "number" && res.average > 0;

      if (res.status && res.status.startsWith("Error")) {
        valSpan.innerHTML = '<span class="error">錯誤 ⚠️</span>';
      } else if (rScore) {
        const rateText = displayRate(res.average, res.count, maxRate);
        if (res.url) {
          valSpan.innerHTML = `<a href="${res.url}" target="_blank" rel="noreferrer" class="multi-result-link">${rateText} (${displayCount(res.count)}) ↗</a>`;
        } else {
          valSpan.textContent = `${rateText} (${displayCount(res.count)})`;
        }
      } else if (res.url) {
        valSpan.innerHTML = `<a href="${res.url}" target="_blank" rel="noreferrer" class="multi-result-link">暫無評分 ↗</a>`;
      } else {
        valSpan.textContent = "無此書籍";
        valSpan.style.color = "var(--text-muted)";
      }

      detailContainer.appendChild(valSpan);
      item.appendChild(detailContainer);
      listContainer.appendChild(item);
    });

    rateEl.appendChild(listContainer);
    countEl.replaceChildren();

    if (cell) {
      const oldTag = cell.querySelector(".search-status-tag");
      if (oldTag) oldTag.remove();
      const tag = _buildStatusTag(status, data);
      cell.appendChild(tag);
    }
    return;
  }

  // --- Single-result mode ---
  if (data.quota_exceeded || status === "QUOTA_EXCEEDED") {
    rateEl.innerHTML = '<span class="error">額度超限 (429) ⚠️</span>';
    countEl.textContent = "請在上方設定個人 API Key，或設定環境變數。";
  } else if (status === "ERROR") {
    rateEl.innerHTML = '<span class="error">讀取錯誤 ⚠️</span>';
    countEl.textContent = "請檢查主機連線。";
  } else if (isNetworkError) {
    rateEl.innerHTML = '<span class="error">連線異常 ⚠️</span>';
    countEl.textContent = status;
  } else if (hasScore) {
    const rateText = displayRate(data.average, data.count, maxRate);
    rateEl.textContent = rateText;
    renderCountCell(countEl, data.count, data.url);
  } else if (hasUrl) {
    rateEl.textContent = "暫無評分";
    countEl.innerHTML = `<a href="${data.url}" target="_blank" rel="noreferrer">連結 ↗</a>`;
  } else {
    rateEl.textContent = "無此書籍";
    countEl.textContent = "-";
  }

  if (cell) {
    const oldTag = cell.querySelector(".search-status-tag");
    if (oldTag) oldTag.remove();
    const tag = _buildStatusTag(status, data);
    cell.appendChild(tag);
  }
}

/** Builds the strategy/status tooltip tag element appended to each source cell. */
function _buildStatusTag(status, data) {
  const tag = document.createElement("span");
  tag.className = `search-status-tag status-${status.toLowerCase().replace(/[^a-z0-9_]/g, "-")}`;
  tag.textContent = status;
  tag.dataset.strat = data.strategy || "";
  tag.dataset.query = data.query || "";
  const friendlyStrat = STRATEGY_LABEL_MAP[data.strategy] || data.strategy || "N/A";
  tag.title = `策略: ${friendlyStrat}, 查詢: ${data.query || "N/A"}`;
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

/** Advances to Step 3, starts the SSE stream, and populates the rating table. */
export async function selectWork(work) {
  state.currentSelectedWork = work;
  markCandidateSelected(_candidateList, work.key);

  _detailsHeading.hidden = false;
  goToStep(3);
  _resultBody.replaceChildren();

  const row = renderInitialWorkRow(work);
  _resultBody.append(row);
  _tableWrap.hidden = false;

  _step3Status.classList.remove("error");
  _step3Status.textContent = "";

  const activeRateSourcesList = getActiveRateSourcesList();
  const apiKey = localStorage.getItem("bookrate:google-api-key") || "";
  const strategies = getSelectedStrategies();

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
    const meta = getStep3Metadata();
    const url = buildStreamUrl(work.key, meta, pendingRateSources, strategies, apiKey);

    const collectedDetails = { work, ratings: {}, editions: {} };
    SOURCES.forEach((source) => { collectedDetails[source.id] = {}; });

    const eventSource = new EventSource(url);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
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
        } else if (data.type === "done") {
          eventSource.close();
          _step3Status.textContent = "";
        }
      } catch (err) {
        console.error("Stream parse error:", err);
      }
    };

    eventSource.onerror = (err) => {
      console.error("EventSource failed:", err);
      eventSource.close();
      _step3Status.textContent = "";
    };
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

  const apiKey = localStorage.getItem("bookrate:google-api-key") || "";
  const strategies = getSelectedStrategies();
  const meta = getStep3Metadata();
  const url = buildStreamUrl(work.key, meta, sourceKey, strategies, apiKey);

  const eventSource = new EventSource(url);
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "source") {
        const maxRate = prefix === "db" ? 10 : 5;
        const strategy = strategies[sourceKey] || getSourceDefaultStrat(sourceKey);
        setRatingCache(work.key, sourceKey, strategy, data.data);
        renderSourceCell(row, prefix, data.data, maxRate);
      } else if (data.type === "done") {
        eventSource.close();
      }
    } catch (err) {
      console.error("Single source re-query parse error:", err);
    }
  };
  eventSource.onerror = (err) => {
    console.error("Single source EventSource failed:", err);
    eventSource.close();
  };
}
