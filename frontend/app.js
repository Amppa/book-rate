import { OPEN_LIBRARY_BASE_URL, MAX_CANDIDATES, HISTORY_KEY, SOURCES, STRATEGIES, SOURCE_PREFIX, LANGUAGE_NAME_MAP } from './js/constants.js';
import { getCachedData, setCachedData, getRatingCache, setRatingCache, cleanExpiredCache } from './js/cache.js';
import { fetchJson, displayRate, displayCount, getWorkExternalUrl, getSourceDisplayName } from './js/utils.js';
import { renderSourceToggles, renderStrategySelects, updateTableVisibility, renderTableHeaders, renderTitleSourceTabs, initTableVisibilityStyles } from './js/ui.js';

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
let currentTitleSource = "open_library";
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

  // Find current source configuration to check if enable_extend_editions is true
  const currentSourceObj = SOURCES.find(p => p.id === currentTitleSource);

  works.forEach((work) => {
    // Only allow expansion if the source supports it AND the work has more than 1 edition
    const hasMultipleEditions = typeof work.edition_count === "number" && work.edition_count > 1;
    const enableExtend = currentSourceObj && currentSourceObj.enable_extend_editions === true && hasMultipleEditions;

    const fragment = candidateTemplate.content.cloneNode(true);
    const cardEl = fragment.querySelector(".candidate-card");
    if (cardEl) {
      cardEl.dataset.key = work.key;
      if (enableExtend) {
        cardEl.classList.add("expandable");
      }
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

    // Toggle chevron visibility
    const chevronEl = fragment.querySelector(".candidate-chevron");
    if (chevronEl) {
      chevronEl.hidden = !enableExtend;
    }

    const selectBtn = fragment.querySelector(".select-work");
    selectBtn.addEventListener("click", (e) => {
      e.stopPropagation(); // Prevent toggling expansion when choosing
      chooseCandidate(work);
    });

    if (enableExtend) {
      const mainRow = fragment.querySelector(".candidate-main-row");
      const editionsArea = fragment.querySelector(".candidate-editions-area");

      mainRow.addEventListener("click", async (e) => {
        // Ignore clicks on links or buttons
        if (e.target.closest(".select-work") || e.target.closest(".candidate-link")) {
          return;
        }

        const isCurrentlyHidden = editionsArea.hidden;

        if (isCurrentlyHidden) {
          // Collapse all other candidate cards first (accordion style)
          candidateList.querySelectorAll(".candidate-card").forEach((otherCard) => {
            if (otherCard !== cardEl && otherCard.classList.contains("expanded")) {
              otherCard.classList.remove("expanded");
              const otherEdArea = otherCard.querySelector(".candidate-editions-area");
              if (otherEdArea) otherEdArea.hidden = true;
            }
          });

          cardEl.classList.add("expanded");
          editionsArea.hidden = false;
        } else {
          cardEl.classList.remove("expanded");
          editionsArea.hidden = true;
          return;
        }

        // Check if editions are already cached on the work object
        if (work.fetched_editions) {
          renderEditionsList(editionsArea, work, work.fetched_editions);
          return;
        }

        // Show loading state
        editionsArea.innerHTML = '<div class="loading-editions">載入版本資訊中...</div>';

        try {
          const resp = await fetch(`/api/work-editions?work_id=${encodeURIComponent(work.key)}`);
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const data = await resp.json(); // { size: N, entries: [...] }

          // Store in cache
          work.fetched_editions = data.entries || [];

          renderEditionsList(editionsArea, work, work.fetched_editions);
        } catch (err) {
          console.error("Failed to load editions:", err);
          editionsArea.innerHTML = '<div class="error-editions">無法載入版本資訊 ⚠️</div>';
        }
      });
    }

    // If this candidate was already the selected one, mark it
    if (currentSelectedWork && currentSelectedWork.key === work.key) {
      if (cardEl) cardEl.classList.add("selected");
      selectBtn.textContent = "已選取";
      selectBtn.disabled = true;
    }

    candidateList.append(fragment);
  });
  candidateSection.hidden = false;
}

