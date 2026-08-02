import { PROVIDERS, STRATEGIES, PROVIDER_CHECKBOX_SUFFIX, LANGUAGE_NAME_MAP, MAX_EDITIONS } from './constants.js';

export function renderProviderToggles(container) {
  if (!container) return;
  container.innerHTML = '<span class="toggle-title">來源：</span>';

  PROVIDERS.forEach((provider) => {
    const suffix = PROVIDER_CHECKBOX_SUFFIX[provider.id];
    const item = document.createElement("div");
    item.className = "provider-toggle-item";

    const label = document.createElement("label");
    label.className = "checkbox-label";

    const input = document.createElement("input");
    input.type = "checkbox";
    input.id = `score-${suffix}`;

    const span = document.createElement("span");
    span.textContent = provider.label;

    label.appendChild(input);
    label.appendChild(span);
    item.appendChild(label);
    container.appendChild(item);
  });
}

export function renderStrategySelects(strategyRow) {
  if (!strategyRow) return;
  strategyRow.replaceChildren();

  strategyRow.appendChild(document.createElement("th"));
  strategyRow.appendChild(document.createElement("th"));

  PROVIDERS.forEach((provider) => {
    const suffix = PROVIDER_CHECKBOX_SUFFIX[provider.id];
    const th = document.createElement("th");
    th.className = `col-${suffix}`;

    const select = document.createElement("select");
    select.className = "strategy-select";
    select.dataset.provider = provider.id;

    STRATEGIES.forEach((strat) => {
      const opt = document.createElement("option");
      opt.value = strat.value;
      opt.textContent = strat.label;
      select.appendChild(opt);
    });

    th.appendChild(select);
    strategyRow.appendChild(th);
  });
}

export function updateTableVisibility(ratingTable) {
  if (ratingTable) {
    PROVIDERS.forEach((provider) => {
      const suffix = PROVIDER_CHECKBOX_SUFFIX[provider.id];
      const checkbox = document.querySelector(`#score-${suffix}`);
      ratingTable.classList.toggle(`hide-${suffix}-score`, checkbox ? !checkbox.checked : true);
    });
  }
}

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

export function openEditionsModal(title, editions) {
  const editionsModal = document.querySelector("#editions-modal");
  const modalTitle = document.querySelector("#editions-modal-title");
  const modalNote = document.querySelector("#editions-modal-note");
  const modalList = document.querySelector("#editions-modal-list");

  if (!editionsModal || !modalTitle || !modalNote || !modalList) return;

  modalTitle.textContent = `《${title}》的版本列表`;

  const size = editions.size || editions.entries?.length || 0;
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
