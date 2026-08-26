import { getCachedData, setCachedData } from './cache.js';
import { STORAGE_KEYS } from './constants.js';

/**
 * In-flight request deduplication map
 * key: cacheKey -> Promise<{ data: Array, fromCache: boolean }>
 */
const pendingRequests = new Map();

/**
 * Transparent fetch interface for title search candidates.
 * Automatically resolves from localStorage cache if hit,
 * reuses in-flight requests if in-progress, or fetches from backend.
 */
export async function fetchWorksWithCache({ query, page = 1, source, bypassCache = false }) {
  const cacheKey = `search:${query}:page:${page}:engines:${source}`;

  // 1. Cache hit check
  if (!bypassCache) {
    const cachedWorks = getCachedData(cacheKey);
    if (cachedWorks) {
      return { data: cachedWorks, fromCache: true };
    }
  }

  // 2. In-flight request deduplication check
  if (pendingRequests.has(cacheKey)) {
    return pendingRequests.get(cacheKey);
  }

  // 3. Fetch from API
  const requestPromise = (async () => {
    const apiKey = localStorage.getItem(STORAGE_KEYS.GOOGLE_API_KEY) || "";
    const works = await fetchSearchWorks(query, page, [source], apiKey);
    if (works) {
      setCachedData(cacheKey, works);
    }
    return { data: works, fromCache: false };
  })();

  pendingRequests.set(cacheKey, requestPromise);

  try {
    return await requestPromise;
  } finally {
    pendingRequests.delete(cacheKey);
  }
}

export async function fetchSearchWorks(query, page = 1, engines = [], googleKey = "") {
  const params = new URLSearchParams({
    q: query,
    page: page,
    engines: engines.join(","),
  });
  if (googleKey) {
    params.set("google_key", googleKey);
  }
  const response = await fetch(`/api/search?${params.toString()}`);
  if (!response.ok) {
    throw new Error(`Search request failed with status ${response.status}`);
  }
  return await response.json();
}

export async function fetchWorkEditions(workId) {
  const params = new URLSearchParams({ work_id: workId });
  const response = await fetch(`/api/work-editions?${params.toString()}`);
  if (!response.ok) {
    throw new Error(`Work editions request failed with status ${response.status}`);
  }
  return await response.json();
}

export async function streamWorkDetailsPost(payload, onMessage, onError, onDone) {
  try {
    const response = await fetch("/api/work-details-stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`Stream request failed with status ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop() || "";

      for (const block of lines) {
        const line = block.trim();
        if (line.startsWith("data: ")) {
          const rawJson = line.slice(6).trim();
          if (rawJson === "[DONE]") {
            if (onDone) onDone();
            return;
          }
          try {
            const data = JSON.parse(rawJson);
            if (data.type === "done") {
              if (onDone) onDone();
              return;
            }
            if (onMessage) onMessage(data);
          } catch (e) {
            console.error("Error parsing SSE JSON payload:", e, rawJson);
          }
        }
      }
    }
    if (onDone) onDone();
  } catch (err) {
    if (onError) onError(err);
  }
}