function renderEditionsList(container, work, editions, showAll = false) {
  container.replaceChildren();

  if (!editions || editions.length === 0) {
    container.innerHTML = '<div class="empty-editions">無版本資訊</div>';
    return;
  }

  // 1. Define English & Chinese language matcher using LANGUAGE_NAME_MAP dynamic resolution
  const isEnOrZh = (ed) => {
    if (!ed.languages || ed.languages.length === 0) return false;
    return ed.languages.some((lang) => {
      const code = (lang.key || "").replace("/languages/", "").toLowerCase();
      const resolvedName = LANGUAGE_NAME_MAP[code] || "";
      return resolvedName.includes("English") || resolvedName.includes("Chinese");
    });
  };

  // 2. Split by language match
  const matchEditions = [];
  const otherEditions = [];

  editions.forEach((ed) => {
    if (isEnOrZh(ed)) {
      matchEditions.push(ed);
    } else {
      otherEditions.push(ed);
    }
  });

  const listDiv = document.createElement("div");
  listDiv.className = "edition-list";

  const renderSingleEdition = (ed) => {
    const title = ed.title || work.title || "Unknown Title";
    const author = (work.author_name || []).join(", ") || "Unknown Author";
    const year = ed.publish_date || "Unknown Year";
    const isbn = ed.isbn_13 || ed.isbn_10 || "No ISBN";

    // Resolve language codes to names using LANGUAGE_NAME_MAP
    const langList = (ed.languages || []).map((l) => {
      const code = (l.key || "").replace("/languages/", "").toLowerCase();
      return LANGUAGE_NAME_MAP[code] || code;
    });
    const langStr = langList.join(", ") || "Unknown Language";

    const editionText = `${title} / 作者: ${author} / ${year} / ISBN: ${isbn} / 語言: ${langStr}`;

    const itemEl = document.createElement("div");
    itemEl.className = "edition-item";
    itemEl.textContent = editionText;

    itemEl.addEventListener("click", (e) => {
      e.stopPropagation(); // Prevent toggling the parent card expansion
      chooseEdition(work, ed, itemEl);
    });

    listDiv.appendChild(itemEl);
  };

  const hasEnZh = matchEditions.length > 0;
  const hasOthers = otherEditions.length > 0;
  const shouldSplit = hasEnZh && hasOthers;

  if (showAll || !shouldSplit) {
    editions.forEach(renderSingleEdition);
  } else {
    matchEditions.forEach(renderSingleEdition);

    if (otherEditions.length > 0) {
      const moreBtn = document.createElement("div");
      moreBtn.className = "edition-more-btn";
      moreBtn.textContent = `[other language]`;
      moreBtn.addEventListener("click", (e) => {
        e.stopPropagation(); // Prevent collapsing card
        renderEditionsList(container, work, editions, true);
      });
      listDiv.appendChild(moreBtn);
    } else if (matchEditions.length === 0) {
      container.innerHTML = '<div class="empty-editions">無符合中/英文語言之版本</div>';
      return;
    }
  }

  container.appendChild(listDiv);
}

