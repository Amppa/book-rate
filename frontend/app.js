import { MAX_CANDIDATES, SOURCES, SOURCE_PREFIX } from './js/constants.js';
import {
  getCachedData, setCachedData, cleanExpiredCache,
  clearAllStep2Cache, clearAllStep3Cache, clearEditionsCache, clearWorkRatingsCache
} from './js/cache.js';
import { fetchJson } from './js/utils.js';
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
const step2Status = document.querySelector("#step-2-status");
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
initWizard({ onSelectWork: selectWork });

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------
function initSettings() {
  initTableVisibilityStyles();
  renderTableHeaders(document.querySelector("#table-header-row"));
  renderTitleSourceTabs(document.querySelector("#title-source-tabs-container"), state.currentTitleSource);
  renderSourceToggles(scoreToggleBarEl);
  renderStrategySelects(scoreStrategyRowEl);

  SOURCES.forEach((source) => {
    const suffix = SOURCE_PREFIX[source.id];
    const checkbox = document.querySelector(`#score-${suffix}`);
    if (checkbox) checkbox.checked = localStorage.getItem(`bookrate:score:${suffix}`) !== "false";

    const select = document.querySelector(`.strategy-select[data-source="${source.id}"]`);
    if (select) {
      const savedStrategy = localStorage.getItem("bookrate:strategy:" + source.id);
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
  const STORAGE_KEY = "bookrate:searchMode";
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

// ---------------------------------------------------------------------------
// Search helpers
// ---------------------------------------------------------------------------
function updateManualSearchLinks(query) {
  const q = (query || "").trim();
  const isbndbLink = document.querySelector("#manual-isbndb-link");
  const isbnsearchLink = document.querySelector("#manual-isbnsearch-link");
  const amazonLink = document.querySelector("#manual-amazon-link");
  if (q) {
    const encoded = encodeURIComponent(q);
    if (isbndbLink) isbndbLink.href = `https://isbndb.com/search/books/${encoded}`;
    if (isbnsearchLink) isbnsearchLink.href = `https://isbnsearch.org/search?s=${encoded}`;
    if (amazonLink) amazonLink.href = `https://www.amazon.com/s?k=${encoded}&i=stripbooks`;
  } else {
    if (isbndbLink) isbndbLink.href = "https://isbndb.com/";
    if (isbnsearchLink) isbnsearchLink.href = "https://isbnsearch.org/";
    if (amazonLink) amazonLink.href = "https://www.amazon.com/s?i=stripbooks";
  }
}

function updateTitleSourceTabs(titleSource) {
  const tabsContainer = document.querySelector("#title-source-tabs-container");
  if (tabsContainer) {
    tabsContainer.querySelectorAll(".title-source-tab-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.sourceId === titleSource);
    });
  }
}

function updatePagination(itemsCount) {
  if (!state.currentQuery) { paginationControls.hidden = true; return; }
  if (state.currentPage === 1 && itemsCount < MAX_CANDIDATES) { paginationControls.hidden = true; return; }
  paginationControls.hidden = false;
  pageIndicator.textContent = `第 ${state.currentPage} 頁`;
  prevPageBtn.disabled = state.currentPage === 1;
  nextPageBtn.disabled = itemsCount < MAX_CANDIDATES;
}

async function searchWorks(query, page, titleSource = "open_library") {
  state.currentQuery = query;
  state.currentPage = page;
  state.currentTitleSource = titleSource;

  candidateSection.hidden = false;
  candidateHeading.hidden = false;
  goToStep(2);
  updateTitleSourceTabs(titleSource);

  const sourceObj = SOURCES.find(p => p.id === titleSource);
  const titleSourceName = sourceObj ? sourceObj.label : "資料庫";

  candidateList.replaceChildren();
  const loadingEl = document.createElement("div");
  loadingEl.className = "no-results loading";
  loadingEl.textContent = `正從 「${titleSourceName}」 尋找「${query}」…`;
  candidateList.append(loadingEl);

  updateManualSearchLinks(query);
  paginationControls.hidden = true;
  detailsHeading.hidden = true;
  tableWrap.hidden = true;
  resultBody.replaceChildren();
  step2Status.classList.remove("error");
  step2Status.textContent = "";

  if (page === 1) {
    saveHistory(query);
    renderHistory((q) => { searchInput.value = q; });
  }

  try {
    const cacheKey = `search:${query}:page:${page}:engines:${titleSource}`;
    let works = getCachedData(cacheKey);
    if (!works) {
      let url = `/api/search?q=${encodeURIComponent(query)}&page=${page}&engines=${encodeURIComponent(titleSource)}`;
      const apiKey = localStorage.getItem("bookrate:google-api-key") || "";
      if (apiKey) url += `&google_key=${encodeURIComponent(apiKey)}`;
      works = await fetchJson(url);
      if (works) setCachedData(cacheKey, works);
    }

    if (!works || !works.length) {
      step2Status.textContent = "";
      if (page === 1) {
        paginationControls.hidden = true;
        candidateList.replaceChildren();
        const noResultsEl = document.createElement("div");
        noResultsEl.className = "no-results";
        noResultsEl.textContent = `${titleSourceName} 找不到「${query}」`;
        candidateList.append(noResultsEl);
      } else {
        paginationControls.hidden = false;
        pageIndicator.textContent = `第 ${state.currentPage} 頁`;
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
    step2Status.textContent = "";
  } catch (error) {
    console.error(error);
    step2Status.classList.add("error");
    step2Status.textContent = "查詢失敗，請確認網路連線後再試一次。";
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
  step2Status.textContent = "";
  step2Status.classList.remove("error");
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
      const cacheKey = `bookrate:cache:search:${state.currentQuery}:page:${state.currentPage}:engines:${state.currentTitleSource}`;
      localStorage.removeItem(cacheKey);
      clearEditionsCache();
      searchWorks(state.currentQuery, state.currentPage, state.currentTitleSource);
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
      localStorage.setItem(`bookrate:score:${id}`, e.target.checked);
      updateTableVisibility(ratingTable);
    }
  });
}

// Strategy selects
if (scoreStrategyRowEl) {
  scoreStrategyRowEl.addEventListener("change", (e) => {
    if (e.target.classList.contains("strategy-select")) {
      const sourceKey = e.target.dataset.source;
      if (sourceKey) localStorage.setItem("bookrate:strategy:" + sourceKey, e.target.value);
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
    if (key.startsWith("bookrate:cache:")) {
      hasStep2 = true;
    } else if (key.startsWith("bookrate:rating:")) {
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
const GOOGLE_KEY_STORAGE_KEY = "bookrate:google-api-key";

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
// Modal initialisation
// ---------------------------------------------------------------------------
initPresetsModal(searchInput);
initEditionsModal();
initSourceInfoModal();
