const OPEN_LIBRARY_BASE_URL = "https://openlibrary.org";
const GOOGLE_BOOKS_BASE_URL = "https://www.googleapis.com/books/v1";
const MAX_CANDIDATES = 10;
const MAX_EDITIONS = 100;
const HISTORY_KEY = "bookrate:recent-searches";
const CACHE_PREFIX = "bookrate:cache:";
const ONE_DAY_MS = 24 * 60 * 60 * 1000;

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
  } catch (e) {}
}

// Clean expired cache entries on load
cleanExpiredCache();

const searchForm = document.querySelector("#search-form");
const searchInput = document.querySelector("#title");
const statusMessage = document.querySelector("#status");
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

function goToStep(step) {
  currentStep = step;
  const offset = - (step - 1) * 33.3333;
  wizardTrack.style.transform = `translateX(${offset}%)`;
}

function fetchJson(url) {
  return fetch(url).then(async (response) => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  });
}

function displayRate(average, count) {
  return Number(count) > 0 && Number(average) > 0
    ? `${Number(average).toFixed(2)} / 5`
    : "暫無評分";
}

function formatCompact(n) {
  if (n >= 1e6) {
    const val = n / 1e6;
    return (val % 1 === 0 ? val : val.toFixed(1)) + "m";
  }
  if (n >= 1e3) {
    const val = n / 1e3;
    return (val % 1 === 0 ? val : val.toFixed(1)) + "k";
  }
  return n.toString();
}

function displayCount(count) {
  return Number(count) > 0
    ? `${formatCompact(Number(count))} 人評價`
    : "尚無評價人數";
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
      searchForm.requestSubmit();
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
    
    const authorText = (work.author_name || []).length
      ? `作者：${work.author_name.join("、")}`
      : "作者：資料未提供";
    const publishText = work.first_publish_year
      ? `首版 ${work.first_publish_year}`
      : "";
    const editionText = work.edition_count
      ? `${work.edition_count.toLocaleString()} 個版本`
      : "";
    
    fragment.querySelector(".candidate-meta").textContent = [
      authorText,
      publishText,
      editionText
    ].filter(Boolean).join(" · ");
    
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
      btn.textContent = "選這本書";
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
  tableWrap.hidden = true;
  statusMessage.classList.remove("error");
  statusMessage.textContent = `正在取得《${work.title}》的版本與評分…`;
  
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
    resultBody.append(renderWorkDetailRow(details));
    tableWrap.hidden = false;
    statusMessage.textContent = `選取《${work.title}》；下方顯示其版本與評分。`;
  } catch (error) {
    console.error(error);
    statusMessage.classList.add("error");
    statusMessage.textContent = "取得作品詳細評分失敗，請確認網路連線後再試一次。";
  }
}

function renderWorkDetailRow({ work, ratings, editions, google }) {
  const fragment = resultRowTemplate.content.cloneNode(true);
  const row = fragment.querySelector(".work-row");
  
  row.querySelector(".work-title").textContent = work.title;
  row.querySelector(".author").textContent = (work.author_name || ["資料未提供"]).join("、");
  row.querySelector(".work-link").href = `${OPEN_LIBRARY_BASE_URL}${work.key}`;
  
  row.querySelector(".ol-rate").textContent = displayRate(ratings.average, ratings.count);
  row.querySelector(".ol-count").textContent = displayCount(ratings.count);
  
  if (google.quota_exceeded) {
    row.querySelector(".gb-score").innerHTML = '<span class="error">額度超限 (429) ⚠️</span>';
    row.querySelector(".gb-count").textContent = "請在上方設定個人 API Key，或設定環境變數。";
  } else {
    row.querySelector(".gb-rate").textContent = displayRate(google.average, google.count);
    row.querySelector(".gb-count").textContent = displayCount(google.count) + (google.title ? ` · ${google.title}` : "");
  }
  
  const size = editions.size || editions.entries.length;
  row.querySelector(".edition-count").textContent = `${size.toLocaleString()}個版本`;
  row.querySelector(".edition-note").textContent = size > MAX_EDITIONS
    ? `為維持查詢速度，目前列出前 ${MAX_EDITIONS} 個版本。`
    : "";
  
  const list = row.querySelector(".edition-list");
  (editions.entries || []).forEach((edition) => {
    const item = document.createElement("div");
    item.className = "edition";
    
    const editionTitle = document.createElement("b");
    editionTitle.textContent = edition.title || "未命名版本";
    
    const info = document.createElement("span");
    const languages = (edition.languages || []).map((language) => language.key?.replace("/languages/", "")).join(", ");
    info.textContent = [edition.publish_date, edition.publishers?.[0], languages].filter(Boolean).join(" · ") || "出版資訊未提供";
    
    item.append(editionTitle, info);
    list.append(item);
  });
  
  if (!editions.entries?.length) {
    list.textContent = "此作品尚未取得版本資料。";
  }
  return fragment;
}

async function searchWorks(query, page) {
  candidateList.replaceChildren();
  candidateSection.hidden = false; 
  candidateHeading.hidden = false;
  goToStep(2);
  
  paginationControls.hidden = true;
  detailsHeading.hidden = true; 
  tableWrap.hidden = true; 
  resultBody.replaceChildren(); 
  statusMessage.classList.remove("error"); 
  statusMessage.textContent = `正在尋找「${query}」的相關作品 (第 ${page} 頁)…`; 
  
  if (page === 1) {
    saveHistory(query);
  }
  
  try {
    const cacheKey = `search:${query}:page:${page}`;
    let works = getCachedData(cacheKey);
    if (!works) {
      works = await fetchJson(`/api/search?q=${encodeURIComponent(query)}&page=${page}`);
      if (works && works.length > 0) {
        setCachedData(cacheKey, works);
      }
    }
    if (!works || !works.length) { 
      statusMessage.classList.add("error"); 
      statusMessage.textContent = page === 1 ? "找不到相符的作品；可嘗試完整書名、作者或 ISBN。" : "已無更多作品。"; 
      return; 
    }
    
    currentQuery = query;
    currentPage = page;
    
    renderCandidates(works);
    candidateHeading.hidden = false;
    updatePagination(works.length);
    statusMessage.textContent = `找到 ${works.length} 個候選作品。請在第 1 步選取正確的書籍。`;
  } catch (error) { 
    console.error(error); 
    statusMessage.classList.add("error"); 
    statusMessage.textContent = "查詢失敗，請確認網路連線後再試一次。"; 
  }
}

searchForm.addEventListener("submit", (event) => {
  event.preventDefault(); 
  const query = searchInput.value.trim(); 
  if (!query) return;
  searchWorks(query, 1);
});

function updatePagination(itemsCount) {
  if (!currentQuery) {
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
    searchWorks(currentQuery, currentPage - 1);
  }
});

nextPageBtn.addEventListener("click", () => {
  searchWorks(currentQuery, currentPage + 1);
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

btnPrevTo1.addEventListener("click", () => {
  goToStep(1);
});

btnPrevTo2.addEventListener("click", () => {
  goToStep(2);
  candidateList.querySelectorAll(".candidate-card").forEach((card) => {
    card.classList.remove("selected");
    const btn = card.querySelector(".select-work");
    if (btn) {
      btn.textContent = "選這本書";
      btn.disabled = false;
    }
  });
});
