import { OPEN_LIBRARY_BASE_URL, MAX_CANDIDATES, HISTORY_KEY, PROVIDERS, STRATEGIES, PROVIDER_CHECKBOX_SUFFIX } from './js/constants.js';
import { getCachedData, setCachedData, getRatingCache, setRatingCache, cleanExpiredCache } from './js/cache.js';
import { fetchJson, displayRate, displayCount, getWorkExternalUrl, getProviderDisplayName } from './js/utils.js';
import { renderProviderToggles, updateTableVisibility, openEditionsModal } from './js/ui.js';

// Clean expired cache entries on load
cleanExpiredCache();

const searchForm = document.querySelector("#search-form");
const searchInput = document.querySelector("#title");
const step2Status = document.querySelector("#step-2-status");
const step3Status = document.querySelector("#step-3-status");
const candidateSection = document.querySelector("#candidate-section");
const candidateList = document.querySelector("#candidate-list");
const candidateTemplate = document.querySelector("#candidate-template");
const historySection = document.querySelector("#history-section");
const historyList = document.querySelector("#history-list");
const resultsSection = document.querySelector("#results");
const tableWrap = resultsSection.querySelector(".table-wrap");
const resultBody = document.querySelector("#result-body");
const detailsHeading = document.querySelector("#details-heading");
const resultRowTemplate = document.querySelector("#result-template");
const paginationControls = document.querySelector("#pagination-controls");
const prevPageBtn = document.querySelector("#prev-page-btn");
const nextPageBtn = document.querySelector("#next-page-btn");
const pageIndicator = document.querySelector("#page-indicator");
const candidateHeading = document.querySelector("#candidate-heading");
const wizardTrack = document.querySelector("#wizard-track");
const btnPrevTo1 = document.querySelector("#btn-prev-to-1");
const btnPrevTo2 = document.querySelector("#btn-prev-to-2");
const ratingTable = document.querySelector("table");

let currentQuery = "";
let currentPage = 1;
let currentStep = 1;
let currentEngine = "open_library";
let currentSelectedWork = null;

function goToStep(step) {
  currentStep = step;
  document.querySelectorAll(".wizard-step").forEach((el, index) => {
    if (index + 1 === step) {
      el.classList.add("active");
    } else {
      el.classList.remove("active");
    }
  });
}

function getHistory() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY)) || [];
  } catch {
    return [];
  }
}

function saveHistory(query) {
  const history = [query, ...getHistory().filter((item) => item !== query)].slice(0, 5);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
  renderHistory();
}

function renderHistory() {
  const history = getHistory();
  historyList.replaceChildren();
  historySection.hidden = !history.length;

  history.forEach((query) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "history-item";
    button.textContent = query;
    button.addEventListener("click", () => {
      searchInput.value = query;
    });
    historyList.append(button);
  });
}

