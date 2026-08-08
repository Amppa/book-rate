import { HISTORY_KEY } from './constants.js';

export function getHistory() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY)) || [];
  } catch {
    return [];
  }
}

export function saveHistory(query) {
  const history = [query, ...getHistory().filter((item) => item !== query)].slice(0, 5);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
}

/**
 * Renders the search history list.
 * @param {(query: string) => void} onSelect - called when a history item is clicked
 */
export function renderHistory(onSelect) {
  const historyList = document.querySelector("#history-list");
  const historySection = document.querySelector("#history-section");
  if (!historyList || !historySection) return;

  const history = getHistory();
  historyList.replaceChildren();
  historySection.hidden = !history.length;

  history.forEach((query) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "history-item";
    button.textContent = query;
    button.addEventListener("click", () => {
      if (onSelect) onSelect(query);
    });
    historyList.append(button);
  });
}
