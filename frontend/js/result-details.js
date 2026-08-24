/**
 * Result Details Component for Step 3 Comparison Table
 * Renders collapsible metadata panel (<details>) without emojis and with strict field ordering.
 */

export const DETAIL_FIELD_DEFINITIONS = [
  { key: "author", label: "作者:" },
  { key: "translator", label: "譯者:" },
  { key: "publisher", label: "出版社:" },
  { key: "publish_date", label: "出版日期:" },
  { key: "language", label: "語言:" },
  { key: "original_title", label: "原作名:" },
  { key: "edition_count", label: "版本數:" },
  { key: "isbn", label: "ISBN:" },
  { key: "work_id", label: "ID:" }
];

const INVALID_METADATA_VALUES = new Set(["", "none", "unknown", "null", "undefined", "n/a"]);

/**
 * Checks whether a metadata field value is valid and displayable.
 * @param {*} val 
 * @returns {boolean}
 */
export function isValidDetailValue(val) {
  if (val === null || val === undefined) return false;
  const str = String(val).trim();
  if (str === "") return false;
  return !INVALID_METADATA_VALUES.has(str.toLowerCase());
}

/**
 * Builds a collapsible book details DOM element.
 * @param {Object|null} bookInfo - Standard 9-field metadata dictionary
 * @returns {HTMLDetailsElement|null}
 */
export function buildBookDetailsElement(bookInfo) {
  if (!bookInfo || typeof bookInfo !== "object") return null;

  const validEntries = DETAIL_FIELD_DEFINITIONS.filter((f) => isValidDetailValue(bookInfo[f.key]));
  if (validEntries.length === 0) return null;

  const details = document.createElement("details");
  details.className = "source-book-details";

  const summary = document.createElement("summary");
  summary.className = "source-details-summary";
  summary.textContent = "details  ▶";

  details.addEventListener("toggle", () => {
    summary.textContent = details.open ? "details  ▼" : "details  ▶";
  });

  details.appendChild(summary);

  const content = document.createElement("div");
  content.className = "source-details-content";

  validEntries.forEach((f) => {
    const row = document.createElement("div");
    row.className = "source-detail-row";

    const label = document.createElement("span");
    label.className = "source-detail-label";
    label.textContent = f.label;

    const val = document.createElement("span");
    val.className = "source-detail-value";
    val.textContent = String(bookInfo[f.key]).trim();

    row.appendChild(label);
    row.appendChild(val);
    content.appendChild(row);
  });

  details.appendChild(content);
  return details;
}
