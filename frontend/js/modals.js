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
  const presetsTableBody = document.querySelector("#presets-table-body");
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

  function renderPresetsTable(presets) {
    if (!presetsTableBody) return;
    const fragment = document.createDocumentFragment();
    (presets || []).forEach((item) => {
      const tr = document.createElement("tr");

      const tdTitle = document.createElement("td");
      tdTitle.className = "clickable-preset";
      tdTitle.dataset.query = item.title || "";
      tdTitle.textContent = item.title || "";

      const tdIsbn = document.createElement("td");
      tdIsbn.className = "clickable-preset";
      tdIsbn.dataset.query = item.isbn || "";
      tdIsbn.textContent = item.isbn || "";

      const selectPreset = (q) => {
        if (q && searchInput) searchInput.value = q;
        if (q) {
          navigator.clipboard.writeText(q).catch((err) => {
            console.error("Failed to copy to clipboard:", err);
          });
        }
        close();
      };
      tdTitle.addEventListener("click", () => selectPreset(item.title));
      tdIsbn.addEventListener("click", () => selectPreset(item.isbn));

      tr.append(tdTitle, tdIsbn);
      fragment.append(tr);
    });
    presetsTableBody.replaceChildren(fragment);
  }

  openPresetsBtn.addEventListener("click", async () => {
    const presets = await loadPresets();
    renderPresetsTable(presets);
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