function renderCandidates(works) {
  candidateList.replaceChildren();
  works.forEach((work) => {
    const fragment = candidateTemplate.content.cloneNode(true);
    const cardEl = fragment.querySelector(".candidate-card");
    if (cardEl) {
      cardEl.dataset.key = work.key;
    }
    fragment.querySelector(".candidate-title").textContent = work.title;

    // 預設顯示：作者和首版日期
    const authorVal = (work.author_name || ["Unknown"]).join("、");
    const basicMetaText = `作者：${authorVal}` + (work.first_publish_year ? ` · 首版 ${work.first_publish_year}` : "");
    fragment.querySelector(".candidate-basic-meta").textContent = basicMetaText;

    // 填充展開的詳細資料
    fragment.querySelector(".meta-author").textContent = authorVal;
    fragment.querySelector(".meta-year").textContent = work.first_publish_year || "暫無資料";
    fragment.querySelector(".meta-editions").textContent = work.edition_count ? `${work.edition_count.toLocaleString()} 個版本` : "暫無資料";

    // 處理 ISBN 與 系列 ISBN
    let primaryIsbn = "暫無資料";
    let otherIsbnsText = "無";
    if (work.isbn) {
      const isbnList = Array.isArray(work.isbn) ? work.isbn : [work.isbn];
      if (isbnList.length > 0) {
        primaryIsbn = isbnList[0];
        const remaining = isbnList.slice(1, 11); // 最多 10 個
        if (remaining.length > 0) {
          otherIsbnsText = remaining.join("、");
        }
      }
    }
    fragment.querySelector(".meta-primary-isbn").textContent = primaryIsbn;
    fragment.querySelector(".meta-other-isbns").textContent = otherIsbnsText;

    // 外部連結
    const metaLinksEl = fragment.querySelector(".meta-links");
    const extUrl = getWorkExternalUrl(work.key);
    if (extUrl) {
      const a = document.createElement("a");
      a.href = extUrl;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.className = "candidate-link";
      a.textContent = `${getProviderDisplayName(work.key.split(":")[0]) || "外部連結"} ↗`;
      metaLinksEl.appendChild(a);
    } else {
      metaLinksEl.textContent = "-";
    }

    // Toggle 按鈕
    const toggleBtn = fragment.querySelector(".toggle-metadata-btn");
    const detailsRow = fragment.querySelector(".candidate-details-row");
    toggleBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const isHidden = detailsRow.hidden;
      detailsRow.hidden = !isHidden;
      toggleBtn.textContent = isHidden ? "收起" : "metadata";
      toggleBtn.classList.toggle("active", isHidden);
    });

    fragment.querySelector(".select-work").addEventListener("click", () => selectWork(work));
    candidateList.append(fragment);
  });
  candidateSection.hidden = false;
}

function getSelectedStrategies() {
  const strats = {};
  document.querySelectorAll(".strategy-select").forEach((sel) => {
    const provider = sel.dataset.provider;
    if (provider) {
      strats[provider] = sel.value;
    }
  });
  return strats;
}

function getActiveScoreEnginesList() {
  const engines = [];
  PROVIDERS.forEach((provider) => {
    const suffix = PROVIDER_CHECKBOX_SUFFIX[provider.id];
    const checkbox = document.querySelector(`#score-${suffix}`);
    if (checkbox && checkbox.checked) {
      engines.push(provider.id);
    }
  });
  return engines;
}

async function selectWork(work) {
  currentSelectedWork = work;
  candidateList.querySelectorAll(".candidate-card").forEach((card) => {
    card.classList.remove("selected");
    const btn = card.querySelector(".select-work");
    if (btn) {
      btn.textContent = "Choose";
      btn.disabled = false;
    }
  });

  const selectedCard = candidateList.querySelector(`[data-key="${work.key}"]`);
  if (selectedCard) {
    selectedCard.classList.add("selected");
    const btn = selectedCard.querySelector(".select-work");
    if (btn) {
      btn.textContent = "已選取";
      btn.disabled = true;
    }
  }

  detailsHeading.hidden = false;
  goToStep(3);
  resultBody.replaceChildren();

  const rowFragment = renderInitialWorkRow(work);
  const row = rowFragment.querySelector(".work-row");
  resultBody.append(rowFragment);
  tableWrap.hidden = false;

  step3Status.classList.remove("error");
  step3Status.textContent = "";

  const activeEnginesList = getActiveScoreEnginesList();
  const apiKey = localStorage.getItem("bookrate:google-api-key") || "";
  const strategies = getSelectedStrategies();

  // 區分命中快取與未命中快取
  const cachedEngines = [];
  const pendingEngines = [];

  activeEnginesList.forEach((provider) => {
    const strategy = strategies[provider] || "isbn_primary";
    const cachedData = getRatingCache(work.key, provider, strategy);
    if (cachedData) {
      cachedEngines.push({ provider, data: cachedData });
    } else {
      pendingEngines.push(provider);
    }
  });

  const prefixMap = {
    open_library: "ol",
    goodreads: "gr",
    douban: "db",
    amazon: "am",
    amazon_jp: "amjp",
    storygraph: "sg"
  };

  // 立即渲染已命中的快取
  cachedEngines.forEach(({ provider, data }) => {
    const prefix = prefixMap[provider] || provider;
    const maxRate = prefix === "db" ? 10 : 5;
    renderPlatformCell(row, prefix, data, maxRate);
  });

  try {
    const strategiesStr = JSON.stringify(strategies);
    let url = `/api/work-details-stream?work_id=${encodeURIComponent(work.key)}&title=${encodeURIComponent(work.title)}&author=${encodeURIComponent((work.author_name || []).join(","))}&engines=${encodeURIComponent(pendingEngines.join(","))}&strategies=${encodeURIComponent(strategiesStr)}`;
    if (apiKey) {
      url += `&google_key=${encodeURIComponent(apiKey)}`;
    }

    const collectedDetails = { work, ratings: {}, editions: {}, goodreads: {}, douban: {}, amazon: {}, amazon_jp: {}, storygraph: {} };
    const eventSource = new EventSource(url);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "init") {
          collectedDetails.ratings = data.ratings;
          collectedDetails.editions = data.editions;
          updateWorkDetailRow(row, collectedDetails);
        } else if (data.type === "platform") {
          const platformKey = data.platform;
          collectedDetails[platformKey] = data.data;

          const prefix = prefixMap[platformKey] || platformKey;
          const maxRate = prefix === "db" ? 10 : 5;

          // 寫入評分快取
          const strategy = strategies[platformKey] || "isbn_primary";
          setRatingCache(work.key, platformKey, strategy, data.data);

          renderPlatformCell(row, prefix, data.data, maxRate);
        } else if (data.type === "done") {
          eventSource.close();
          step3Status.textContent = "";
        }
      } catch (err) {
        console.error("Stream parse error:", err);
      }
    };

    eventSource.onerror = (err) => {
      console.error("EventSource failed:", err);
      eventSource.close();
      step3Status.textContent = "";
    };
  } catch (error) {
    console.error(error);
    step3Status.classList.add("error");
    step3Status.textContent = "取得作品詳細評分失敗，請確認網路連線後再試一次。";
  }
}

