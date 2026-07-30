const OPEN_LIBRARY_BASE_URL = "https://openlibrary.org";
const MAX_CANDIDATES = 10;
const MAX_EDITIONS = 100;
const HISTORY_KEY = "bookrate:recent-searches";
const CACHE_PREFIX = "bookrate:cache:";
const ONE_DAY_MS = 24 * 60 * 60 * 1000;

// Settings selectors & storage keys
const scoreOlCheckbox = document.querySelector("#score-ol");
const scoreGbCheckbox = document.querySelector("#score-gb");
const scoreGrCheckbox = document.querySelector("#score-gr");
const scoreDbCheckbox = document.querySelector("#score-db");
const scoreAmCheckbox = document.querySelector("#score-am");
const ratingTable = document.querySelector("table");

const SCORE_OL_KEY = "bookrate:score:ol";
const SCORE_GB_KEY = "bookrate:score:gb";
const SCORE_GR_KEY = "bookrate:score:gr";
const SCORE_DB_KEY = "bookrate:score:db";
const SCORE_AM_KEY = "bookrate:score:am";

function getCachedData(key) {
  try {
    const cached = localStorage.getItem(CACHE_PREFIX + key);
    if (!cached) return null;
    const { data, timestamp } = JSON.parse(cached);
    if (Date.now() - timestamp > ONE_DAY_MS) {
      localStorage.removeItem(CACHE_PREFIX + key);
      return null;
    }
    return data;
  } catch (e) {
    return null;
  }
}

function setCachedData(key, data) {
  try {
    const record = { data, timestamp: Date.now() };
    localStorage.setItem(CACHE_PREFIX + key, JSON.stringify(record));
  } catch (e) {
    console.warn("Failed to write to localStorage cache:", e);
  }
}

function cleanExpiredCache() {
  try {
    const keysToRemove = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith(CACHE_PREFIX)) {
        const cached = localStorage.getItem(key);
        if (cached) {
          const { timestamp } = JSON.parse(cached);
          if (Date.now() - timestamp > ONE_DAY_MS) {
            keysToRemove.push(key);
          }
        }
      }
    }
    keysToRemove.forEach((key) => localStorage.removeItem(key));
  } catch (e) { }
}

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

let currentQuery = "";
let currentPage = 1;
let currentStep = 1;
let currentEngine = "open_library";

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

function fetchJson(url) {
  return fetch(url).then(async (response) => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  });
}

function displayRate(average, count, maxScore = 5) {
  return Number(count) > 0 && Number(average) > 0
    ? `${Number(average).toFixed(2)} / ${maxScore}`
    : "暫無評分";
}

function formatCompact(n) {
  return new Intl.NumberFormat("en", {
    notation: "compact",
    maximumFractionDigits: 1
  }).format(n);
}

function displayCount(count) {
  return Number(count) > 0
    ? `${formatCompact(Number(count))} 人評價`
    : "NULL";
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

function getWorkExternalUrl(key) {
  if (!key) return null;
  if (key.startsWith("/works/")) return `${OPEN_LIBRARY_BASE_URL}${key}`;
  if (key.startsWith("gb:")) return `https://books.google.com/books?id=${key.slice(3)}`;
  if (key.startsWith("gr:")) return `https://www.goodreads.com/book/show/${key.slice(3)}`;
  if (key.startsWith("db:")) return `https://book.douban.com/subject/${key.slice(3)}/`;
  return null;
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
    const editionText = work.edition_count
      ? `${work.edition_count.toLocaleString()} 個版本`
      : "";

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

    fragment.querySelector(".select-work").addEventListener("click", () => selectWork(work));
    candidateList.append(fragment);
  });
  candidateSection.hidden = false;
}

