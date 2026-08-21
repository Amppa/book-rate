import { MAX_CANDIDATES, SOURCES, SOURCE_PREFIX, STORAGE_KEYS } from './js/constants.js';
import {
  getCachedData, setCachedData, cleanExpiredCache,
  clearAllStep2Cache, clearAllStep3Cache, clearEditionsCache, clearWorkRatingsCache,
  getSourceStatusCache, setSourceStatusCache
} from './js/cache.js';
import { fetchJson, getOrCreateTask, getSourceSearchUrl } from './js/utils.js';
import {
  renderSourceToggles, renderStrategySelects, updateTableVisibility,
  renderTableHeaders, renderTitleSourceTabs, initTableVisibilityStyles
} from './js/ui.js';
import { saveHistory, renderHistory } from './js/history.js';
import {
  initWizard, goToStep,
  chooseCandidate, chooseEdition,
  resetMetadataPanel, confirmToStep3,
  getSourceDefaultStrat, directToStep3
} from './js/wizard.js';
import { renderCandidates } from './js/candidates.js';
import { initRatings, selectWork, reQuerySingleSource } from './js/ratings.js';
import { initPresetsModal, initEditionsModal, initSourceInfoModal } from './js/modals.js';
import { state } from './js/state.js';

// Clean expired cache entries on startup
cleanExpiredCache();

// ---------------------------------------------------------------------------
// DOM References
// ---------------------------------------------------------------------------
const searchForm = document.querySelector("#search-form");
const searchInput = document.querySelector("#title");

const step3Status = document.querySelector("#step-3-status");
const candidateSection = document.querySelector("#candidate-section");
const candidateList = document.querySelector("#candidate-list");
const resultsSection = document.querySelector("#results");
const tableWrap = resultsSection.querySelector(".table-wrap");
const resultBody = document.querySelector("#result-body");
const detailsHeading = document.querySelector("#details-heading");
const paginationControls = document.querySelector("#pagination-controls");
const prevPageBtn = document.querySelector("#prev-page-btn");
const nextPageBtn = document.querySelector("#next-page-btn");
const pageIndicator = document.querySelector("#page-indicator");
const candidateHeading = document.querySelector("#candidate-heading");
const btnPrevTo1 = document.querySelector("#btn-prev-to-1");
const btnPrevTo2 = document.querySelector("#btn-prev-to-2");
const ratingTable = document.querySelector("table");
const scoreToggleBarEl = document.querySelector("#score-toggle-bar");
const scoreStrategyRowEl = document.querySelector("#score-strategy-row");

// ---------------------------------------------------------------------------
// Module initialisation
// ---------------------------------------------------------------------------
initRatings({ resultBody, step3Status, tableWrap, detailsHeading, candidateList });
initWizard();

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------
function initSettings() {
  initTableVisibilityStyles();
  renderTableHeaders(document.querySelector("#table-header-row"));
  renderTitleSourceTabs(document.querySelector("#title-source-tabs-container"), state.currentTitleSource);
  updateSourceHint(state.currentTitleSource);
  renderSourceToggles(scoreToggleBarEl);
  renderStrategySelects(scoreStrategyRowEl);

  SOURCES.forEach((source) => {
    const suffix = SOURCE_PREFIX[source.id];
    const checkbox = document.querySelector(`#score-${suffix}`);
    if (checkbox) checkbox.checked = localStorage.getItem(`${STORAGE_KEYS.SCORE_TOGGLE_PREFIX}${suffix}`) !== "false";

    const select = document.querySelector(`.strategy-select[data-source="${source.id}"]`);
    if (select) {
      const savedStrategy = localStorage.getItem(STORAGE_KEYS.STRATEGY_PREFIX + source.id);
      select.value = savedStrategy || source.defaultStrategy;
    }
  });

  updateTableVisibility(ratingTable);
}
initSettings();

