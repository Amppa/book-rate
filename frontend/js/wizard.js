import { state } from './state.js';
import { SOURCES, SOURCE_PREFIX } from './constants.js';
import { removeBrackets, toHalfWidth, cleanIsbnText, normalizeComparisonKey } from './utils.js';

/**
 * Initialises wizard event listeners.
 */
export function initWizard() {
  // Monitor the bracket removal checkbox and clean/deduplicate existing fields
  const removeBracketsCb = document.querySelector("#bm-remove-brackets");
  if (removeBracketsCb) {
    removeBracketsCb.addEventListener("change", (e) => {
      const isChecked = e.target.checked;
      const titleEl = document.querySelector("#bm-title");
      const authorEl = document.querySelector("#bm-author");

      if (titleEl && titleEl.value) {
        const lines = titleEl.value.split('\n').filter(Boolean);
        titleEl.value = "";
        const res = appendAndLimitTextarea(titleEl, lines, 5, { type: "title", removeBrackets: isChecked });
        const hintEl = document.querySelector("#bm-title-hint");
        if (hintEl && res && res.duplicateCount > 0) {
          hintEl.textContent = "（已自動去重）";
        }
      }
      if (authorEl && authorEl.value) {
        const lines = authorEl.value.split('\n').filter(Boolean);
        authorEl.value = "";
        appendAndLimitTextarea(authorEl, lines, 5, { type: "author", removeBrackets: isChecked });
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
 * Appends unique, non-empty items to a textarea (one per line) with normalization.
 * Keeps only the most recent `maxLimit` lines.
 *
 * @param {HTMLTextAreaElement|null} textareaEl
 * @param {string|string[]} newItems
 * @param {number} maxLimit
 * @param {Object} [options]
 * @param {string} [options.type] - "title" | "author" | "isbn" | "raw"
 * @param {boolean} [options.removeBrackets] - whether to apply removeBrackets
 * @returns {{ addedCount: number, duplicateCount: number }}
 */
export function appendAndLimitTextarea(textareaEl, newItems, maxLimit, options = {}) {
  if (!textareaEl) return { addedCount: 0, duplicateCount: 0 };

  const items = Array.isArray(newItems) ? newItems : [newItems];
  const validItems = items.map(item => String(item).trim()).filter(Boolean);
  if (validItems.length === 0) return { addedCount: 0, duplicateCount: 0 };

  const currentVal = textareaEl.value.trim();
  let lines = currentVal ? currentVal.split('\n').map(s => s.trim()).filter(Boolean) : [];

  const existingKeys = new Set(
    lines.map(line => {
      if (options.type === "isbn") return cleanIsbnText(line);
      return normalizeComparisonKey(line, false);
    })
  );

  let addedCount = 0;
  let duplicateCount = 0;

  validItems.forEach((rawItem) => {
    let cleanItem = rawItem;
    if (options.type === "isbn") {
      cleanItem = cleanIsbnText(rawItem);
    } else {
      cleanItem = toHalfWidth(rawItem);
      if (options.removeBrackets) {
        cleanItem = removeBrackets(cleanItem);
      }
    }

    if (!cleanItem) return;

    const compKey = options.type === "isbn"
      ? cleanItem
      : normalizeComparisonKey(cleanItem, false);

    if (existingKeys.has(compKey)) {
      duplicateCount++;
    } else {
      existingKeys.add(compKey);
      lines.push(cleanItem);
      addedCount++;
    }
  });

  if (lines.length > maxLimit) {
    lines = lines.slice(lines.length - maxLimit);
  }
  textareaEl.value = lines.join('\n');

  return { addedCount, duplicateCount };
}

// ---------------------------------------------------------------------------
// Candidate / edition selection (fills Step-2 metadata panel)
// ---------------------------------------------------------------------------

/** Marks a work as selected and fills the Step-2 metadata fields. */
export function chooseCandidate(work) {
  state.currentSelectedWork = work;

  const titleEl = document.querySelector("#bm-title");
  const authorEl = document.querySelector("#bm-author");
  const publishDateEl = document.querySelector("#bm-publish-date");
  const isbnEl = document.querySelector("#bm-isbn");
  const hintEl = document.querySelector("#bm-title-hint");

  const removeBracketsActive = document.querySelector("#bm-remove-brackets")?.checked ?? false;

  if (work.title) {
    const res = appendAndLimitTextarea(titleEl, work.title, 5, {
      type: "title",
      removeBrackets: removeBracketsActive
    });
    if (hintEl) {
      if (res.duplicateCount > 0 && res.addedCount === 0) {
        hintEl.textContent = "（已自動去重）";
      } else if (res.addedCount > 0) {
        hintEl.textContent = "";
      }
    }
  }

  if (work.author_name && work.author_name.length > 0) {
    const validAuthors = work.author_name
      .map(name => name.trim())
      .filter(name => name && name.toLowerCase() !== 'unknown');
    appendAndLimitTextarea(authorEl, validAuthors, 5, {
      type: "author",
      removeBrackets: removeBracketsActive
    });
  }

  if (publishDateEl) publishDateEl.value = work.first_publish_year || "";

  if (work.isbn) {
    appendAndLimitTextarea(isbnEl, work.isbn, 5, { type: "isbn" });
  }
}

/** Selects a specific edition of a work and fills the Step-2 metadata fields. */
export function chooseEdition(work, edition) {
  chooseCandidate(work);

  const titleEl = document.querySelector("#bm-title");
  const publishDateEl = document.querySelector("#bm-publish-date");
  const isbnEl = document.querySelector("#bm-isbn");
  const hintEl = document.querySelector("#bm-title-hint");

  const removeBracketsActive = document.querySelector("#bm-remove-brackets")?.checked ?? false;

  const titleVal = edition.title || work.title;
  if (titleVal) {
    const res = appendAndLimitTextarea(titleEl, titleVal, 5, {
      type: "title",
      removeBrackets: removeBracketsActive
    });
    if (hintEl) {
      if (res.duplicateCount > 0 && res.addedCount === 0) {
        hintEl.textContent = "（已自動去重）";
      } else if (res.addedCount > 0) {
        hintEl.textContent = "";
      }
    }
  }

  const pubDateVal = edition.publish_date || (work.first_publish_year ? String(work.first_publish_year) : "");
  if (publishDateEl && pubDateVal) publishDateEl.value = pubDateVal;

  const isbnVal = edition.isbn_13 || edition.isbn_10;
  if (isbnEl && isbnVal) appendAndLimitTextarea(isbnEl, isbnVal, 5, { type: "isbn" });
}

/** Clears the Step-2 metadata panel (called on a new search). */
export function resetMetadataPanel(query) {
  const searchNameEl = document.querySelector("#bm-search-name");
  const titleEl = document.querySelector("#bm-title");
  const authorEl = document.querySelector("#bm-author");
  const publishDateEl = document.querySelector("#bm-publish-date");
  const isbnEl = document.querySelector("#bm-isbn");

  if (searchNameEl) searchNameEl.value = query || "";
  if (titleEl) titleEl.value = "";
  if (authorEl) authorEl.value = "";
  if (publishDateEl) publishDateEl.value = "";
  if (isbnEl) isbnEl.value = "";
  const hintEl = document.querySelector("#bm-title-hint");
  if (hintEl) hintEl.textContent = "";
  state.currentSelectedWork = null;

  const splitLayout = document.querySelector(".step3-split-layout");
  if (splitLayout) {
    splitLayout.classList.remove("s3-meta-collapsed");
  }
}

/**
 * Programmatically populates Step 2 metadata fields and transitions
 * directly to Step 3 for Quick Search mode.
 */
export function directToStep3(query) {
  resetMetadataPanel(query);

  const titleEl = document.querySelector("#bm-title");
  const isbnEl = document.querySelector("#bm-isbn");

  const clean = query.replace(/[- ]/g, '');
  const isIsbn = /^\d{10}$|^\d{13}$/.test(clean);

  if (isIsbn) {
    if (isbnEl) isbnEl.value = clean;
  } else {
    if (titleEl) titleEl.value = query;
  }

  confirmToStep3();
}

// ---------------------------------------------------------------------------
// Step-3 metadata readers (used by ratings.js for the API call)
// ---------------------------------------------------------------------------

export function getStep3Metadata() {
  const searchName = document.querySelector("#s3-search-name")?.value.trim() || "";
  const titleList = (document.querySelector("#s3-title")?.value || "").split("\n").map(s => s.trim()).filter(Boolean);
  const authorList = (document.querySelector("#s3-author")?.value || "").split("\n").map(s => s.trim()).filter(Boolean);
  const isbnList = (document.querySelector("#s3-isbn")?.value || "").split("\n").map(s => s.trim()).filter(Boolean);
  return { searchName, titleList, titleZhList: [], authorList, isbnList };
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
  return SOURCES.find(p => p.id === provId)?.defaultStrategy || "search_name";
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
  const s3Author = document.querySelector("#s3-author");
  const s3PublishDate = document.querySelector("#s3-publish-date");
  const s3Isbn = document.querySelector("#s3-isbn");

  if (s3SearchName) s3SearchName.value = searchNameVal;
  if (s3Title) s3Title.value = titleVal;
  if (s3Author) s3Author.value = authorVal;
  if (s3PublishDate) s3PublishDate.value = publishDateVal;
  if (s3Isbn) s3Isbn.value = isbnVal;

  let workToUse = state.currentSelectedWork;
  if (!workToUse) {
    const keyIdentifier = (isbnVal || searchNameVal || Date.now().toString()).trim().replace(/\s+/g, '_');
    workToUse = {
      key: "custom:" + keyIdentifier,
      title: titleVal || "",
      author_name: authorVal ? [authorVal] : ["Unknown"],
      first_publish_year: publishDateVal,
      isbn: isbnVal
    };
  } else {
    workToUse = {
      ...workToUse,
      title: titleVal || workToUse.title || "",
      author_name: authorVal ? authorVal.split(",").map((s) => s.trim()) : workToUse.author_name,
      first_publish_year: publishDateVal || workToUse.first_publish_year,
      isbn: isbnVal || workToUse.isbn
    };
  }

  window.dispatchEvent(new CustomEvent("bookrate:select-work", { detail: workToUse }));
}