async function selectWork(work) {
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

  // Render initial placeholder row showing "Fetching..." while loading
  const initialFragment = renderInitialWorkRow(work);
  resultBody.append(initialFragment);
  tableWrap.hidden = false;
  step3Status.classList.remove("error");
  step3Status.textContent = `正在取得《${work.title}》的版本與評分…`;

  try {
    const apiKey = localStorage.getItem("bookrate:google-api-key") || "";
    const cacheKey = `work:${work.key}`;
    let details = getCachedData(cacheKey);

    if (details && details.google?.quota_exceeded && apiKey) {
      details = null;
    }

    if (!details) {
      let url = `/api/work-details?work_id=${encodeURIComponent(work.key)}&title=${encodeURIComponent(work.title)}&author=${encodeURIComponent((work.author_name || []).join(","))}`;
      if (apiKey) {
        url += `&google_key=${encodeURIComponent(apiKey)}`;
      }
      details = await fetchJson(url);
      setCachedData(cacheKey, details);
    }

    details.work = work;
    updateWorkDetailRow(resultBody.querySelector(".work-row"), details);
    step3Status.textContent = "";
  } catch (error) {
    console.error(error);
    step3Status.classList.add("error");
    step3Status.textContent = "取得作品詳細評分失敗，請確認網路連線後再試一次。";
    const row = resultBody.querySelector(".work-row");
    if (row) {
      row.querySelectorAll(".ol-rate, .gb-rate, .gr-rate, .db-rate").forEach(el => {
        el.textContent = "暫無評分";
      });
      row.querySelectorAll(".ol-count, .gb-count, .gr-count, .db-count").forEach(el => {
        el.textContent = "讀取失敗";
      });
    }
  }
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

  if (work.isbn) {
    row.querySelector(".info-isbn").textContent = `ISBN：${work.isbn}`;
  } else {
    row.querySelector(".info-isbn").textContent = "ISBN：讀取中...";
  }

  if (work.edition_count) {
    row.querySelector(".edition-count").textContent = `${work.edition_count.toLocaleString()}個版本`;
  } else {
    row.querySelector(".edition-count").textContent = "載入中...";
  }

  row.querySelector(".ol-rate").innerHTML = '<span class="fetching-tag">Fetching...</span>';
  row.querySelector(".ol-count").textContent = "讀取中...";

  row.querySelector(".gb-rate").innerHTML = '<span class="fetching-tag">Fetching...</span>';
  row.querySelector(".gb-count").textContent = "讀取中...";

  row.querySelector(".gr-rate").innerHTML = '<span class="fetching-tag">Fetching...</span>';
  row.querySelector(".gr-count").textContent = "讀取中...";

  row.querySelector(".db-rate").innerHTML = '<span class="fetching-tag">Fetching...</span>';
  row.querySelector(".db-count").textContent = "讀取中...";

  row.querySelector(".am-rate").innerHTML = '<span class="fetching-tag">Fetching...</span>';
  row.querySelector(".am-count").textContent = "讀取中...";

  return fragment;
}

function renderPlatformCell(row, prefix, data, maxRate = 5) {
  const rateEl = row.querySelector(`.${prefix}-rate`);
  const countEl = row.querySelector(`.${prefix}-count`);

  if (!rateEl || !countEl) return;

  const hasScore = data && typeof data.average === "number" && data.average > 0;
  const hasUrl = data && Boolean(data.url);

  if (hasScore) {
    rateEl.textContent = displayRate(data.average, data.count, maxRate);
    renderCountCell(countEl, data.count, data.url);
  } else if (hasUrl) {
    rateEl.textContent = "暫無評分";
    countEl.innerHTML = `<a href="${data.url}" target="_blank" rel="noreferrer">連結 ↗</a>`;
  } else {
    rateEl.textContent = "無此書籍";
    countEl.textContent = "-";
  }
}

function updateWorkDetailRow(row, { work, ratings, editions, google, goodreads, douban, amazon }) {
  if (!row) return;

  row.querySelector(".work-title").textContent = work.title;

  const authorText = `作者：${(work.author_name || ["Unknown"]).join("、")}`;
  row.querySelector(".info-author").textContent = authorText;

  const publishText = `首版：${work.first_publish_year || "Unknown"}`;
  row.querySelector(".info-publish").textContent = publishText;

  let reprIsbn = "ISBN：Unknown";
  if (editions?.entries) {
    const editionWithIsbn = editions.entries.find(ed => ed.isbn_13 || ed.isbn_10);
    if (editionWithIsbn) {
      reprIsbn = `ISBN：${editionWithIsbn.isbn_13 || editionWithIsbn.isbn_10}`;
    }
  }
  row.querySelector(".info-isbn").textContent = reprIsbn;

  const olUrl = (work.key && work.key.startsWith("/works/")) ? `${OPEN_LIBRARY_BASE_URL}${work.key}` : null;
  renderPlatformCell(row, "ol", { average: ratings?.average, count: ratings?.count, url: olUrl }, 5);

  if (google?.quota_exceeded) {
    row.querySelector(".gb-rate").innerHTML = '<span class="error">額度超限 (429) ⚠️</span>';
    row.querySelector(".gb-count").textContent = "請在上方設定個人 API Key，或設定環境變數。";
  } else {
    renderPlatformCell(row, "gb", google, 5);
  }

  renderPlatformCell(row, "gr", goodreads, 5);
  renderPlatformCell(row, "db", douban, 10);
  renderPlatformCell(row, "am", amazon, 5);

  const size = work.edition_count || editions?.size || editions?.entries?.length || 0;
  row.querySelector(".edition-count").textContent = `${size.toLocaleString()}個版本`;

  const btn = row.querySelector(".show-editions-btn");
  if (btn) {
    btn.onclick = () => {
      openEditionsModal(work.title, editions);
    };
  }
}