// ---------------------------------------------------------------------------
// Search Mode Configuration
// ---------------------------------------------------------------------------
function initSearchMode() {
  const STORAGE_KEY = STORAGE_KEYS.SEARCH_MODE;
  const savedMode = localStorage.getItem(STORAGE_KEY);
  if (savedMode === "quick_search" || savedMode === "edition_search") {
    state.searchMode = savedMode;
  } else {
    state.searchMode = "quick_search"; // Default is quick_search
  }

  // Update UI selector buttons active class
  const modeButtons = document.querySelectorAll(".mode-tab-btn");
  modeButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mode === state.searchMode);

    // Bind click event
    btn.addEventListener("click", () => {
      const mode = btn.dataset.mode;
      if (mode) {
        state.searchMode = mode;
        localStorage.setItem(STORAGE_KEY, mode);
        modeButtons.forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
      }
    });
  });
}
initSearchMode();


function updateSourceHint(titleSource) {
  const hintEl = document.querySelector("#source-hint");
  if (!hintEl) return;
  const sourceObj = SOURCES.find((s) => s.id === titleSource);
  const hintText = (sourceObj && sourceObj.hint) ? sourceObj.hint.trim() : "";
  hintEl.textContent = hintText || "\u00A0";
}

function updateTitleSourceTabs(titleSource) {
  const tabsContainer = document.querySelector("#title-source-tabs-container");
  if (tabsContainer) {
    tabsContainer.querySelectorAll(".title-source-tab-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.sourceId === titleSource);
    });
  }
  updateSourceHint(titleSource);
}

function updatePagination(itemsCount) {
  if (!state.currentQuery) { paginationControls.hidden = true; return; }
  if (state.currentPage === 1 && itemsCount < MAX_CANDIDATES) { paginationControls.hidden = true; return; }
  paginationControls.hidden = false;
  pageIndicator.textContent = `第 ${state.currentPage} 頁`;
  prevPageBtn.disabled = state.currentPage === 1;
  nextPageBtn.disabled = itemsCount < MAX_CANDIDATES;
}

function renderSearchLoading(titleSource, query) {
  const sourceObj = SOURCES.find(p => p.id === titleSource);
  const titleSourceName = sourceObj ? sourceObj.label : "資料庫";

  candidateList.replaceChildren();
  const loadingEl = document.createElement("div");
  loadingEl.className = "no-results loading";
  loadingEl.textContent = `正從 「${titleSourceName}」 尋找「${query}」…`;
  candidateList.append(loadingEl);

  paginationControls.hidden = true;
}

function renderSearchResults(titleSource, query, page, works) {
  const sourceObj = SOURCES.find(p => p.id === titleSource);
  const titleSourceName = sourceObj ? sourceObj.label : "資料庫";

  if (!works || !works.length) {
    if (page === 1) {
      paginationControls.hidden = true;
      candidateList.replaceChildren();
      const noResultsEl = document.createElement("div");
      noResultsEl.className = "no-results";
      noResultsEl.textContent = `${titleSourceName} 找不到「${query}」`;
      candidateList.append(noResultsEl);
    } else {
      paginationControls.hidden = false;
      pageIndicator.textContent = `第 ${page} 頁`;
      prevPageBtn.disabled = false;
      nextPageBtn.disabled = true;
    }
    return;
  }

  renderCandidates(works, {
    onChooseCandidate: chooseCandidate,
    onChooseEdition: chooseEdition
  });
  candidateHeading.hidden = false;
  updatePagination(works.length);
}

function renderSearchError(titleSource, query, page, errorMsg) {
  candidateList.replaceChildren();
  if (paginationControls) paginationControls.hidden = true;

  const sourceObj = SOURCES.find(p => p.id === titleSource);
  const titleSourceName = sourceObj ? sourceObj.label : "資料庫";
  const errStr = String(errorMsg || "");
  const isWaf = /waf|challenge|403|429|rate\s*limit|blocked|forbidden/i.test(errStr);

  const errorEl = document.createElement("div");
  errorEl.className = "no-results";

  if (isWaf) {
    const detailText = errStr || "WAF Challenge / HTTP 403 Forbidden";
    const searchUrl = getSourceSearchUrl(titleSource, query);
    errorEl.innerHTML = `⚠️ 觸發 ${titleSourceName} 的反爬蟲風控<br>Details: ${detailText}<br>建議: 等待數分鐘，或 <a class="waf-alert-link" href="${searchUrl}" target="_blank" rel="noreferrer">手動搜尋 ↗</a>`;
  } else {
    errorEl.classList.add("error");
    errorEl.textContent = errorMsg || "查詢失敗。";
  }

  candidateList.append(errorEl);
}

