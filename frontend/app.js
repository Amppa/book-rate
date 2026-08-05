import { OPEN_LIBRARY_BASE_URL, MAX_CANDIDATES, HISTORY_KEY, PROVIDERS, STRATEGIES, PROVIDER_CHECKBOX_SUFFIX, PROVIDER_PREFIX } from './js/constants.js';
import { getCachedData, setCachedData, getRatingCache, setRatingCache, cleanExpiredCache } from './js/cache.js';
import { fetchJson, displayRate, displayCount, getWorkExternalUrl, getProviderDisplayName } from './js/utils.js';
import { renderProviderToggles, renderStrategySelects, updateTableVisibility, openEditionsModal, renderTableHeaders, renderTitleProviderTabs, initTableVisibilityStyles } from './js/ui.js';

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
let currentTitleProvider = "open_library";
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

function getShortStatus(status) {
  if (!status || status === "Normal") return null;

  const lower = status.toLowerCase();

  // Successful failover
  if (lower.includes("successfully")) {
    return { text: "failover", type: "warning" };
  }

  // HTTP status codes (e.g. HTTP 403)
  const httpMatch = status.match(/HTTP\s+(\d+)/i) || status.match(/\b(403|404|503|500|429)\b/);
  if (httpMatch) {
    const code = httpMatch[1];
    if (code === "403") {
      return { text: "403", type: "error" };
    }
    return { text: `HTTP ${code}`, type: "error" };
  }

  if (lower.includes("waf") || lower.includes("challenge")) {
    return { text: "WAF fail", type: "error" };
  }

  if (lower.includes("error") || lower.includes("failed")) {
    return { text: "error", type: "error" };
  }

  return { text: status, type: "info" };
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

    const authorText = `作者：${(work.author_name || ["Unknown"]).join("、")}`;
    const publishText = work.first_publish_year
      ? `首版 ${work.first_publish_year}`
      : "";

    let editionText = work.edition_count
      ? `${work.edition_count.toLocaleString()} 個版本`
      : "";

    const statusTag = fragment.querySelector(".candidate-status-tag");
    if (statusTag && work.key && (work.key.startsWith("gr:") || work.key.startsWith("sg:")) && work.status) {
      const shortInfo = getShortStatus(work.status);
      if (shortInfo) {
        statusTag.textContent = shortInfo.text;
        statusTag.title = work.status; // Full detailed message as tooltip
        statusTag.hidden = false;
        statusTag.className = `candidate-status-tag status-tag-${shortInfo.type}`;
      } else {
        statusTag.hidden = true;
      }
    }

    const metaText = [
      authorText,
      publishText,
      editionText
    ].filter(Boolean).join(" · ") + " ↗";

    const metaLink = fragment.querySelector(".candidate-meta");
    const extUrl = getWorkExternalUrl(work.key);
    if (metaLink) {
      metaLink.textContent = metaText;
      if (extUrl) {
        metaLink.href = extUrl;
      } else {
        metaLink.removeAttribute("href");
      }
    }

    fragment.querySelector(".select-work").addEventListener("click", () => chooseCandidate(work));
    candidateList.append(fragment);
  });
  candidateSection.hidden = false;
}

function chooseCandidate(work) {
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

  const titleEl = document.querySelector("#bm-title");
  const authorEl = document.querySelector("#bm-author");
  const publishDateEl = document.querySelector("#bm-publish-date");
  const isbnEl = document.querySelector("#bm-isbn");

  if (titleEl) titleEl.value = work.title || "";
  if (authorEl) authorEl.value = (work.author_name || []).join(", ") || "";
  if (publishDateEl) publishDateEl.value = work.first_publish_year || "";
  if (isbnEl) isbnEl.value = work.isbn || "";
}