const LANGUAGE_NAME_MAP = {
  eng: "English",
  en: "English",
  zho: "Chinese",
  chi: "Chinese",
  zh: "Chinese",
  cht: "Traditional Chinese",
  "zh-hant": "Traditional Chinese",
  "zh-tw": "Traditional Chinese",
  chs: "Simplified Chinese",
  "zh-hans": "Simplified Chinese",
  "zh-cn": "Simplified Chinese",
  jpn: "Japanese",
  ja: "Japanese",
  fre: "French",
  fra: "French",
  fr: "French",
  ger: "German",
  deu: "German",
  de: "German",
  spa: "Spanish",
  es: "Spanish",
  rus: "Russian",
  ru: "Russian",
  ita: "Italian",
  it: "Italian",
  lat: "Latin",
  la: "Latin",
  por: "Portuguese",
  pt: "Portuguese",
  kor: "Korean",
  ko: "Korean",
  nld: "Dutch",
  dut: "Dutch",
  nl: "Dutch",
  swe: "Swedish",
  sv: "Swedish",
  pol: "Polish",
  pl: "Polish",
  ara: "Arabic",
  ar: "Arabic",
  hin: "Hindi",
  hi: "Hindi",
  vie: "Vietnamese",
  vi: "Vietnamese",
  tha: "Thai",
  th: "Thai",
  ind: "Indonesian",
  id: "Indonesian"
};

function formatLanguageFullName(langItem) {
  if (!langItem) return "";
  let code = "";
  if (typeof langItem === "string") {
    code = langItem;
  } else if (typeof langItem === "object" && langItem.key) {
    code = langItem.key.replace("/languages/", "");
  }
  code = code.trim().toLowerCase();
  if (!code) return "";
  return LANGUAGE_NAME_MAP[code] || (code.length <= 3 ? code.toUpperCase() : code);
}

function createEditionsTableCell(value, isMonospace = false) {
  const td = document.createElement("td");
  const text = value && String(value).trim() && String(value).trim() !== "出版年未提供"
    ? String(value).trim()
    : "-";
  td.textContent = text;
  if (text === "-") {
    td.className = "empty-cell";
  } else if (isMonospace) {
    td.className = "isbn-cell";
  }
  return td;
}