async function searchWorks(query, page, titleSource = "open_library") {
  if (state.currentQuery !== query || state.currentPage !== page) {
    state.sourceStates = {};
    detailsHeading.hidden = true;
    tableWrap.hidden = true;
    resultBody.replaceChildren();
  }

  state.currentQuery = query;
  state.currentPage = page;
  state.currentTitleSource = titleSource;

  candidateSection.hidden = false;
  candidateHeading.hidden = false;
  goToStep(2);
  updateTitleSourceTabs(titleSource);

  if (page === 1) {
    saveHistory(query);
    renderHistory((q) => { searchInput.value = q; });
  }

  const cacheKey = `search:${query}:page:${page}:engines:${titleSource}`;

  // 1. Prioritize LocalStorage check for instantaneous, synchronous loading
  const cachedWorks = getCachedData(cacheKey);
  if (cachedWorks) {
    state.sourceStates[titleSource] = {
      status: 'success',
      data: cachedWorks,
      error: null,
      promise: Promise.resolve(cachedWorks)
    };
    renderSearchResults(titleSource, query, page, cachedWorks);
    return;
  }

  // 2. Retrieve or create async background search state
  const sourceState = getOrCreateTask(state.sourceStates, titleSource, () => {
    return (async () => {
      let url = `/api/search?q=${encodeURIComponent(query)}&page=${page}&engines=${encodeURIComponent(titleSource)}`;
      const apiKey = localStorage.getItem(STORAGE_KEYS.GOOGLE_API_KEY) || "";
      if (apiKey) url += `&google_key=${encodeURIComponent(apiKey)}`;
      const works = await fetchJson(url);
      if (works) setCachedData(cacheKey, works);
      return works;
    })();
  });

  sourceState.promise.then((works) => {
    if (state.currentTitleSource === titleSource && state.currentQuery === query && state.currentPage === page) {
      renderSearchResults(titleSource, query, page, works);
    }
  }).catch((err) => {
    if (state.currentTitleSource === titleSource && state.currentQuery === query && state.currentPage === page) {
      renderSearchError(titleSource, query, page, sourceState.error);
    }
  });

  // 3. Render immediate UI view based on currently locked memory state
  if (sourceState.status === 'loading') {
    renderSearchLoading(titleSource, query);
  } else if (sourceState.status === 'success') {
    renderSearchResults(titleSource, query, page, sourceState.data);
  } else if (sourceState.status === 'error') {
    renderSearchError(titleSource, query, page, sourceState.error);
  }
}

// ---------------------------------------------------------------------------
// History init
// ---------------------------------------------------------------------------
renderHistory((query) => { searchInput.value = query; });

// ---------------------------------------------------------------------------
// Event bindings
// ---------------------------------------------------------------------------

// Search form
searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = searchInput.value.trim();
  if (!query) return;

  if (state.searchMode === "quick_search") {
    directToStep3(query);
  } else {
    resetMetadataPanel(query);
    searchWorks(query, 1, "open_library");
  }
});

// Source tabs
const tabsContainer = document.querySelector("#title-source-tabs-container");
if (tabsContainer) {
  tabsContainer.addEventListener("click", (e) => {
    const btn = e.target.closest(".title-source-tab-btn");
    if (btn) {
      const sourceId = btn.dataset.sourceId;
      const q = searchInput.value.trim() || state.currentQuery;
      if (q && sourceId) searchWorks(q, 1, sourceId);
    }
  });
}

// Pagination
prevPageBtn.addEventListener("click", () => {
  if (state.currentPage > 1) searchWorks(state.currentQuery, state.currentPage - 1, state.currentTitleSource);
});
nextPageBtn.addEventListener("click", () => {
  searchWorks(state.currentQuery, state.currentPage + 1, state.currentTitleSource);
});

// Wizard navigation
btnPrevTo1.addEventListener("click", () => {
  goToStep(1);

});
btnPrevTo2.addEventListener("click", () => {
  if (state.searchMode === "quick_search") {
    goToStep(1);
  } else {
    goToStep(2);
  }
  step3Status.textContent = "";
  step3Status.classList.remove("error");
});

