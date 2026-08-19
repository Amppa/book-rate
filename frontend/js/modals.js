import { openModal, closeModal } from './ui.js';

// ---------------------------------------------------------------------------
// Presets Modal
// ---------------------------------------------------------------------------

/**
 * Initialises the presets (書單) modal.
 * @param {HTMLInputElement} searchInput - the main search field to fill on preset click
 */
export function initPresetsModal(searchInput) {
  const presetsModal = document.querySelector("#presets-modal");
  const openPresetsBtn = document.querySelector("#open-presets-btn");
  const closePresetsBtn = document.querySelector("#close-presets-btn");
  const presetsContainer = document.querySelector("#presets-container");
  if (!presetsModal || !openPresetsBtn || !closePresetsBtn) return;

  let cachedPresets = null;

  const close = () => closeModal(presetsModal);

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

  function renderPresetsList(presets) {
    if (!presetsContainer) return;
    const fragment = document.createDocumentFragment();
    (presets || []).forEach((item) => {
      const bubble = document.createElement("div");
      bubble.className = "preset-bubble";

      const selectPreset = (q) => {
        if (q && searchInput) searchInput.value = q;
        if (q) {
          navigator.clipboard.writeText(q).catch((err) => {
            console.error("Failed to copy to clipboard:", err);
          });
        }
        close();
      };

      const titleEl = document.createElement("div");
      titleEl.className = "preset-bubble-title";
      titleEl.title = "點擊填入書名並複製";
      titleEl.textContent = item.title || "";
      titleEl.addEventListener("click", (e) => {
        e.stopPropagation();
        selectPreset(item.title);
      });
      bubble.appendChild(titleEl);

      if (item.isbn) {
        const isbnEl = document.createElement("div");
        isbnEl.className = "preset-bubble-isbn";
        isbnEl.title = "點擊填入 ISBN 並複製";

        const isbnTag = document.createElement("span");
        isbnTag.className = "preset-isbn-badge";
        isbnTag.textContent = "ISBN";

        const isbnText = document.createElement("span");
        isbnText.className = "preset-isbn-text";
        isbnText.textContent = item.isbn;

        isbnEl.append(isbnTag, isbnText);
        isbnEl.addEventListener("click", (e) => {
          e.stopPropagation();
          selectPreset(item.isbn);
        });
        bubble.appendChild(isbnEl);
      }

      bubble.addEventListener("click", () => selectPreset(item.title));
      fragment.append(bubble);
    });
    presetsContainer.replaceChildren(fragment);
  }

  openPresetsBtn.addEventListener("click", async () => {
    const presets = await loadPresets();
    renderPresetsList(presets);
    openModal(presetsModal);
  });
  closePresetsBtn.addEventListener("click", close);
  presetsModal.addEventListener("click", (event) => {
    if (event.target === presetsModal) close();
  });
}

// ---------------------------------------------------------------------------
// Editions Modal
// ---------------------------------------------------------------------------

export function initEditionsModal() {
  const editionsModal = document.querySelector("#editions-modal");
  const closeEditionsBtn = document.querySelector("#close-editions-btn");
  if (!editionsModal || !closeEditionsBtn) return;

  const close = () => closeModal(editionsModal);
  closeEditionsBtn.addEventListener("click", close);
  editionsModal.addEventListener("click", (event) => {
    if (event.target === editionsModal) close();
  });
}

// ---------------------------------------------------------------------------
// Source Info Modal (dynamically loaded from source_info.html)
// ---------------------------------------------------------------------------

export function initSourceInfoModal() {
  const openSourceInfoBtn = document.querySelector("#open-source-info-btn");
  if (!openSourceInfoBtn) return;

  openSourceInfoBtn.addEventListener("click", async () => {
    // Always reload to reflect any updates
    let sourceInfoModal = document.querySelector("#source-info-modal");
    if (sourceInfoModal) {
      sourceInfoModal.remove();
      sourceInfoModal = null;
    }

    try {
      const resp = await fetch("./source_info.html?v=" + Date.now());
      if (resp.ok) {
        const htmlText = await resp.text();
        const tempDiv = document.createElement("div");
        tempDiv.innerHTML = htmlText;
        sourceInfoModal = tempDiv.firstElementChild;
        document.body.appendChild(sourceInfoModal);

        const closeBtn = sourceInfoModal.querySelector("#close-source-info-btn");
        const close = () => closeModal(sourceInfoModal);
        if (closeBtn) closeBtn.addEventListener("click", close);
        sourceInfoModal.addEventListener("click", (e) => {
          if (e.target === sourceInfoModal) close();
        });
      }
    } catch (err) {
      console.error("Failed to load source_info.html:", err);
    }

    if (sourceInfoModal) openModal(sourceInfoModal);
  });
}