function openEditionsModal(title, editions) {
  const editionsModal = document.querySelector("#editions-modal");
  const modalTitle = document.querySelector("#editions-modal-title");
  const modalNote = document.querySelector("#editions-modal-note");
  const modalList = document.querySelector("#editions-modal-list");

  if (!editionsModal || !modalTitle || !modalNote || !modalList) return;

  modalTitle.textContent = `《${title}》的版本列表`;

  const size = editions.size || editions.entries.length;
  modalNote.textContent = size > MAX_EDITIONS
    ? `為維持查詢速度，目前列出前 ${MAX_EDITIONS} 個版本。`
    : "";

  const fragment = document.createDocumentFragment();

  if (!editions.entries?.length) {
    const emptyMsg = document.createElement("div");
    emptyMsg.textContent = "此作品尚未取得版本資料。";
    fragment.appendChild(emptyMsg);
  } else {
    const tableWrap = document.createElement("div");
    tableWrap.className = "editions-table-wrap";

    const table = document.createElement("table");
    table.className = "editions-table";

    const thead = document.createElement("thead");
    thead.innerHTML = `
      <tr>
        <th>書名</th>
        <th>出版年份</th>
        <th>語言</th>
        <th>ISBN</th>
      </tr>
    `;
    table.appendChild(thead);

    const tbody = document.createElement("tbody");

    (editions.entries || []).forEach((edition) => {
      const tr = document.createElement("tr");

      const rawLangs = edition.languages || [];
      const formattedLangs = (Array.isArray(rawLangs) ? rawLangs : [rawLangs])
        .map(formatLanguageFullName)
        .filter(Boolean);
      const langText = formattedLangs.length ? formattedLangs.join("、") : null;
      const isbnVal = edition.isbn_13 || edition.isbn_10;

      tr.append(
        createEditionsTableCell(edition.title),
        createEditionsTableCell(edition.publish_date),
        createEditionsTableCell(langText),
        createEditionsTableCell(isbnVal, true)
      );
      tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    tableWrap.appendChild(table);
    fragment.appendChild(tableWrap);
  }

  modalList.replaceChildren(fragment);

  // Open the modal
  editionsModal.hidden = false;
  setTimeout(() => editionsModal.classList.add("open"), 10);
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

  if (searchOlBtn) searchOlBtn.classList.toggle("active", engine === "open_library");
  if (searchGrBtn) searchGrBtn.classList.toggle("active", engine === "goodreads");
  if (searchGbBtn) searchGbBtn.classList.toggle("active", engine === "google_books");
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
    google_books: "Google Books"
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

if (searchOlBtn) {
  searchOlBtn.addEventListener("click", () => {
    const q = searchInput.value.trim() || currentQuery;
    if (q && currentEngine !== "open_library") {
      searchWorks(q, 1, "open_library");
    }
  });
}

if (searchGrBtn) {
  searchGrBtn.addEventListener("click", () => {
    const q = searchInput.value.trim() || currentQuery;
    if (q && currentEngine !== "goodreads") {
      searchWorks(q, 1, "goodreads");
    }
  });
}

if (searchGbBtn) {
  searchGbBtn.addEventListener("click", () => {
    const q = searchInput.value.trim() || currentQuery;
    if (q && currentEngine !== "google_books") {
      searchWorks(q, 1, "google_books");
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
apiKeyInput.value = savedKey;
if (savedKey) {
  apiKeyInput.placeholder = "已儲存 API 金鑰 (已遮蔽)";
}

saveApiKeyBtn.addEventListener("click", () => {
  const val = apiKeyInput.value.trim();
  if (val) {
    localStorage.setItem(GOOGLE_KEY_STORAGE_KEY, val);
    apiKeyInput.placeholder = "已儲存 API 金鑰 (已遮蔽)";
    alert("Google Books API Key 儲存成功！");
  } else {
    alert("請輸入有效的金鑰！");
  }
});

clearApiKeyBtn.addEventListener("click", () => {
  localStorage.removeItem(GOOGLE_KEY_STORAGE_KEY);
  apiKeyInput.value = "";
  apiKeyInput.placeholder = "輸入 API 金鑰 (例如 AIzaSy...)";
  alert("Google Books API Key 已清除！");
});

// Settings checkboxes logic
function initSettings() {
  if (scoreOlCheckbox) scoreOlCheckbox.checked = localStorage.getItem(SCORE_OL_KEY) !== "false";
  if (scoreGbCheckbox) scoreGbCheckbox.checked = localStorage.getItem(SCORE_GB_KEY) !== "false";
  if (scoreGrCheckbox) scoreGrCheckbox.checked = localStorage.getItem(SCORE_GR_KEY) !== "false";
  if (scoreDbCheckbox) scoreDbCheckbox.checked = localStorage.getItem(SCORE_DB_KEY) !== "false";
  if (scoreAmCheckbox) scoreAmCheckbox.checked = localStorage.getItem(SCORE_AM_KEY) !== "false";

  updateTableVisibility();
}

function updateTableVisibility() {
  if (ratingTable) {
    if (scoreOlCheckbox) ratingTable.classList.toggle("hide-ol-score", !scoreOlCheckbox.checked);
    if (scoreGbCheckbox) ratingTable.classList.toggle("hide-gb-score", !scoreGbCheckbox.checked);
    if (scoreGrCheckbox) ratingTable.classList.toggle("hide-gr-score", !scoreGrCheckbox.checked);
    if (scoreDbCheckbox) ratingTable.classList.toggle("hide-db-score", !scoreDbCheckbox.checked);
    if (scoreAmCheckbox) ratingTable.classList.toggle("hide-am-score", !scoreAmCheckbox.checked);
  }
}

if (scoreOlCheckbox) {
  scoreOlCheckbox.addEventListener("change", () => {
    localStorage.setItem(SCORE_OL_KEY, scoreOlCheckbox.checked);
    updateTableVisibility();
  });
}

if (scoreGbCheckbox) {
  scoreGbCheckbox.addEventListener("change", () => {
    localStorage.setItem(SCORE_GB_KEY, scoreGbCheckbox.checked);
    updateTableVisibility();
  });
}

if (scoreGrCheckbox) {
  scoreGrCheckbox.addEventListener("change", () => {
    localStorage.setItem(SCORE_GR_KEY, scoreGrCheckbox.checked);
    updateTableVisibility();
  });
}

if (scoreDbCheckbox) {
  scoreDbCheckbox.addEventListener("change", () => {
    localStorage.setItem(SCORE_DB_KEY, scoreDbCheckbox.checked);
    updateTableVisibility();
  });
}

if (scoreAmCheckbox) {
  scoreAmCheckbox.addEventListener("change", () => {
    localStorage.setItem(SCORE_AM_KEY, scoreAmCheckbox.checked);
    updateTableVisibility();
  });
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
    // Clear all localStorage cache keys starting with bookrate:cache:
    const keysToRemove = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith(CACHE_PREFIX)) {
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