function reQuerySingleProvider(work, providerKey) {
  const row = resultBody.querySelector(".work-row");
  if (!row) return;

  const prefixMap = {
    open_library: "ol",
    goodreads: "gr",
    douban: "db",
    amazon: "am",
    amazon_jp: "amjp",
    storygraph: "sg"
  };
  const prefix = prefixMap[providerKey] || providerKey;
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
  const strategiesStr = JSON.stringify(strategies);

  let url = `/api/work-details-stream?work_id=${encodeURIComponent(work.key)}&title=${encodeURIComponent(work.title)}&author=${encodeURIComponent((work.author_name || []).join(","))}&engines=${encodeURIComponent(providerKey)}&strategies=${encodeURIComponent(strategiesStr)}`;
  if (apiKey) {
    url += `&google_key=${encodeURIComponent(apiKey)}`;
  }

  const eventSource = new EventSource(url);
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "platform") {
        const maxRate = prefix === "db" ? 10 : 5;

        // 重新查詢寫入評分快取並渲染
        const strategy = strategies[providerKey] || "isbn_primary";
        setRatingCache(work.key, providerKey, strategy, data.data);

        renderPlatformCell(row, prefix, data.data, maxRate);
      } else if (data.type === "done") {
        eventSource.close();
      }
    } catch (err) {
      console.error("Single provider re-query parse error:", err);
    }
  };
  eventSource.onerror = (err) => {
    console.error("Single provider EventSource failed:", err);
    eventSource.close();
  };
}

// Bind strategy select change handler via delegation
const scoreToggleBarEl = document.querySelector("#score-toggle-bar");
if (scoreToggleBarEl) {
  scoreToggleBarEl.addEventListener("change", (e) => {
    if (e.target.classList.contains("strategy-select")) {
      const providerKey = e.target.dataset.provider;
      if (providerKey) {
        localStorage.setItem("bookrate:strategy:" + providerKey, e.target.value);
      }
      if (currentSelectedWork && providerKey) {
        reQuerySingleProvider(currentSelectedWork, providerKey);
      }
    } else if (e.target.type === "checkbox") {
      const id = e.target.id.replace("score-", ""); // 'ol', 'gr' 等
      localStorage.setItem(`bookrate:score:${id}`, e.target.checked);
      updateTableVisibility(ratingTable);
    }
  });
}

function renderCountCell(countEl, countVal, url) {
  const countText = displayCount(countVal);
  if (url) {
    countEl.innerHTML = `<a href="${url}" target="_blank" rel="noreferrer">${countText} ↗</a>`;
  } else {
    countEl.textContent = countText;
  }
}

