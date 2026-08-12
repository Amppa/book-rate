import { state } from './state.js';
import { SOURCES, SOURCE_PREFIX } from './constants.js';
import { markCandidateSelected } from './candidates.js';
import { removeBrackets } from './utils.js';

// Injected dependency: avoids a circular import between wizard ↔ ratings.
let _onSelectWork = null;

/**
 * Call once at startup to inject the selectWork function from ratings.js.
 * @param {{ onSelectWork: (work: object) => void }} deps
 */
export function initWizard({ onSelectWork }) {
  _onSelectWork = onSelectWork;

  // Monitor the bracket removal checkbox and clean existing fields when checked
  const removeBracketsCb = document.querySelector("#bm-remove-brackets");
  if (removeBracketsCb) {
    removeBracketsCb.addEventListener("change", (e) => {
      if (e.target.checked) {
        const titleEl = document.querySelector("#bm-title");
        const titleZhEl = document.querySelector("#bm-title-zh");
        const authorEl = document.querySelector("#bm-author");

        if (titleEl && titleEl.value) {
          titleEl.value = titleEl.value.split('\n').map(removeBrackets).filter(Boolean).join('\n');
        }
        if (titleZhEl && titleZhEl.value) {
          titleZhEl.value = titleZhEl.value.split('\n').map(removeBrackets).filter(Boolean).join('\n');
        }
        if (authorEl && authorEl.value) {
          authorEl.value = authorEl.value.split('\n').map(removeBrackets).filter(Boolean).join('\n');
        }
      }
    });
  }
}

// ---------------------------------------------------------------------------
// Step navigation
// ---------------------------------------------------------------------------

export function goToStep(step) {
  state.currentStep = step;
  document.querySelectorAll(".wizard-step").forEach((el, index) => {
    if (index + 1 === step) {
      el.classList.add("active");
    } else {
      el.classList.remove("active");
    }
  });

  if (step === 3) {
    const strategyRow = document.querySelector("#score-strategy-row");
    if (strategyRow) {
      strategyRow.hidden = (state.searchMode === "quick_search");
    }
    const metadataCard = document.querySelector("#step3-metadata-card");
    if (metadataCard) {
      metadataCard.hidden = (state.searchMode === "quick_search");
    }
  }
}

// ---------------------------------------------------------------------------
// Textarea helpers
// ---------------------------------------------------------------------------

/**
 * Appends unique, non-empty items to a textarea (one per line).
 * Keeps only the most recent `maxLimit` lines.
 */
export function appendAndLimitTextarea(textareaEl, newItems, maxLimit) {
  if (!textareaEl) return;

  const items = Array.isArray(newItems) ? newItems : [newItems];
  const validItems = items.map(item => String(item).trim()).filter(Boolean);
  if (validItems.length === 0) return;

  const currentVal = textareaEl.value.trim();
  let lines = currentVal ? currentVal.split('\n').map(s => s.trim()) : [];

  validItems.forEach(item => {
    if (!lines.includes(item)) lines.push(item);
  });

  if (lines.length > maxLimit) lines = lines.slice(lines.length - maxLimit);
  textareaEl.value = lines.join('\n');
}

const hasCjk = (str) => /[\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff\uac00-\ud7a3]/.test(str);

// ---------------------------------------------------------------------------
// Candidate / edition selection (fills Step-2 metadata panel)
// ---------------------------------------------------------------------------

/** Marks a work as selected and fills the Step-2 metadata fields. */
export function chooseCandidate(work) {
  state.currentSelectedWork = work;
  markCandidateSelected(document.querySelector("#candidate-list"), work.key);

  // Clear any active edition highlights
  document.querySelectorAll(".edition-item").forEach((el) => el.classList.remove("selected"));

  const titleEl = document.querySelector("#bm-title");
  const titleZhEl = document.querySelector("#bm-title-zh");
  const authorEl = document.querySelector("#bm-author");
  const publishDateEl = document.querySelector("#bm-publish-date");
  const isbnEl = document.querySelector("#bm-isbn");

  const removeBracketsActive = document.querySelector("#bm-remove-brackets")?.checked ?? false;

  if (work.title) {
    let titleVal = work.title;
    if (removeBracketsActive) titleVal = removeBrackets(titleVal);
    if (hasCjk(titleVal)) {
      appendAndLimitTextarea(titleZhEl, titleVal, 4);
    } else {
      appendAndLimitTextarea(titleEl, titleVal, 4);
    }
  }

  if (work.author_name && work.author_name.length > 0) {
    let validAuthors = work.author_name
      .map(name => name.trim())
      .filter(name => name && name.toLowerCase() !== 'unknown');
    if (removeBracketsActive) {
      validAuthors = validAuthors.map(name => removeBrackets(name)).filter(Boolean);
    }
    appendAndLimitTextarea(authorEl, validAuthors, 8);
  }

  if (publishDateEl) publishDateEl.value = work.first_publish_year || "";

  if (work.isbn) {
    const isbnVal = Array.isArray(work.isbn) ? work.isbn[0] : work.isbn;
    appendAndLimitTextarea(isbnEl, isbnVal, 8);
  }
}

