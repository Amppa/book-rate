import { SOURCES, STRATEGIES, SOURCE_PREFIX, LANGUAGE_NAME_MAP, MAX_EDITIONS } from './constants.js';

export function renderSourceToggles(container) {
  if (!container) return;
  container.innerHTML = '<span class="toggle-title">來源：</span>';

  SOURCES.forEach((source) => {
    if (source.id === "douban_api") return;
    const suffix = SOURCE_PREFIX[source.id];
    const item = document.createElement("div");
    item.className = "source-toggle-item";

    const label = document.createElement("label");
    label.className = "checkbox-label";

    const input = document.createElement("input");
    input.type = "checkbox";
    input.id = `score-${suffix}`;

    const span = document.createElement("span");
    span.textContent = source.label;

    label.appendChild(input);
    label.appendChild(span);
    item.appendChild(label);
    container.appendChild(item);
  });
}

export function renderStrategySelects(strategyRow) {
  if (!strategyRow) return;
  strategyRow.replaceChildren();

  SOURCES.forEach((source) => {
    if (source.id === "douban_api") return;
    const suffix = SOURCE_PREFIX[source.id];
    const th = document.createElement("th");
    th.className = `col-${suffix}`;

    const select = document.createElement("select");
    select.className = "strategy-select";
    select.dataset.source = source.id;

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
    SOURCES.forEach((source) => {
      if (source.id === "douban_api") return;
      const suffix = SOURCE_PREFIX[source.id];
      const checkbox = document.querySelector(`#score-${suffix}`);
      ratingTable.classList.toggle(`hide-${suffix}-score`, checkbox ? !checkbox.checked : true);
    });
  }
}

export function renderTableHeaders(headerRow) {
  if (!headerRow) return;
  headerRow.replaceChildren();

  SOURCES.forEach((source) => {
    if (source.id === "douban_api") return;
    const suffix = SOURCE_PREFIX[source.id];
    const th = document.createElement("th");
    th.className = `col-${suffix}`;
    th.textContent = source.label;
    headerRow.appendChild(th);
  });
}

export function renderTitleSourceTabs(container, currentTitleSource) {
  if (!container) return;
  container.replaceChildren();

  SOURCES.forEach((source) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "title-source-tab-btn";
    if (source.id === currentTitleSource) {
      btn.classList.add("active");
    }
    btn.dataset.sourceId = source.id;
    btn.textContent = source.label;
    container.appendChild(btn);
  });
}

export function initTableVisibilityStyles() {
  let styleEl = document.querySelector("#dynamic-visibility-styles");
  if (!styleEl) {
    styleEl = document.createElement("style");
    styleEl.id = "dynamic-visibility-styles";
    document.head.appendChild(styleEl);
  }
  let css = "";
  SOURCES.forEach((source) => {
    if (source.id === "douban_api") return;
    const suffix = SOURCE_PREFIX[source.id];
    css += `
      .hide-${suffix}-score .col-${suffix} {
        display: none !important;
      }
    `;
  });
  styleEl.textContent = css;
}

/**
 * Shows a modal element with the CSS "open" animation class.
 * @param {HTMLElement|null} el
 */
export function openModal(el) {
  if (!el) return;
  el.hidden = false;
  setTimeout(() => el.classList.add("open"), 10);
}

/**
 * Hides a modal element after the CSS close animation completes.
 * @param {HTMLElement|null} el
 * @param {number} [delay=300] - milliseconds matching the CSS transition duration
 */
export function closeModal(el, delay = 300) {
  if (!el) return;
  el.classList.remove("open");
  setTimeout(() => {
    if (!el.classList.contains("open")) el.hidden = true;
  }, delay);
}