function renderInitialWorkRow(work) {
  const fragment = resultRowTemplate.content.cloneNode(true);
  const row = fragment.querySelector(".work-row");

  row.querySelector(".work-title").textContent = work.title;

  const authorText = `作者：${(work.author_name || ["Unknown"]).join("、")}`;
  row.querySelector(".info-author").textContent = authorText;

  const publishText = `首版：${work.first_publish_year || "Unknown"}`;
  row.querySelector(".info-publish").textContent = publishText;

  row.querySelector(".edition-count").textContent = "載入中...";

  const prefixes = ["ol", "gr", "db", "am", "amjp", "sg"];
  prefixes.forEach((prefix) => {
    const rateEl = row.querySelector(`.${prefix}-rate`);
    const countEl = row.querySelector(`.${prefix}-count`);
    if (rateEl) rateEl.innerHTML = '<span class="fetching-tag">Fetching...</span>';
    if (countEl) countEl.textContent = "讀取中...";
  });

  return fragment;
}

function renderPlatformCell(row, prefix, data, maxRate = 5) {
  const rateEl = row.querySelector(`.${prefix}-rate`);
  const countEl = row.querySelector(`.${prefix}-count`);

  if (!rateEl || !countEl) return;
  if (!data || Object.keys(data).length === 0) return;

  const hasScore = typeof data.average === "number" && data.average > 0;
  const hasUrl = Boolean(data.url);
  const status = data.status || (hasScore ? "MATCH" : "NO_MATCH");
  const isNetworkError = status && status !== "MATCH" && status !== "NO_MATCH" && status !== "QUOTA_EXCEEDED" && status !== "ERROR";

  // Clear previous elements
  rateEl.replaceChildren();

  let resultText = "";

  if (data.quota_exceeded || status === "QUOTA_EXCEEDED") {
    rateEl.innerHTML = '<span class="error">額度超限 (429) ⚠️</span>';
    countEl.textContent = "請在上方設定個人 API Key，或設定環境變數。";
    resultText = "額度超限 (429)";
  } else if (status === "ERROR") {
    rateEl.innerHTML = '<span class="error">讀取錯誤 ⚠️</span>';
    countEl.textContent = "請檢查主機連線。";
    resultText = "讀取錯誤";
  } else if (isNetworkError) {
    rateEl.innerHTML = '<span class="error">連線異常 ⚠️</span>';
    countEl.textContent = status; // Shows HTTP 503 etc.
    resultText = `連線異常 (${status})`;
  } else if (hasScore) {
    const rateText = displayRate(data.average, data.count, maxRate);
    rateEl.textContent = rateText;
    renderCountCell(countEl, data.count, data.url);
    resultText = `${rateText} (${displayCount(data.count)} 條評價)`;
  } else if (hasUrl) {
    rateEl.textContent = "暫無評分";
    countEl.innerHTML = `<a href="${data.url}" target="_blank" rel="noreferrer">連結 ↗</a>`;
    resultText = "暫無評分 (但有網頁連結)";
  } else {
    rateEl.textContent = "無此書籍";
    countEl.textContent = "-";
    resultText = "無此書籍";
  }

  // Render status tag at the bottom of the td cell
  const cell = rateEl.closest("td");
  if (cell) {
    const oldTag = cell.querySelector(".search-status-tag");
    if (oldTag) oldTag.remove();

    const tag = document.createElement("span");
    tag.className = `search-status-tag status-${status.toLowerCase().replace(/[^a-z0-9_]/g, "-")}`;
    tag.textContent = status;
    tag.dataset.strat = data.strategy || "";
    tag.dataset.query = data.query || "";
    // 用 native tooltip 取代 debug modal
    tag.title = `策略: ${data.strategy || "N/A"}, 查詢: ${data.query || "N/A"}`;

    cell.appendChild(tag);
  }
}

