import { CACHE_PREFIX, ONE_DAY_MS } from './constants.js';

export function getCachedData(key) {
  try {
    const cached = localStorage.getItem(CACHE_PREFIX + key);
    if (!cached) return null;
    const { data, timestamp } = JSON.parse(cached);
    if (Date.now() - timestamp > 7 * ONE_DAY_MS) {
      localStorage.removeItem(CACHE_PREFIX + key);
      return null;
    }
    return data;
  } catch (e) {
    return null;
  }
}

export function setCachedData(key, data) {
  try {
    const record = { data, timestamp: Date.now() };
    localStorage.setItem(CACHE_PREFIX + key, JSON.stringify(record));
  } catch (e) {
    console.warn("Failed to write to localStorage cache:", e);
  }
}

export function getRatingCache(workKey, source, strategy) {
  const key = `bookrate:rating:${workKey}:${source}:${strategy}`;
  try {
    const cached = localStorage.getItem(key);
    if (!cached) return null;
    const { data, timestamp } = JSON.parse(cached);
    if (Date.now() - timestamp > 7 * ONE_DAY_MS) {
      localStorage.removeItem(key);
      return null;
    }
    return data;
  } catch (e) {
    return null;
  }
}

export function setRatingCache(workKey, source, strategy, data) {
  const key = `bookrate:rating:${workKey}:${source}:${strategy}`;
  try {
    const record = { data, timestamp: Date.now() };
    localStorage.setItem(key, JSON.stringify(record));
  } catch (e) {
    console.warn("Failed to write rating to localStorage cache:", e);
  }
}

export function cleanExpiredCache() {
  try {
    const keysToRemove = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (!key) continue;
      
      if (key.startsWith(CACHE_PREFIX)) {
        const cached = localStorage.getItem(key);
        if (cached) {
          const { timestamp } = JSON.parse(cached);
          if (Date.now() - timestamp > 7 * ONE_DAY_MS) {
            keysToRemove.push(key);
          }
        }
      } else if (key.startsWith("bookrate:rating:")) {
        const cached = localStorage.getItem(key);
        if (cached) {
          const { timestamp } = JSON.parse(cached);
          if (Date.now() - timestamp > 7 * ONE_DAY_MS) {
            keysToRemove.push(key);
          }
        }
      }
    }
    keysToRemove.forEach((key) => localStorage.removeItem(key));
  } catch (e) { }
}

export function clearAllStep2Cache() {
  try {
    const keysToRemove = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith(CACHE_PREFIX)) {
        keysToRemove.push(key);
      }
    }
    keysToRemove.forEach((k) => localStorage.removeItem(k));
  } catch (e) {
    console.warn("Failed to clear Step 2 cache:", e);
  }
}

export function clearAllStep3Cache() {
  try {
    const keysToRemove = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith("bookrate:rating:")) {
        keysToRemove.push(key);
      }
    }
    keysToRemove.forEach((k) => localStorage.removeItem(k));
  } catch (e) {
    console.warn("Failed to clear Step 3 cache:", e);
  }
}

export function clearEditionsCache() {
  try {
    const prefix = CACHE_PREFIX + "editions:";
    const keysToRemove = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith(prefix)) {
        keysToRemove.push(key);
      }
    }
    keysToRemove.forEach((k) => localStorage.removeItem(k));
  } catch (e) {
    console.warn("Failed to clear editions cache:", e);
  }
}

export function clearWorkRatingsCache(workKey) {
  try {
    const prefix = `bookrate:rating:${workKey}:`;
    const keysToRemove = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith(prefix)) {
        keysToRemove.push(key);
      }
    }
    keysToRemove.forEach((k) => localStorage.removeItem(k));
  } catch (e) {
    console.warn("Failed to clear work ratings cache:", e);
  }
}

