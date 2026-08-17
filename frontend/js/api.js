/**
 * BookRate API Client Module
 * Provides unified interfaces for REST endpoints and POST SSE streams.
 */

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