function updateWorkDetailRow(row, { work, ratings, editions }) {
  if (!row) return;

  row.querySelector(".work-title").textContent = work.title;

  const authorText = `作者：${(work.author_name || ["Unknown"]).join("、")}`;
  row.querySelector(".info-author").textContent = authorText;

  const publishText = `首版：${work.first_publish_year || "Unknown"}`;
  row.querySelector(".info-publish").textContent = publishText;

  // 1. 版本數量與 editions modal
  const size = work.edition_count || editions?.size || editions?.entries?.length || 0;
  row.querySelector(".edition-count").textContent = `${size.toLocaleString()}個版本`;

  const btn = row.querySelector(".show-editions-btn");
  if (btn) {
    btn.onclick = () => {
      openEditionsModal(work.title, editions);
    };
  }

  // 2. 填寫 metadata 展開內容
  let reprIsbn = "Unknown";
  let otherIsbnsText = "無";
  if (editions?.entries) {
    const isbns = [];
    editions.entries.forEach(ed => {
      const isbnVal = ed.isbn_13 || ed.isbn_10;
      if (isbnVal && !isbns.includes(isbnVal)) {
        isbns.push(isbnVal);
      }
    });
    if (isbns.length > 0) {
      reprIsbn = isbns[0];
      const remaining = isbns.slice(1, 11);
      if (remaining.length > 0) {
        otherIsbnsText = remaining.join("、");
      }
    }
  } else if (work.isbn) {
    const isbnList = Array.isArray(work.isbn) ? work.isbn : [work.isbn];
    if (isbnList.length > 0) {
      reprIsbn = isbnList[0];
      const remaining = isbnList.slice(1, 11);
      if (remaining.length > 0) {
        otherIsbnsText = remaining.join("、");
      }
    }
  }
  row.querySelector(".step3-primary-isbn").textContent = reprIsbn;
  row.querySelector(".step3-other-isbns").textContent = otherIsbnsText;

  // 外部連結：
  const linksContainer = row.querySelector(".step3-links");
  linksContainer.replaceChildren();
  const extUrl = getWorkExternalUrl(work.key);
  if (extUrl) {
    const a = document.createElement("a");
    a.href = extUrl;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = `${getProviderDisplayName(work.key.split(":")[0]) || "外部連結"} ↗`;
    linksContainer.appendChild(a);
  } else {
    linksContainer.textContent = "-";
  }

  // 綁定 metadata 展開按鈕事件
  const toggleBtn = row.querySelector(".toggle-metadata-btn");
  const detailsBlock = row.querySelector(".step3-metadata-details");
  if (toggleBtn && detailsBlock) {
    toggleBtn.onclick = (e) => {
      e.stopPropagation();
      const isHidden = detailsBlock.hidden;
      detailsBlock.hidden = !isHidden;
      toggleBtn.textContent = isHidden ? "收起" : "metadata";
      toggleBtn.classList.toggle("active", isHidden);
    };
  }

  // 3. 渲染 Open Library 評分
  const olUrl = ratings?.url || ((work.key && work.key.startsWith("/works/")) ? `${OPEN_LIBRARY_BASE_URL}${work.key}` : null);
  renderPlatformCell(row, "ol", { average: ratings?.average, count: ratings?.count, url: olUrl, status: (ratings?.average ? "MATCH" : "NO_MATCH") }, 5);
}

