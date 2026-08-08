// Shared mutable application state — single source of truth for wizard navigation.
// All modules read/write this object directly; no setter boilerplate needed.
export const state = {
  currentQuery: "",
  currentPage: 1,
  currentStep: 1,
  currentTitleSource: "open_library",
  currentSelectedWork: null,
};