function appendAndLimitTextarea(textareaEl, newItems, maxLimit) {
  if (!textareaEl) return;

  const items = Array.isArray(newItems) ? newItems : [newItems];
  const validItems = items.map(item => String(item).trim()).filter(Boolean);
  if (validItems.length === 0) return;

  const currentVal = textareaEl.value.trim();
  let lines = currentVal ? currentVal.split('\n').map(s => s.trim()) : [];

  validItems.forEach(item => {
    if (!lines.includes(item)) {
      lines.push(item);
    }
  });

  if (lines.length > maxLimit) {
    lines = lines.slice(lines.length - maxLimit);
  }

  textareaEl.value = lines.join('\n');
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

  // Clear any active highlights on editions list
  document.querySelectorAll(".edition-item").forEach((el) => {
    el.classList.remove("selected");
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
  const titleZhEl = document.querySelector("#bm-title-zh");
  const authorEl = document.querySelector("#bm-author");
  const publishDateEl = document.querySelector("#bm-publish-date");
  const isbnEl = document.querySelector("#bm-isbn");

  const hasCjk = (str) => /[\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff\uac00-\ud7a3]/.test(str);

  if (work.title) {
    if (hasCjk(work.title)) {
      appendAndLimitTextarea(titleZhEl, work.title, 4);
    } else {
      appendAndLimitTextarea(titleEl, work.title, 4);
    }
  }

  if (work.author_name && work.author_name.length > 0) {
    const validAuthors = work.author_name
      .map(name => name.trim())
      .filter(name => name && name.toLowerCase() !== 'unknown');
    appendAndLimitTextarea(authorEl, validAuthors, 8);
  }

  if (publishDateEl) {
    publishDateEl.value = work.first_publish_year || "";
  }

  if (work.isbn) {
    const isbnVal = Array.isArray(work.isbn) ? work.isbn[0] : work.isbn;
    appendAndLimitTextarea(isbnEl, isbnVal, 8);
  }
}

function chooseEdition(work, edition, itemEl) {
  // Mark parent work as selected
  chooseCandidate(work);

  // Set highlight state on selected edition item element
  document.querySelectorAll(".edition-item").forEach((el) => {
    el.classList.remove("selected");
  });
  if (itemEl) {
    itemEl.classList.add("selected");
  }

  const titleEl = document.querySelector("#bm-title");
  const titleZhEl = document.querySelector("#bm-title-zh");
  const publishDateEl = document.querySelector("#bm-publish-date");
  const isbnEl = document.querySelector("#bm-isbn");

  const hasCjk = (str) => /[\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff\uac00-\ud7a3]/.test(str);

  const titleVal = edition.title || work.title;
  if (titleVal) {
    if (hasCjk(titleVal)) {
      appendAndLimitTextarea(titleZhEl, titleVal, 4);
    } else {
      appendAndLimitTextarea(titleEl, titleVal, 4);
    }
  }

  const pubDateVal = edition.publish_date || (work.first_publish_year ? String(work.first_publish_year) : "");
  if (publishDateEl && pubDateVal) {
    publishDateEl.value = pubDateVal;
  }

  const isbnVal = edition.isbn_13 || edition.isbn_10;
  if (isbnEl && isbnVal) {
    appendAndLimitTextarea(isbnEl, isbnVal, 8);
  }
}

function resetMetadataPanel(query) {
  const searchNameEl = document.querySelector("#bm-search-name");
  const titleEl = document.querySelector("#bm-title");
  const titleZhEl = document.querySelector("#bm-title-zh");
  const authorEl = document.querySelector("#bm-author");
  const publishDateEl = document.querySelector("#bm-publish-date");
  const isbnEl = document.querySelector("#bm-isbn");

  if (searchNameEl) searchNameEl.value = query || "";
  if (titleEl) titleEl.value = "";
  if (titleZhEl) titleZhEl.value = "";
  if (authorEl) authorEl.value = "";
  if (publishDateEl) publishDateEl.value = "";
  if (isbnEl) isbnEl.value = "";
  currentSelectedWork = null;
}

function confirmToStep3() {
  const searchNameVal = document.querySelector("#bm-search-name")?.value || "";
  const titleVal = document.querySelector("#bm-title")?.value.trim() || "";
  const titleZhVal = document.querySelector("#bm-title-zh")?.value || "";
  const authorVal = document.querySelector("#bm-author")?.value.trim() || "";
  const publishDateVal = document.querySelector("#bm-publish-date")?.value.trim() || "";
  const isbnVal = document.querySelector("#bm-isbn")?.value.trim() || "";

  if (!searchNameVal.trim() && !isbnVal.trim()) {
    alert("搜尋名稱或 ISBN 至少要有一個。");
    return;
  }

  // Copy values to step 3 metadata fields
  const s3SearchName = document.querySelector("#s3-search-name");
  const s3Title = document.querySelector("#s3-title");
  const s3TitleZh = document.querySelector("#s3-title-zh");
  const s3Author = document.querySelector("#s3-author");
  const s3PublishDate = document.querySelector("#s3-publish-date");
  const s3Isbn = document.querySelector("#s3-isbn");

  if (s3SearchName) s3SearchName.value = searchNameVal;
  if (s3Title) s3Title.value = titleVal;
  if (s3TitleZh) s3TitleZh.value = titleZhVal;
  if (s3Author) s3Author.value = authorVal;
  if (s3PublishDate) s3PublishDate.value = publishDateVal;
  if (s3Isbn) s3Isbn.value = isbnVal;

  let workToUse = currentSelectedWork;
  if (!workToUse) {
    workToUse = {
      key: "custom:" + Date.now(),
      title: titleVal || (titleZhVal ? titleZhVal.split("\n")[0] : ""),
      author_name: authorVal ? [authorVal] : ["Unknown"],
      first_publish_year: publishDateVal,
      isbn: isbnVal
    };
  } else {
    workToUse = {
      ...workToUse,
      title: titleVal || workToUse.title || (titleZhVal ? titleZhVal.split("\n")[0] : ""),
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
    const source = sel.dataset.source;
    if (source) {
      strats[source] = sel.value;
    }
  });
  return strats;
}

function getActiveRateSourcesList() {
  const rateSources = [];
  SOURCES.forEach((source) => {
    const suffix = SOURCE_PREFIX[source.id];
    const checkbox = document.querySelector(`#score-${suffix}`);
    if (checkbox && checkbox.checked) {
      rateSources.push(source.id);
    }
  });
  return rateSources;
}

function getStep3Metadata() {
  const searchName = document.querySelector("#s3-search-name")?.value.trim() || "";
  const titleList = (document.querySelector("#s3-title")?.value || "").split("\n").map(s => s.trim()).filter(Boolean);
  const titleZhList = (document.querySelector("#s3-title-zh")?.value || "").split("\n").map(s => s.trim()).filter(Boolean);
  const authorList = (document.querySelector("#s3-author")?.value || "").split("\n").map(s => s.trim()).filter(Boolean);
  const isbnList = (document.querySelector("#s3-isbn")?.value || "").split("\n").map(s => s.trim()).filter(Boolean);

  return { searchName, titleList, titleZhList, authorList, isbnList };
}

function getSourceDefaultStrat(provId) {
  return SOURCES.find(p => p.id === provId)?.defaultStrategy || "title_list";
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

  const row = renderInitialWorkRow(work);
  resultBody.append(row);
  tableWrap.hidden = false;

  step3Status.classList.remove("error");
  step3Status.textContent = "";

  const activeRateSourcesList = getActiveRateSourcesList();
  const apiKey = localStorage.getItem("bookrate:google-api-key") || "";
  const strategies = getSelectedStrategies();

  // 區分命中快取與未命中快取
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

  // 立即渲染已命中的快取
  cachedRateSources.forEach(({ source, data }) => {
    const prefix = SOURCE_PREFIX[source] || source;
    const maxRate = prefix === "db" ? 10 : 5;
    renderSourceCell(row, prefix, data, maxRate);
  });

  try {
    const meta = getStep3Metadata();
    const strategiesStr = JSON.stringify(strategies);
    let url = `/api/work-details-stream?work_id=${encodeURIComponent(work.key)}` +
      `&search_name=${encodeURIComponent(meta.searchName)}` +
      `&title_list=${encodeURIComponent(JSON.stringify(meta.titleList))}` +
      `&title_zh_list=${encodeURIComponent(JSON.stringify(meta.titleZhList))}` +
      `&author_list=${encodeURIComponent(JSON.stringify(meta.authorList))}` +
      `&isbn_list=${encodeURIComponent(JSON.stringify(meta.isbnList))}` +
      `&engines=${encodeURIComponent(pendingRateSources.join(","))}` +
      `&strategies=${encodeURIComponent(strategiesStr)}`;
    if (apiKey) {
      url += `&google_key=${encodeURIComponent(apiKey)}`;
    }

    const collectedDetails = { work, ratings: {}, editions: {} };
    SOURCES.forEach((source) => {
      collectedDetails[source.id] = {};
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
        } else if (data.type === "source") {
          const sourceKey = data.source;
          collectedDetails[sourceKey] = data.data;

          const prefix = SOURCE_PREFIX[sourceKey] || sourceKey;
          const maxRate = prefix === "db" ? 10 : 5;

          // 寫入評分快取
          const strategy = strategies[sourceKey] || getSourceDefaultStrat(sourceKey);
          setRatingCache(work.key, sourceKey, strategy, data.data);

          renderSourceCell(row, prefix, data.data, maxRate);
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

function reQuerySingleSource(work, sourceKey) {
  const row = resultBody.querySelector(".work-row");
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
  const strategiesStr = JSON.stringify(strategies);

  const meta = getStep3Metadata();
  let url = `/api/work-details-stream?work_id=${encodeURIComponent(work.key)}` +
    `&search_name=${encodeURIComponent(meta.searchName)}` +
    `&title_list=${encodeURIComponent(JSON.stringify(meta.titleList))}` +
    `&title_zh_list=${encodeURIComponent(JSON.stringify(meta.titleZhList))}` +
    `&author_list=${encodeURIComponent(JSON.stringify(meta.authorList))}` +
    `&isbn_list=${encodeURIComponent(JSON.stringify(meta.isbnList))}` +
    `&engines=${encodeURIComponent(sourceKey)}` +
    `&strategies=${encodeURIComponent(strategiesStr)}`;
  if (apiKey) {
    url += `&google_key=${encodeURIComponent(apiKey)}`;
  }

  const eventSource = new EventSource(url);
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "source") {
        const maxRate = prefix === "db" ? 10 : 5;

        // 重新查詢寫入評分快取並渲染
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
      const sourceKey = e.target.dataset.source;
      if (sourceKey) {
        localStorage.setItem("bookrate:strategy:" + sourceKey, e.target.value);
      }
      if (currentSelectedWork && sourceKey) {
        reQuerySingleSource(currentSelectedWork, sourceKey);
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

function renderSourceCell(row, prefix, data, maxRate = 5) {
  const rateEl = row.querySelector(`.${prefix}-rate`);
  const countEl = row.querySelector(`.${prefix}-count`);

  if (!rateEl || !countEl) return;
  if (!data || Object.keys(data).length === 0) return;

  const hasScore = typeof data.average === "number" && data.average > 0;
  const hasUrl = Boolean(data.url);
  const status = data.status || (hasScore ? "MATCH" : "NO_MATCH");
  const isNetworkError = status && status !== "MATCH" && status !== "CURL_MATCH" && status !== "NO_MATCH" && status !== "QUOTA_EXCEEDED" && status !== "ERROR";

  // Clear previous elements
  rateEl.replaceChildren();

  const cell = rateEl.closest("td");
  if (cell) {
    const oldTitle = cell.querySelector(".source-book-title");
    if (oldTitle) oldTitle.remove();
    
    // In single-result mode, display the title above the rating if it exists
    if (data.title && (!data.results || data.results.length === 0)) {
      const titleDiv = document.createElement("div");
      titleDiv.className = "source-book-title";
      titleDiv.textContent = data.title;
      cell.insertBefore(titleDiv, rateEl);
    }
  }

  const STRATEGY_LABEL_MAP = {
    "search_name": "搜尋名稱",
    "title_list": "書名列表 (短路)",
    "title_zh_list": "書名列表 (亞洲) (短路)",
    "title_list_full": "書名列表 (完整)",
    "title_zh_list_full": "書名列表 (亞洲) (完整)",
    "isbn": "ISBN",
    "source_id": "書籍ID (精確)"
  };

  if (data.results && data.results.length > 0) {
    const listContainer = document.createElement("div");
    listContainer.className = "multi-result-list";

    data.results.forEach((res, index) => {
      const item = document.createElement("div");
      item.className = "multi-result-item";

      const friendlyStrat = STRATEGY_LABEL_MAP[res.strategy] || res.strategy || "N/A";
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
    countEl.replaceChildren(); // clear countEl

    // Render status tag
    if (cell) {
      const oldTag = cell.querySelector(".search-status-tag");
      if (oldTag) oldTag.remove();

      const tag = document.createElement("span");
      tag.className = `search-status-tag status-${status.toLowerCase().replace(/[^a-z0-9_]/g, "-")}`;
      tag.textContent = status;
      tag.dataset.strat = data.strategy || "";
      tag.dataset.query = data.query || "";
      const friendlyStrat = STRATEGY_LABEL_MAP[data.strategy] || data.strategy || "N/A";
      tag.title = `策略: ${friendlyStrat}, 查詢: ${data.query || "N/A"}`;
      cell.appendChild(tag);
    }
    return;
  }

  // --- Single-result render logic ---
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
    countEl.textContent = status;
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
  if (cell) {
    const oldTag = cell.querySelector(".search-status-tag");
    if (oldTag) oldTag.remove();

    const tag = document.createElement("span");
    tag.className = `search-status-tag status-${status.toLowerCase().replace(/[^a-z0-9_]/g, "-")}`;
    tag.textContent = status;
    tag.dataset.strat = data.strategy || "";
    tag.dataset.query = data.query || "";
    const friendlyStrat = STRATEGY_LABEL_MAP[data.strategy] || data.strategy || "N/A";
    tag.title = `策略: ${friendlyStrat}, 查詢: ${data.query || "N/A"}`;

    cell.appendChild(tag);
  }
}

function updateWorkDetailRow(row, { work, ratings }, strategies) {
  if (!row) return;

  // 3. 渲染 Open Library 評分
  const olUrl = ratings?.url || ((work.key && work.key.startsWith("/works/")) ? `${OPEN_LIBRARY_BASE_URL}${work.key}` : null);
  const olData = { average: ratings?.average, count: ratings?.count, url: olUrl, status: (ratings?.average ? "MATCH" : "NO_MATCH") };
  renderSourceCell(row, "ol", olData, 5);

  // 寫入快取
  if (strategies) {
    const olStrategy = strategies.open_library || getSourceDefaultStrat("open_library");
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

function updateTitleSourceTabs(titleSource) {
  const tabsContainer = document.querySelector("#title-source-tabs-container");
  if (tabsContainer) {
    tabsContainer.querySelectorAll(".title-source-tab-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.sourceId === titleSource);
    });
  }
}

async function searchWorks(query, page, titleSource = "open_library") {
  currentQuery = query;
  currentPage = page;
  currentTitleSource = titleSource;
  candidateSection.hidden = false;
  candidateHeading.hidden = false;
  goToStep(2);
  updateTitleSourceTabs(titleSource);

  const sourceObj = SOURCES.find(p => p.id === titleSource);
  const titleSourceName = sourceObj ? sourceObj.label : "資料庫";

  candidateList.replaceChildren();
  const loadingEl = document.createElement("div");
  loadingEl.className = "no-results loading";
  loadingEl.textContent = `載入中… 正在使用 ${titleSourceName} 尋找「${query}」`;
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
    const cacheKey = `search:${query}:page:${page}:engines:${titleSource}`;
    let works = getCachedData(cacheKey);
    if (!works) {
      let url = `/api/search?q=${encodeURIComponent(query)}&page=${page}&engines=${encodeURIComponent(titleSource)}`;
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
        noResultsEl.textContent = `${titleSourceName} 找不到「${query}」`;
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
  resetMetadataPanel(query);
  searchWorks(query, 1, "open_library");
});

const tabsContainer = document.querySelector("#title-source-tabs-container");
if (tabsContainer) {
  tabsContainer.addEventListener("click", (e) => {
    const btn = e.target.closest(".title-source-tab-btn");
    if (btn) {
      const sourceId = btn.dataset.sourceId;
      const q = searchInput.value.trim() || currentQuery;
      if (q && sourceId) {
        searchWorks(q, 1, sourceId);
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
    searchWorks(currentQuery, currentPage - 1, currentTitleSource);
  }
});

nextPageBtn.addEventListener("click", () => {
  searchWorks(currentQuery, currentPage + 1, currentTitleSource);
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
  renderTitleSourceTabs(document.querySelector("#title-source-tabs-container"), currentTitleSource);

  renderSourceToggles(scoreToggleBarEl);
  renderStrategySelects(scoreStrategyRowEl);

  SOURCES.forEach((source) => {
    const suffix = SOURCE_PREFIX[source.id];
    const checkbox = document.querySelector(`#score-${suffix}`);
    if (checkbox) {
      checkbox.checked = localStorage.getItem(`bookrate:score:${suffix}`) !== "false";
    }

    const select = document.querySelector(`.strategy-select[data-source="${source.id}"]`);
    if (select) {
      const savedStrategy = localStorage.getItem("bookrate:strategy:" + source.id);
      select.value = savedStrategy || source.defaultStrategy;
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

// Source Info Modal logic (dynamic load from source_info.html)
const openSourceInfoBtn = document.querySelector("#open-source-info-btn");

if (openSourceInfoBtn) {
  openSourceInfoBtn.addEventListener("click", async () => {
    let sourceInfoModal = document.querySelector("#source-info-modal");

    if (sourceInfoModal) {
      sourceInfoModal.remove();
      sourceInfoModal = null;
    }

    if (!sourceInfoModal) {
      try {
        const resp = await fetch("./source_info.html?v=" + Date.now());
        if (resp.ok) {
          const htmlText = await resp.text();
          const tempDiv = document.createElement("div");
          tempDiv.innerHTML = htmlText;
          sourceInfoModal = tempDiv.firstElementChild;
          document.body.appendChild(sourceInfoModal);

          const closeBtn = sourceInfoModal.querySelector("#close-source-info-btn");
          const closeModal = () => {
            sourceInfoModal.classList.remove("open");
            setTimeout(() => {
              if (!sourceInfoModal.classList.contains("open")) {
                sourceInfoModal.hidden = true;
              }
            }, 300);
          };

          if (closeBtn) {
            closeBtn.addEventListener("click", closeModal);
          }
          sourceInfoModal.addEventListener("click", (e) => {
            if (e.target === sourceInfoModal) {
              closeModal();
            }
          });
        }
      } catch (err) {
        console.error("Failed to load source_info.html:", err);
      }
    }

    if (sourceInfoModal) {
      sourceInfoModal.hidden = false;
      setTimeout(() => sourceInfoModal.classList.add("open"), 10);
    }
  });
}
