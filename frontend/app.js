const OL = "https://openlibrary.org";
const GOOGLE = "https://www.googleapis.com/books/v1";
const MAX_CANDIDATES = 10;
const MAX_EDITIONS = 100;
const HISTORY_KEY = "books-score:recent-searches";

const form = document.querySelector("#search-form");
const input = document.querySelector("#title");
const status = document.querySelector("#status");
const candidateSection = document.querySelector("#candidate-section");
const candidateList = document.querySelector("#candidate-list");
const candidateTemplate = document.querySelector("#candidate-template");
const historySection = document.querySelector("#history-section");
const historyList = document.querySelector("#history-list");
const results = document.querySelector("#results");
const tableWrap = results.querySelector(".table-wrap");
const resultBody = document.querySelector("#result-body");
const detailsHeading = document.querySelector("#details-heading");
const template = document.querySelector("#result-template");

function fetchJson(url) {
  return fetch(url).then(async (response) => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  });
}

function workId(key) { return key.split("/").pop(); }
function displayScore(average, count) { return Number(count) > 0 && Number(average) > 0 ? `${Number(average).toFixed(2)} / 5` : "暫無評分"; }
function displayCount(count) { return Number(count) > 0 ? `${Number(count).toLocaleString()} 人評價` : "尚無評價人數"; }
function normalise(value) { return (value || "").toLocaleLowerCase().replace(/[\s：:，,。.\-]/g, ""); }
function isbnValue(value) { const clean = value.replace(/[\s-]/g, ""); return /^(?:\d{9}[\dXx]|\d{13})$/.test(clean) ? clean : null; }

function getHistory() { try { return JSON.parse(localStorage.getItem(HISTORY_KEY)) || []; } catch { return []; } }
function saveHistory(query) {
  const history = [query, ...getHistory().filter((item) => item !== query)].slice(0, 5);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history)); renderHistory();
}
function renderHistory() {
  const history = getHistory(); historyList.replaceChildren(); historySection.hidden = !history.length;
  history.forEach((query) => { const button = document.createElement("button"); button.type = "button"; button.className = "history-item"; button.textContent = query; button.addEventListener("click", () => { input.value = query; form.requestSubmit(); }); historyList.append(button); });
}

function renderCandidates(works) {
  candidateList.replaceChildren();
  works.forEach((work) => {
    const fragment = candidateTemplate.content.cloneNode(true);
    fragment.querySelector(".candidate-title").textContent = work.title;
    fragment.querySelector(".candidate-author").textContent = (work.author_name || ["資料未提供"]).join("、");
    fragment.querySelector(".candidate-meta").textContent = [work.first_publish_year ? `首版 ${work.first_publish_year}` : "", work.edition_count ? `${work.edition_count.toLocaleString()} 個版本` : ""].filter(Boolean).join(" · ") || "出版資訊未提供";
    fragment.querySelector(".select-work").addEventListener("click", () => selectWork(work));
    candidateList.append(fragment);
  });
  candidateSection.hidden = false;
}

async function selectWork(work) {
  resultBody.replaceChildren(); tableWrap.hidden = true; detailsHeading.hidden = false;
  status.classList.remove("error"); status.textContent = `正在取得《${work.title}》的版本與評分…`;
  try {
    const details = await fetchJson(`/api/work-details?work_id=${encodeURIComponent(work.key)}&title=${encodeURIComponent(work.title)}&author=${encodeURIComponent((work.author_name || []).join(","))}`);
    details.work = work;
    resultBody.append(renderWork(details)); tableWrap.hidden = false;
    status.textContent = `已鎖定《${work.title}》；下方顯示其版本與評分。`;
  } catch (error) {
    console.error(error);
    status.classList.add("error");
    status.textContent = "取得作品詳細評分失敗，請確認網路連線後再試一次。";
  }
}

function renderWork({ work, ratings, editions, google }) {
  const fragment = template.content.cloneNode(true); const row = fragment.querySelector(".work-row");
  row.querySelector(".work-title").textContent = work.title;
  row.querySelector(".author").textContent = (work.author_name || ["資料未提供"]).join("、");
  row.querySelector(".work-link").href = `${OL}${work.key}`;
  row.querySelector(".ol-score").textContent = displayScore(ratings.average, ratings.count); row.querySelector(".ol-count").textContent = displayCount(ratings.count);
  row.querySelector(".gb-score").textContent = displayScore(google.average, google.count); row.querySelector(".gb-count").textContent = displayCount(google.count) + (google.title ? ` · ${google.title}` : "");
  const size = editions.size || editions.entries.length; row.querySelector(".edition-count").textContent = `（Open Library 共 ${size.toLocaleString()} 個）`;
  row.querySelector(".edition-note").textContent = size > MAX_EDITIONS ? `為維持查詢速度，目前列出前 ${MAX_EDITIONS} 個版本。` : "";
  const list = row.querySelector(".edition-list");
  (editions.entries || []).forEach((edition) => { const item = document.createElement("div"); item.className = "edition"; const editionTitle = document.createElement("b"); editionTitle.textContent = edition.title || "未命名版本"; const info = document.createElement("span"); const languages = (edition.languages || []).map((language) => language.key?.replace("/languages/", "")).join(", "); info.textContent = [edition.publish_date, edition.publishers?.[0], languages].filter(Boolean).join(" · ") || "出版資訊未提供"; item.append(editionTitle, info); list.append(item); });
  if (!editions.entries?.length) list.textContent = "此作品尚未取得版本資料。"; return fragment;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault(); const query = input.value.trim(); if (!query) return;
  candidateSection.hidden = true; detailsHeading.hidden = true; tableWrap.hidden = true; resultBody.replaceChildren(); status.classList.remove("error"); status.textContent = `正在尋找「${query}」的相關作品…`; saveHistory(query);
  try {
    const works = await fetchJson(`/api/search?q=${encodeURIComponent(query)}`);
    if (!works.length) { status.classList.add("error"); status.textContent = "找不到相符的作品；可嘗試完整書名、作者或 ISBN。"; return; }
    renderCandidates(works);
    status.textContent = `找到 ${works.length} 個候選作品。請在第 1 步鎖定正確的書籍。`;
  } catch (error) { console.error(error); status.classList.add("error"); status.textContent = "查詢失敗，請確認網路連線後再試一次。"; }
});

renderHistory();