const btnConfirmTo3 = document.querySelector("#btn-confirm-to-3");
if (btnConfirmTo3) btnConfirmTo3.addEventListener("click", confirmToStep3);

// Local cache refresh buttons
const btnRefreshStep2 = document.querySelector("#btn-refresh-step-2");
if (btnRefreshStep2) {
  btnRefreshStep2.addEventListener("click", () => {
    if (state.currentQuery) {
      const sourceId = state.currentTitleSource;
      const cacheKey = `${STORAGE_KEYS.CACHE_PREFIX}search:${state.currentQuery}:page:${state.currentPage}:engines:${sourceId}`;
      localStorage.removeItem(cacheKey);
      clearEditionsCache();
      if (state.sourceStates && state.sourceStates[sourceId]) {
        delete state.sourceStates[sourceId];
      }
      searchWorks(state.currentQuery, state.currentPage, sourceId);
    }
  });
}

const btnRefreshStep3 = document.querySelector("#btn-refresh-step-3");
if (btnRefreshStep3) {
  btnRefreshStep3.addEventListener("click", () => {
    if (state.currentSelectedWork) {
      clearWorkRatingsCache(state.currentSelectedWork.key);
      selectWork(state.currentSelectedWork);
    }
  });
}

// Score toggles
if (scoreToggleBarEl) {
  scoreToggleBarEl.addEventListener("change", (e) => {
    if (e.target.type === "checkbox") {
      const id = e.target.id.replace("score-", "");
      localStorage.setItem(`${STORAGE_KEYS.SCORE_TOGGLE_PREFIX}${id}`, e.target.checked);
      updateTableVisibility(ratingTable);
    }
  });
}

// Strategy selects
if (scoreStrategyRowEl) {
  scoreStrategyRowEl.addEventListener("change", (e) => {
    if (e.target.classList.contains("strategy-select")) {
      const sourceKey = e.target.dataset.source;
      if (sourceKey) localStorage.setItem(STORAGE_KEYS.STRATEGY_PREFIX + sourceKey, e.target.value);
      if (state.currentSelectedWork && sourceKey) reQuerySingleSource(state.currentSelectedWork, sourceKey);
    }
  });
}

// ---------------------------------------------------------------------------
// Cache Management
// ---------------------------------------------------------------------------
function updateCacheButtonsState() {
  const clearStep2Btn = document.querySelector("#clear-step2-cache-btn");
  const clearStep3Btn = document.querySelector("#clear-step3-cache-btn");
  if (!clearStep2Btn || !clearStep3Btn) return;

  let hasStep2 = false;
  let hasStep3 = false;

  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (!key) continue;
    if (key.startsWith(STORAGE_KEYS.CACHE_PREFIX)) {
      hasStep2 = true;
    } else if (key.startsWith(STORAGE_KEYS.RATING_PREFIX)) {
      hasStep3 = true;
    }
  }

  clearStep2Btn.disabled = !hasStep2;
  clearStep3Btn.disabled = !hasStep3;
}

const clearStep2CacheBtn = document.querySelector("#clear-step2-cache-btn");
if (clearStep2CacheBtn) {
  clearStep2CacheBtn.addEventListener("click", () => {
    clearAllStep2Cache();
    updateCacheButtonsState();
  });
}

const clearStep3CacheBtn = document.querySelector("#clear-step3-cache-btn");
if (clearStep3CacheBtn) {
  clearStep3CacheBtn.addEventListener("click", () => {
    clearAllStep3Cache();
    updateCacheButtonsState();
  });
}

// Google Books API key
const apiKeyInput = document.querySelector("#google-api-key");
const saveApiKeyBtn = document.querySelector("#save-api-key-btn");
const clearApiKeyBtn = document.querySelector("#clear-api-key-btn");
const GOOGLE_KEY_STORAGE_KEY = STORAGE_KEYS.GOOGLE_API_KEY;