function updateManualSearchLinks(query) {
  const isbndbLink = document.querySelector("#manual-isbndb-link");
  const isbnsearchLink = document.querySelector("#manual-isbnsearch-link");
  const amazonLink = document.querySelector("#manual-amazon-link");

  const q = (query || "").trim();
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

function updateEngineTabs(engine) {
  const searchOlBtn = document.querySelector("#search-ol-btn");
  const searchGrBtn = document.querySelector("#search-gr-btn");
  const searchGbBtn = document.querySelector("#search-gb-btn");
  const searchDbBtn = document.querySelector("#search-db-btn");
  const searchAmjpBtn = document.querySelector("#search-amjp-btn");
  const searchSgBtn = document.querySelector("#search-sg-btn");

  if (searchOlBtn) searchOlBtn.classList.toggle("active", engine === "open_library");
  if (searchGrBtn) searchGrBtn.classList.toggle("active", engine === "goodreads");
  if (searchGbBtn) searchGbBtn.classList.toggle("active", engine === "google_books");
  if (searchDbBtn) searchDbBtn.classList.toggle("active", engine === "douban");
  if (searchAmjpBtn) searchAmjpBtn.classList.toggle("active", engine === "amazon_jp");
  if (searchSgBtn) searchSgBtn.classList.toggle("active", engine === "storygraph");
}

async function searchWorks(query, page, engine = "open_library") {
  currentQuery = query;
  currentPage = page;
  currentEngine = engine;
  candidateSection.hidden = false;
  candidateHeading.hidden = false;
  goToStep(2);
  updateEngineTabs(engine);

  const engineNameMap = {
    open_library: "Open Library",
    goodreads: "Goodreads",
    google_books: "Google Books",
    douban: "豆瓣",
    amazon_jp: "Amazon JP",
    storygraph: "StoryGraph"
  };
  const engineName = engineNameMap[engine] || "資料庫";

  candidateList.replaceChildren();
  const loadingEl = document.createElement("div");
  loadingEl.className = "no-results loading";
  loadingEl.textContent = `載入中… 正在使用 ${engineName} 尋找「${query}」`;
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
  }

  try {
    const cacheKey = `search:${query}:page:${page}:engines:${engine}`;
    let works = getCachedData(cacheKey);
    if (!works) {
      let url = `/api/search?q=${encodeURIComponent(query)}&page=${page}&engines=${encodeURIComponent(engine)}`;
      const apiKey = localStorage.getItem("bookrate:google-api-key") || "";
      if (apiKey) {
        url += `&google_key=${encodeURIComponent(apiKey)}`;
      }
      works = await fetchJson(url);
      if (works && works.length > 0) {
        setCachedData(cacheKey, works);
      }
    }

    if (!works || !works.length) {
      step2Status.textContent = "";
      if (page === 1) {
        paginationControls.hidden = true;
        candidateList.replaceChildren();
        const noResultsEl = document.createElement("div");
        noResultsEl.className = "no-results";
        noResultsEl.textContent = `${engineName} 找不到「${query}」`;
        candidateList.append(noResultsEl);
      } else {
        paginationControls.hidden = false;
        pageIndicator.textContent = `第 ${currentPage} 頁`;
        prevPageBtn.disabled = false;
        nextPageBtn.disabled = true;
      }
      return;
    }

    renderCandidates(works);
    candidateHeading.hidden = false;
    updatePagination(works.length);
    step2Status.textContent = "";
  } catch (error) {
    console.error(error);
    step2Status.classList.add("error");
    step2Status.textContent = "查詢失敗，請確認網路連線後再試一次。";
  }
}

searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = searchInput.value.trim();
  if (!query) return;
  searchWorks(query, 1, "open_library");
});

const searchOlBtn = document.querySelector("#search-ol-btn");
const searchGrBtn = document.querySelector("#search-gr-btn");
const searchGbBtn = document.querySelector("#search-gb-btn");
const searchDbBtn = document.querySelector("#search-db-btn");
const searchAmjpBtn = document.querySelector("#search-amjp-btn");
const searchSgBtn = document.querySelector("#search-sg-btn");

if (searchOlBtn) {
  searchOlBtn.addEventListener("click", () => {
    const q = searchInput.value.trim() || currentQuery;
    if (q) {
      searchWorks(q, 1, "open_library");
    }
  });
}

if (searchGrBtn) {
  searchGrBtn.addEventListener("click", () => {
    const q = searchInput.value.trim() || currentQuery;
    if (q) {
      searchWorks(q, 1, "goodreads");
    }
  });
}

if (searchGbBtn) {
  searchGbBtn.addEventListener("click", () => {
    const q = searchInput.value.trim() || currentQuery;
    if (q) {
      searchWorks(q, 1, "google_books");
    }
  });
}

if (searchDbBtn) {
  searchDbBtn.addEventListener("click", () => {
    const q = searchInput.value.trim() || currentQuery;
    if (q) {
      searchWorks(q, 1, "douban");
    }
  });
}

if (searchAmjpBtn) {
  searchAmjpBtn.addEventListener("click", () => {
    const q = searchInput.value.trim() || currentQuery;
    if (q) {
      searchWorks(q, 1, "amazon_jp");
    }
  });
}

