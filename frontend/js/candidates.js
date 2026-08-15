import { state } from './state.js';
import { SOURCES, LANGUAGE_NAME_MAP } from './constants.js';
import { getWorkExternalUrl } from './utils.js';
import { getCachedData, setCachedData } from './cache.js';

// ---------------------------------------------------------------------------
// Status tag helpers
// ---------------------------------------------------------------------------

/** Converts a raw status string into a short badge descriptor. */
export function getShortStatus(status) {
  if (!status || status === "Normal") return null;

  const lower = status.toLowerCase();

  if (lower.includes("successfully")) {
    return { text: "failover", type: "warning" };
  }

  const httpMatch = status.match(/HTTP\s+(\d+)/i) || status.match(/\b(403|404|503|500|429)\b/);
  if (httpMatch) {
    const code = httpMatch[1];
    if (code === "403") return { text: "403", type: "error" };
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

// ---------------------------------------------------------------------------
// Card selection UI (shared by wizard.js → chooseCandidate and ratings.js → selectWork)
// ---------------------------------------------------------------------------

/**
 * Updates the visual selected state of candidate cards.
 * Deselects all cards, then marks the one matching workKey as selected.
 * @param {HTMLElement|null} candidateList
 * @param {string} workKey
 */
export function markCandidateSelected(candidateList, workKey) {
  if (!candidateList) return;
  candidateList.querySelectorAll(".candidate-card").forEach((card) => {
    card.classList.remove("selected");
    const btn = card.querySelector(".select-work");
    if (btn) { btn.textContent = "Choose"; btn.disabled = false; }
  });

  const selectedCard = candidateList.querySelector(`[data-key="${workKey}"]`);
  if (selectedCard) {
    selectedCard.classList.add("selected");
    const btn = selectedCard.querySelector(".select-work");
    if (btn) { btn.textContent = "已選取"; btn.disabled = true; }
  }
}

// ---------------------------------------------------------------------------
// Edition list renderer
// ---------------------------------------------------------------------------

/**
 * Renders editions into a container element.
 * @param {HTMLElement} container
 * @param {object} work
 * @param {object[]} editions
 * @param {boolean} [showAll=false] - whether to skip the en/zh filter split
 * @param {((work: object, edition: object, itemEl: HTMLElement) => void)|null} [onChooseEdition]
 */
export function renderEditionsList(container, work, editions, showAll = false, onChooseEdition = null) {
  container.replaceChildren();

  if (!editions || editions.length === 0) {
    container.innerHTML = '<div class="empty-editions">無版本資訊</div>';
    return;
  }

  const isZh = (ed) => {
    if (!ed.languages || ed.languages.length === 0) return false;
    return ed.languages.some((lang) => {
      const code = (lang.key || "").replace("/languages/", "").toLowerCase();
      const resolvedName = LANGUAGE_NAME_MAP[code] || code;
      return resolvedName.toLowerCase().includes("chinese");
    });
  };

  const isEn = (ed) => {
    if (!ed.languages || ed.languages.length === 0) return false;
    return ed.languages.some((lang) => {
      const code = (lang.key || "").replace("/languages/", "").toLowerCase();
      const resolvedName = LANGUAGE_NAME_MAP[code] || code;
      return resolvedName.toLowerCase().includes("english");
    });
  };

  const zhEditions = [];
  const enEditions = [];
  const otherEditions = [];
  editions.forEach((ed) => {
    if (isZh(ed)) {
      zhEditions.push(ed);
    } else if (isEn(ed)) {
      enEditions.push(ed);
    } else {
      otherEditions.push(ed);
    }
  });

  const listDiv = document.createElement("div");
  listDiv.className = "edition-list";

  const renderSingleEdition = (ed, targetContainer) => {
    const title = ed.title || work.title || "Unknown Title";
    const author = (work.author_name || []).join(", ") || "Unknown Author";
    const year = ed.publish_date || "Unknown Year";
    const isbn = ed.isbn_13 || ed.isbn_10 || "No ISBN";

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
      e.stopPropagation();
      if (onChooseEdition) onChooseEdition(work, ed, itemEl);
    });
    targetContainer.appendChild(itemEl);
  };

  const createGroup = (titleText, groupEditions, defaultExpanded) => {
    if (groupEditions.length === 0) return null;

    const groupEl = document.createElement("div");
    groupEl.className = "edition-group";
    if (defaultExpanded) {
      groupEl.classList.add("expanded");
    }

    const headerBtn = document.createElement("button");
    headerBtn.type = "button";
    headerBtn.className = "edition-group-header";

    const labelSpan = document.createElement("span");
    labelSpan.textContent = `${titleText} (${groupEditions.length})`;

    const chevronSpan = document.createElement("span");
    chevronSpan.className = "group-chevron";
    chevronSpan.textContent = "▼";

    headerBtn.appendChild(labelSpan);
    headerBtn.appendChild(chevronSpan);

    const contentDiv = document.createElement("div");
    contentDiv.className = "edition-group-content";
    contentDiv.hidden = !defaultExpanded;

    groupEditions.forEach((ed) => {
      renderSingleEdition(ed, contentDiv);
    });

    headerBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const isHidden = contentDiv.hidden;
      contentDiv.hidden = !isHidden;
      groupEl.classList.toggle("expanded", isHidden);
    });

    groupEl.appendChild(headerBtn);
    groupEl.appendChild(contentDiv);
    return groupEl;
  };

  const hasZhOrEn = zhEditions.length > 0 || enEditions.length > 0;

  const zhGroup = createGroup("中文版本", zhEditions, false);
  const enGroup = createGroup("英文版本", enEditions, false);
  const otherGroup = createGroup("其他語言版本", otherEditions, false);

  if (zhGroup) listDiv.appendChild(zhGroup);
  if (enGroup) listDiv.appendChild(enGroup);
  if (otherGroup) listDiv.appendChild(otherGroup);

  container.appendChild(listDiv);
}