/** Selects a specific edition of a work and fills the Step-2 metadata fields. */
export function chooseEdition(work, edition, itemEl) {
  chooseCandidate(work);

  document.querySelectorAll(".edition-item").forEach((el) => el.classList.remove("selected"));
  if (itemEl) itemEl.classList.add("selected");

  const titleEl = document.querySelector("#bm-title");
  const titleZhEl = document.querySelector("#bm-title-zh");
  const publishDateEl = document.querySelector("#bm-publish-date");
  const isbnEl = document.querySelector("#bm-isbn");

  const removeBracketsActive = document.querySelector("#bm-remove-brackets")?.checked ?? false;

  const titleVal = edition.title || work.title;
  if (titleVal) {
    let finalTitle = titleVal;
    if (removeBracketsActive) finalTitle = removeBrackets(finalTitle);
    if (hasCjk(finalTitle)) {
      appendAndLimitTextarea(titleZhEl, finalTitle, 4);
    } else {
      appendAndLimitTextarea(titleEl, finalTitle, 4);
    }
  }

  const pubDateVal = edition.publish_date || (work.first_publish_year ? String(work.first_publish_year) : "");
  if (publishDateEl && pubDateVal) publishDateEl.value = pubDateVal;

  const isbnVal = edition.isbn_13 || edition.isbn_10;
  if (isbnEl && isbnVal) appendAndLimitTextarea(isbnEl, isbnVal, 8);
}

/** Clears the Step-2 metadata panel (called on a new search). */
export function resetMetadataPanel(query) {
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
  state.currentSelectedWork = null;
}

/**
 * Programmatically populates Step 2 metadata fields and transitions
 * directly to Step 3 for Quick Search mode.
 */
export function directToStep3(query) {
  resetMetadataPanel(query);

  const titleEl = document.querySelector("#bm-title");
  const titleZhEl = document.querySelector("#bm-title-zh");
  const isbnEl = document.querySelector("#bm-isbn");

  const clean = query.replace(/[- ]/g, '');
  const isIsbn = /^\d{10}$|^\d{13}$/.test(clean);

  if (isIsbn) {
    if (isbnEl) isbnEl.value = clean;
  } else {
    if (hasCjk(query)) {
      if (titleZhEl) titleZhEl.value = query;
    } else {
      if (titleEl) titleEl.value = query;
    }
  }

  confirmToStep3();
}

// ---------------------------------------------------------------------------
// Step-3 metadata readers (used by ratings.js for the API call)
// ---------------------------------------------------------------------------

export function getStep3Metadata() {
  const searchName = document.querySelector("#s3-search-name")?.value.trim() || "";
  const titleList = (document.querySelector("#s3-title")?.value || "").split("\n").map(s => s.trim()).filter(Boolean);
  const titleZhList = (document.querySelector("#s3-title-zh")?.value || "").split("\n").map(s => s.trim()).filter(Boolean);
  const authorList = (document.querySelector("#s3-author")?.value || "").split("\n").map(s => s.trim()).filter(Boolean);
  const isbnList = (document.querySelector("#s3-isbn")?.value || "").split("\n").map(s => s.trim()).filter(Boolean);
  return { searchName, titleList, titleZhList, authorList, isbnList };
}

export function getSelectedStrategies() {
  const strats = {};
  document.querySelectorAll(".strategy-select").forEach((sel) => {
    const source = sel.dataset.source;
    if (source) strats[source] = sel.value;
  });
  return strats;
}

export function getActiveRateSourcesList() {
  const rateSources = [];
  SOURCES.forEach((source) => {
    const suffix = SOURCE_PREFIX[source.id];
    const checkbox = document.querySelector(`#score-${suffix}`);
    if (checkbox && checkbox.checked) rateSources.push(source.id);
  });
  return rateSources;
}

export function getSourceDefaultStrat(provId) {
  return SOURCES.find(p => p.id === provId)?.defaultStrategy || "title_list";
}

// ---------------------------------------------------------------------------
// Step-2 → Step-3 transition
// ---------------------------------------------------------------------------

/**
 * Validates Step-2 metadata, copies it to Step-3 fields, builds the work object,
 * then calls the injected selectWork (ratings.js) to proceed.
 */
export function confirmToStep3() {
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

  // Copy values to Step-3 metadata fields
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

  let workToUse = state.currentSelectedWork;
  if (!workToUse) {
    const keyIdentifier = (isbnVal || searchNameVal || Date.now().toString()).trim().replace(/\s+/g, '_');
    workToUse = {
      key: "custom:" + keyIdentifier,
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

  if (_onSelectWork) _onSelectWork(workToUse);
}