if (searchSgBtn) {
  searchSgBtn.addEventListener("click", () => {
    const q = searchInput.value.trim() || currentQuery;
    if (q) {
      searchWorks(q, 1, "storygraph");
    }
  });
}

function updatePagination(itemsCount) {
  if (!currentQuery) {
    paginationControls.hidden = true;
    return;
  }
  if (currentPage === 1 && itemsCount < MAX_CANDIDATES) {
    paginationControls.hidden = true;
    return;
  }
  paginationControls.hidden = false;
  pageIndicator.textContent = `第 ${currentPage} 頁`;
  prevPageBtn.disabled = currentPage === 1;
  nextPageBtn.disabled = itemsCount < MAX_CANDIDATES;
}

prevPageBtn.addEventListener("click", () => {
  if (currentPage > 1) {
    searchWorks(currentQuery, currentPage - 1, currentEngine);
  }
});

nextPageBtn.addEventListener("click", () => {
  searchWorks(currentQuery, currentPage + 1, currentEngine);
});

renderHistory();

// Google Books API Key settings logic
const apiKeyInput = document.querySelector("#google-api-key");
const saveApiKeyBtn = document.querySelector("#save-api-key-btn");
const clearApiKeyBtn = document.querySelector("#clear-api-key-btn");
const GOOGLE_KEY_STORAGE_KEY = "bookrate:google-api-key";

// Initialise API key input
const savedKey = localStorage.getItem(GOOGLE_KEY_STORAGE_KEY) || "";
if (apiKeyInput) {
  apiKeyInput.value = savedKey;
  if (savedKey) {
    apiKeyInput.placeholder = "已儲存 API 金鑰 (已遮蔽)";
  }
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

// Settings checkboxes logic
function initSettings() {
  renderProviderToggles(scoreToggleBarEl);

  PROVIDERS.forEach((provider) => {
    const suffix = PROVIDER_CHECKBOX_SUFFIX[provider.id];
    const checkbox = document.querySelector(`#score-${suffix}`);
    if (checkbox) {
      checkbox.checked = localStorage.getItem(`bookrate:score:${suffix}`) !== "false";
    }

    const select = document.querySelector(`.strategy-select[data-provider="${provider.id}"]`);
    if (select) {
      const savedStrategy = localStorage.getItem("bookrate:strategy:" + provider.id);
      select.value = savedStrategy || provider.defaultStrategy;
    }
  });

  updateTableVisibility(ratingTable);
}

initSettings();

// Auto-close settings details when clicking outside of it
const settingsDetails = document.querySelector(".settings-details");
if (settingsDetails) {
  document.addEventListener("click", (event) => {
    if (settingsDetails.open && !settingsDetails.contains(event.target)) {
      settingsDetails.removeAttribute("open");
    }
  });
}

btnPrevTo1.addEventListener("click", () => {
  goToStep(1);
  step2Status.textContent = "";
  step2Status.classList.remove("error");
});

btnPrevTo2.addEventListener("click", () => {
  goToStep(2);
  step3Status.textContent = "";
  step3Status.classList.remove("error");
  candidateList.querySelectorAll(".candidate-card").forEach((card) => {
    card.classList.remove("selected");
    const btn = card.querySelector(".select-work");
    if (btn) {
      btn.textContent = "Choose";
      btn.disabled = false;
    }
  });
});

const clearCacheBtn = document.querySelector("#clear-cache-btn");
if (clearCacheBtn) {
  clearCacheBtn.addEventListener("click", () => {
    // Clear all localStorage cache keys starting with bookrate:cache: or bookrate:rating:
    const keysToRemove = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && (key.startsWith("bookrate:cache:") || key.startsWith("bookrate:rating:"))) {
        keysToRemove.push(key);
      }
    }
    keysToRemove.forEach((k) => localStorage.removeItem(k));
    alert("快取已清除！");
  });
}

// Presets Modal logic
const presetsModal = document.querySelector("#presets-modal");
const openPresetsBtn = document.querySelector("#open-presets-btn");
const closePresetsBtn = document.querySelector("#close-presets-btn");
const presetsTableBody = document.querySelector("#presets-table-body");
let cachedPresets = null;