// ---------------------------------------------------------------------------
// Candidate list renderer
// ---------------------------------------------------------------------------

/**
 * Renders the candidate work cards into #candidate-list.
 * @param {object[]} works
 * @param {{ onChooseCandidate: (work: object) => void, onChooseEdition: (work: object, edition: object, el: HTMLElement) => void }} callbacks
 */
export function renderCandidates(works, { onChooseCandidate, onChooseEdition } = {}) {
  const candidateList = document.querySelector("#candidate-list");
  const candidateTemplate = document.querySelector("#candidate-template");
  const candidateSection = document.querySelector("#candidate-section");
  if (!candidateList || !candidateTemplate) return;

  candidateList.replaceChildren();

  const currentSourceObj = SOURCES.find(p => p.id === state.currentTitleSource);

  works.forEach((work) => {
    const hasMultipleEditions = typeof work.edition_count === "number" && work.edition_count > 1;
    const enableExtend = currentSourceObj && currentSourceObj.enable_extend_editions === true && hasMultipleEditions;

    const fragment = candidateTemplate.content.cloneNode(true);
    const cardEl = fragment.querySelector(".candidate-card");
    if (cardEl) {
      cardEl.dataset.key = work.key;
      if (enableExtend) cardEl.classList.add("expandable");
    }
    fragment.querySelector(".candidate-title").textContent = work.title;

    const authorText = `作者：${(work.author_name || ["Unknown"]).join("、")}`;
    const publishText = work.first_publish_year ? `首版 ${work.first_publish_year}` : "";
    const editionText = work.edition_count ? `${work.edition_count.toLocaleString()} 個版本` : "";

    const statusTag = fragment.querySelector(".candidate-status-tag");
    if (statusTag && work.key && (work.key.startsWith("gr:") || work.key.startsWith("sg:")) && work.status) {
      const shortInfo = getShortStatus(work.status);
      if (shortInfo) {
        statusTag.textContent = shortInfo.text;
        statusTag.title = work.status;
        statusTag.hidden = false;
        statusTag.className = `candidate-status-tag status-tag-${shortInfo.type}`;
      } else {
        statusTag.hidden = true;
      }
    }

    const metaText = [authorText, publishText, editionText].filter(Boolean).join(" · ") + " ↗";
    const metaLink = fragment.querySelector(".candidate-meta");
    const extUrl = getWorkExternalUrl(work.key);
    if (metaLink) {
      metaLink.textContent = metaText;
      if (extUrl) { metaLink.href = extUrl; } else { metaLink.removeAttribute("href"); }
    }

    const chevronEl = fragment.querySelector(".candidate-chevron");
    if (chevronEl) chevronEl.hidden = !enableExtend;

    const selectBtn = fragment.querySelector(".select-work");
    selectBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (onChooseCandidate) onChooseCandidate(work);
    });

    if (enableExtend) {
      const mainRow = fragment.querySelector(".candidate-main-row");
      const editionsArea = fragment.querySelector(".candidate-editions-area");

      mainRow.addEventListener("click", (e) => {
        if (e.target.closest(".select-work") || e.target.closest(".candidate-link")) return;

        const isCurrentlyHidden = editionsArea.hidden;
        if (isCurrentlyHidden) {
          // Collapse all other expanded cards (accordion behaviour)
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

        // 1. Use memory-cached editions if available
        if (work.fetched_editions) {
          renderEditionsList(editionsArea, work, work.fetched_editions, false, onChooseEdition);
          return;
        }

        // 2. Use localStorage cached editions if available
        const cachedEditions = getCachedData("editions:" + work.key);
        if (cachedEditions) {
          work.fetched_editions = cachedEditions;
          work.editions_state = {
            status: 'success',
            promise: Promise.resolve(cachedEditions)
          };
          renderEditionsList(editionsArea, work, cachedEditions, false, onChooseEdition);
          return;
        }

        // 3. Check memory state (to prevent duplicate queries if clicked repeatedly during loading)
        let editionsState = work.editions_state;
        if (editionsState && editionsState.status === 'loading') {
          editionsArea.innerHTML = '<div class="loading-editions">載入版本資訊中...</div>';
          editionsState.promise.then((editionsList) => {
            if (!editionsArea.hidden) {
              renderEditionsList(editionsArea, work, editionsList, false, onChooseEdition);
            }
          }).catch((err) => {
            if (!editionsArea.hidden) {
              editionsArea.innerHTML = '<div class="error-editions">無法載入版本資訊 ⚠️</div>';
            }
          });
          return;
        }

        // 4. Trigger fetch and store promise
        editionsState = {
          status: 'loading',
          promise: (async () => {
            const resp = await fetch(`/api/work-editions?work_id=${encodeURIComponent(work.key)}`);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            const editionsList = data.entries || [];
            work.fetched_editions = editionsList;
            setCachedData("editions:" + work.key, editionsList);
            return editionsList;
          })()
        };
        work.editions_state = editionsState;

        editionsArea.innerHTML = '<div class="loading-editions">載入版本資訊中...</div>';
        editionsState.promise.then((editionsList) => {
          editionsState.status = 'success';
          if (!editionsArea.hidden) {
            renderEditionsList(editionsArea, work, editionsList, false, onChooseEdition);
          }
        }).catch((err) => {
          editionsState.status = 'error';
          console.error("Failed to load editions:", err);
          if (!editionsArea.hidden) {
            editionsArea.innerHTML = '<div class="error-editions">無法載入版本資訊 ⚠️</div>';
          }
        });
      });
    }

    // Restore selected state if this work was already chosen
    if (state.currentSelectedWork && state.currentSelectedWork.key === work.key) {
      if (cardEl) cardEl.classList.add("selected");
      selectBtn.textContent = "已選取";
      selectBtn.disabled = true;
    }

    candidateList.append(fragment);
  });

  if (candidateSection) candidateSection.hidden = false;
}