function confirmToStep3() {
  const titleVal = document.querySelector("#bm-title")?.value.trim() || "";
  const authorVal = document.querySelector("#bm-author")?.value.trim() || "";
  const publishDateVal = document.querySelector("#bm-publish-date")?.value.trim() || "";
  const isbnVal = document.querySelector("#bm-isbn")?.value.trim() || "";

  if (!titleVal) {
    alert("請先選取書籍或輸入書名！");
    return;
  }

  let workToUse = currentSelectedWork;
  if (!workToUse) {
    workToUse = {
      key: "custom:" + Date.now(),
      title: titleVal,
      author_name: authorVal ? [authorVal] : ["Unknown"],
      first_publish_year: publishDateVal,
      isbn: isbnVal
    };
  } else {
    workToUse = {
      ...workToUse,
      title: titleVal,
      author_name: authorVal ? authorVal.split(",").map((s) => s.trim()) : workToUse.author_name,
      first_publish_year: publishDateVal || workToUse.first_publish_year,
      isbn: isbnVal || workToUse.isbn
    };
  }

  selectWork(workToUse);
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

function getActiveRateProvidersList() {
  const rateProviders = [];
  PROVIDERS.forEach((provider) => {
    const suffix = PROVIDER_CHECKBOX_SUFFIX[provider.id];
    const checkbox = document.querySelector(`#score-${suffix}`);
    if (checkbox && checkbox.checked) {
      rateProviders.push(provider.id);
    }
  });
  return rateProviders;
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

  const activeRateProvidersList = getActiveRateProvidersList();
  const apiKey = localStorage.getItem("bookrate:google-api-key") || "";
  const strategies = getSelectedStrategies();

  // 區分命中快取與未命中快取
  const cachedRateProviders = [];
  const pendingRateProviders = [];

  activeRateProvidersList.forEach((provider) => {
    const strategy = strategies[provider] || "isbn_primary";
    const cachedData = getRatingCache(work.key, provider, strategy);
    if (cachedData) {
      cachedRateProviders.push({ provider, data: cachedData });
    } else {
      pendingRateProviders.push(provider);
    }
  });

  // 立即渲染已命中的快取
  cachedRateProviders.forEach(({ provider, data }) => {
    const prefix = PROVIDER_PREFIX[provider] || provider;
    const maxRate = prefix === "db" ? 10 : 5;
    renderPlatformCell(row, prefix, data, maxRate);
  });

  try {
    const strategiesStr = JSON.stringify(strategies);
    let url = `/api/work-details-stream?work_id=${encodeURIComponent(work.key)}&title=${encodeURIComponent(work.title)}&author=${encodeURIComponent((work.author_name || []).join(","))}&engines=${encodeURIComponent(pendingRateProviders.join(","))}&strategies=${encodeURIComponent(strategiesStr)}`;
    if (apiKey) {
      url += `&google_key=${encodeURIComponent(apiKey)}`;
    }

    const collectedDetails = { work, ratings: {}, editions: {} };
    PROVIDERS.forEach((provider) => {
      collectedDetails[provider.id] = {};
    });
    const eventSource = new EventSource(url);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "init") {
          collectedDetails.ratings = data.ratings;
          collectedDetails.editions = data.editions;
          collectedDetails.crawler_status = data.crawler_status;
          updateWorkDetailRow(row, collectedDetails, strategies);
        } else if (data.type === "platform") {
          const platformKey = data.platform;
          collectedDetails[platformKey] = data.data;

          const prefix = PROVIDER_PREFIX[platformKey] || platformKey;
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

  const prefix = PROVIDER_PREFIX[providerKey] || providerKey;
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
const scoreStrategyRowEl = document.querySelector("#score-strategy-row");

if (scoreToggleBarEl) {
  scoreToggleBarEl.addEventListener("change", (e) => {
    if (e.target.type === "checkbox") {
      const id = e.target.id.replace("score-", "");
      localStorage.setItem(`bookrate:score:${id}`, e.target.checked);
      updateTableVisibility(ratingTable);
    }
  });
}

if (scoreStrategyRowEl) {
  scoreStrategyRowEl.addEventListener("change", (e) => {
    if (e.target.classList.contains("strategy-select")) {
      const providerKey = e.target.dataset.provider;
      if (providerKey) {
        localStorage.setItem("bookrate:strategy:" + providerKey, e.target.value);
      }
      if (currentSelectedWork && providerKey) {
        reQuerySingleProvider(currentSelectedWork, providerKey);
      }
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

  PROVIDERS.forEach((provider) => {
    const suffix = PROVIDER_CHECKBOX_SUFFIX[provider.id];
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

function updateWorkDetailRow(row, { work, ratings, editions, crawler_status }, strategies) {
  if (!row) return;

  row.querySelector(".work-title").textContent = work.title;

  const authorText = `作者：${(work.author_name || ["Unknown"]).join("、")}`;
  row.querySelector(".info-author").textContent = authorText;

  const publishText = `首版：${work.first_publish_year || "Unknown"}`;
  row.querySelector(".info-publish").textContent = publishText;

  // 1. 版本數量與 editions modal
  const size = work.edition_count || editions?.size || editions?.entries?.length || 0;
  row.querySelector(".edition-count").textContent = `${size.toLocaleString()}個版本`;

  const statusEl = row.querySelector(".step3-crawler-status");
  if (statusEl) {
    if (crawler_status && Object.keys(crawler_status).length > 0) {
      statusEl.textContent = Object.entries(crawler_status)
        .map(([k, v]) => `${k}: ${v}`)
        .join(" | ");
    } else {
      statusEl.textContent = "正常";
    }
  }

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
        if (isbns.length > 11) {
          otherIsbnsText += " ...";
        }
      }
    }
  } else if (work.isbn) {
    const isbnList = Array.isArray(work.isbn) ? work.isbn : [work.isbn];
    if (isbnList.length > 0) {
      reprIsbn = isbnList[0];
      const remaining = isbnList.slice(1, 11);
      if (remaining.length > 0) {
        otherIsbnsText = remaining.join("、");
        if (isbnList.length > 11) {
          otherIsbnsText += " ...";
        }
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
      toggleBtn.classList.toggle("active", isHidden);
    };
  }

  // 3. 渲染 Open Library 評分
  const olUrl = ratings?.url || ((work.key && work.key.startsWith("/works/")) ? `${OPEN_LIBRARY_BASE_URL}${work.key}` : null);
  const olData = { average: ratings?.average, count: ratings?.count, url: olUrl, status: (ratings?.average ? "MATCH" : "NO_MATCH") };
  renderPlatformCell(row, "ol", olData, 5);

  // 寫入快取
  if (strategies) {
    const olStrategy = strategies.open_library || "title_author";
    setRatingCache(work.key, "open_library", olStrategy, olData);
  }
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

function updateTitleProviderTabs(titleProvider) {
  const tabsContainer = document.querySelector("#title-provider-tabs-container");
  if (tabsContainer) {
    tabsContainer.querySelectorAll(".title-provider-tab-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.providerId === titleProvider);
    });
  }
}

async function searchWorks(query, page, titleProvider = "open_library") {
  currentQuery = query;
  currentPage = page;
  currentTitleProvider = titleProvider;
  candidateSection.hidden = false;
  candidateHeading.hidden = false;
  goToStep(2);
  updateTitleProviderTabs(titleProvider);

  const providerObj = PROVIDERS.find(p => p.id === titleProvider);
  const titleProviderName = providerObj ? providerObj.label : "資料庫";

  candidateList.replaceChildren();
  const loadingEl = document.createElement("div");
  loadingEl.className = "no-results loading";
  loadingEl.textContent = `載入中… 正在使用 ${titleProviderName} 尋找「${query}」`;
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
    const titleEl = document.querySelector("#bm-title");
    const authorEl = document.querySelector("#bm-author");
    const publishDateEl = document.querySelector("#bm-publish-date");
    const isbnEl = document.querySelector("#bm-isbn");
    if (titleEl) titleEl.value = query;
    if (authorEl) authorEl.value = "";
    if (publishDateEl) publishDateEl.value = "";
    if (isbnEl) isbnEl.value = "";
    currentSelectedWork = null;
  }

  try {
    const cacheKey = `search:${query}:page:${page}:engines:${titleProvider}`;
    let works = getCachedData(cacheKey);
    if (!works) {
      let url = `/api/search?q=${encodeURIComponent(query)}&page=${page}&engines=${encodeURIComponent(titleProvider)}`;
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
        noResultsEl.textContent = `${titleProviderName} 找不到「${query}」`;
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

const tabsContainer = document.querySelector("#title-provider-tabs-container");
if (tabsContainer) {
  tabsContainer.addEventListener("click", (e) => {
    const btn = e.target.closest(".title-provider-tab-btn");
    if (btn) {
      const providerId = btn.dataset.providerId;
      const q = searchInput.value.trim() || currentQuery;
      if (q && providerId) {
        searchWorks(q, 1, providerId);
      }
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
    searchWorks(currentQuery, currentPage - 1, currentTitleProvider);
  }
});

nextPageBtn.addEventListener("click", () => {
  searchWorks(currentQuery, currentPage + 1, currentTitleProvider);
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
  initTableVisibilityStyles();
  renderTableHeaders(document.querySelector("#table-header-row"));
  renderTitleProviderTabs(document.querySelector("#title-provider-tabs-container"), currentTitleProvider);

  renderProviderToggles(scoreToggleBarEl);
  renderStrategySelects(scoreStrategyRowEl);

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
});

const btnConfirmTo3 = document.querySelector("#btn-confirm-to-3");
if (btnConfirmTo3) {
  btnConfirmTo3.addEventListener("click", confirmToStep3);
}

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