async function loadPresets() {
  if (cachedPresets) return cachedPresets;
  try {
    const res = await fetch("./presets.json?t=" + new Date().getTime());
    if (!res.ok) throw new Error("Failed to load presets");
    cachedPresets = await res.json();
    return cachedPresets;
  } catch (e) {
    console.error(e);
    return [];
  }
}

function renderPresetsTable(presets, closeModalFn) {
  if (!presetsTableBody) return;
  const fragment = document.createDocumentFragment();
  (presets || []).forEach((item) => {
    const tr = document.createElement("tr");

    const tdTitle = document.createElement("td");
    tdTitle.className = "clickable-preset";
    tdTitle.dataset.query = item.title || "";
    tdTitle.textContent = item.title || "";

    const tdIsbn = document.createElement("td");
    tdIsbn.className = "clickable-preset";
    tdIsbn.dataset.query = item.isbn || "";
    tdIsbn.textContent = item.isbn || "";

    const selectPreset = (q) => {
      if (q && searchInput) {
        searchInput.value = q;
      }
      closeModalFn();
    };

    tdTitle.addEventListener("click", () => selectPreset(item.title));
    tdIsbn.addEventListener("click", () => selectPreset(item.isbn));

    tr.append(tdTitle, tdIsbn);
    fragment.append(tr);
  });
  presetsTableBody.replaceChildren(fragment);
}

if (presetsModal && openPresetsBtn && closePresetsBtn) {
  const closeModal = () => {
    presetsModal.classList.remove("open");
    setTimeout(() => {
      if (!presetsModal.classList.contains("open")) {
        presetsModal.hidden = true;
      }
    }, 300);
  };

  openPresetsBtn.addEventListener("click", async () => {
    const presets = await loadPresets();
    renderPresetsTable(presets, closeModal);
    presetsModal.hidden = false;
    setTimeout(() => presetsModal.classList.add("open"), 10);
  });

  closePresetsBtn.addEventListener("click", closeModal);

  presetsModal.addEventListener("click", (event) => {
    if (event.target === presetsModal) {
      closeModal();
    }
  });
}

// Editions Modal logic
const editionsModal = document.querySelector("#editions-modal");
const closeEditionsBtn = document.querySelector("#close-editions-btn");

if (editionsModal && closeEditionsBtn) {
  const closeEditions = () => {
    editionsModal.classList.remove("open");
    setTimeout(() => {
      if (!editionsModal.classList.contains("open")) {
        editionsModal.hidden = true;
      }
    }, 300);
  };

  closeEditionsBtn.addEventListener("click", closeEditions);

  editionsModal.addEventListener("click", (event) => {
    if (event.target === editionsModal) {
      closeEditions();
    }
  });
}

// Platform Info Modal logic (dynamic load from platform_info.html)
const openPlatformInfoBtn = document.querySelector("#open-platform-info-btn");

if (openPlatformInfoBtn) {
  openPlatformInfoBtn.addEventListener("click", async () => {
    let platformInfoModal = document.querySelector("#platform-info-modal");

    if (!platformInfoModal) {
      try {
        const resp = await fetch("./platform_info.html");
        if (resp.ok) {
          const htmlText = await resp.text();
          const tempDiv = document.createElement("div");
          tempDiv.innerHTML = htmlText;
          platformInfoModal = tempDiv.firstElementChild;
          document.body.appendChild(platformInfoModal);

          const closeBtn = platformInfoModal.querySelector("#close-platform-info-btn");
          const closeModal = () => {
            platformInfoModal.classList.remove("open");
            setTimeout(() => {
              if (!platformInfoModal.classList.contains("open")) {
                platformInfoModal.hidden = true;
              }
            }, 300);
          };

          if (closeBtn) {
            closeBtn.addEventListener("click", closeModal);
          }
          platformInfoModal.addEventListener("click", (e) => {
            if (e.target === platformInfoModal) {
              closeModal();
            }
          });
        }
      } catch (err) {
        console.error("Failed to load platform_info.html:", err);
      }
    }

    if (platformInfoModal) {
      platformInfoModal.hidden = false;
      setTimeout(() => platformInfoModal.classList.add("open"), 10);
    }
  });
}