const savedKey = localStorage.getItem(GOOGLE_KEY_STORAGE_KEY) || "";
if (apiKeyInput) {
  apiKeyInput.value = savedKey;
  if (savedKey) apiKeyInput.placeholder = "已儲存 API 金鑰 (已遮蔽)";
}
if (saveApiKeyBtn) {
  saveApiKeyBtn.addEventListener("click", () => {
    const val = apiKeyInput ? apiKeyInput.value.trim() : "";
    if (val) {
      localStorage.setItem(GOOGLE_KEY_STORAGE_KEY, val);
      if (apiKeyInput) apiKeyInput.placeholder = "已儲存 API 金鑰 (已遮蔽)";
      alert("Google Books API Key 儲存成功！");
    } else {
      alert("請輸入有效的金鑰！");
    }
  });
}
if (clearApiKeyBtn) {
  clearApiKeyBtn.addEventListener("click", () => {
    localStorage.removeItem(GOOGLE_KEY_STORAGE_KEY);
    if (apiKeyInput) {
      apiKeyInput.value = "";
      apiKeyInput.placeholder = "輸入 API 金鑰 (例如 AIzaSy...)";
    }
    alert("Google Books API Key 已清除！");
  });
}

// Settings auto-close on outside click and cache status update
const settingsDetails = document.querySelector(".settings-details");
if (settingsDetails) {
  settingsDetails.addEventListener("toggle", () => {
    if (settingsDetails.open) {
      updateCacheButtonsState();
    }
  });

  document.addEventListener("click", (event) => {
    if (settingsDetails.open && !settingsDetails.contains(event.target)) {
      settingsDetails.removeAttribute("open");
    }
  });
}

// ---------------------------------------------------------------------------
// Source Status Verification (source-status)
// ---------------------------------------------------------------------------
function initSourceStatus() {
  const statusListEl = document.querySelector("#source-status-list");
  const refreshBtn = document.querySelector("#source-status-refresh-btn");
  if (!statusListEl) return;

  const targetSources = SOURCES.filter(s => s.id !== "douban_api");

  function renderStatus(cachedResults = null) {
    statusListEl.innerHTML = "";
    targetSources.forEach(source => {
      const item = document.createElement("div");
      item.className = "source-status-item";

      const light = document.createElement("span");
      light.className = "source-status-light";

      const name = document.createElement("a");
      name.className = "source-status-name";
      name.textContent = source.label;
      if (source.url) {
        name.href = source.url;
        name.target = "_blank";
        name.rel = "noreferrer";
        name.title = `前往 ${source.label} 首頁`;
      }

      if (cachedResults && cachedResults[source.id]) {
        const res = cachedResults[source.id];
        if (res.status === "ok") {
          light.classList.add("status-ok");
          light.title = `連通延遲: ${res.message}`;
        } else {
          light.classList.add("status-failed");
          light.title = `連線失敗原因: ${res.message}`;
        }
      } else {
        light.title = "尚未檢測連線狀態";
      }

      item.appendChild(name);
      item.appendChild(light);
      statusListEl.appendChild(item);
    });
  }

  async function performCheck(bypassCache = false) {
    if (!bypassCache) {
      const cached = getSourceStatusCache();
      if (cached) {
        renderStatus(cached);
        return;
      }
    }

    statusListEl.querySelectorAll(".source-status-light").forEach(light => {
      light.className = "source-status-light status-checking";
      light.title = "正在檢測連線狀態...";
    });
    if (refreshBtn) refreshBtn.style.pointerEvents = "none";

    try {
      const enginesParam = targetSources.map(s => s.id).join(",");
      const response = await fetch(`/api/source-status?engines=${encodeURIComponent(enginesParam)}`);
      if (!response.ok) throw new Error("API responded with error");

      const results = await response.json();
      setSourceStatusCache(results);
      renderStatus(results);
    } catch (e) {
      console.error("Failed to check source status:", e);
      statusListEl.querySelectorAll(".source-status-light").forEach(light => {
        light.className = "source-status-light status-failed";
        light.title = `連線檢測失敗: ${e.message}`;
      });
    } finally {
      if (refreshBtn) refreshBtn.style.pointerEvents = "";
    }
  }

  const cached = getSourceStatusCache();
  if (cached) {
    renderStatus(cached);
  } else {
    renderStatus();
    performCheck(false);
  }

  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      performCheck(true);
    });
  }
}

// ---------------------------------------------------------------------------
// Modal initialisation
// ---------------------------------------------------------------------------
initPresetsModal(searchInput);
initEditionsModal();
initSourceInfoModal();
initSourceStatus();
