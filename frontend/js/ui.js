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

export function renderTableHeaders(headerRow) {
  if (!headerRow) return;
  headerRow.replaceChildren();

  PROVIDERS.forEach((provider) => {
    const suffix = PROVIDER_CHECKBOX_SUFFIX[provider.id];
    const th = document.createElement("th");
    th.className = `col-${suffix}`;
    th.textContent = provider.label;
    headerRow.appendChild(th);
  });
}

export function renderTitleProviderTabs(container, currentTitleProvider) {
  if (!container) return;
  container.replaceChildren();

  PROVIDERS.forEach((provider) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "title-provider-tab-btn";
    if (provider.id === currentTitleProvider) {
      btn.classList.add("active");
    }
    btn.dataset.providerId = provider.id;
    btn.textContent = provider.label;
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
  PROVIDERS.forEach((provider) => {
    const suffix = PROVIDER_CHECKBOX_SUFFIX[provider.id];
    css += `
      .hide-${suffix}-score .col-${suffix} {
        display: none !important;
      }
    `;
  });
  styleEl.textContent = css;
}



