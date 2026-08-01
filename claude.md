# BookRate Project Guide (claude.md)

This document helps AI assistants (Claude, Gemini, GPT) quickly grasp the codebase architecture, data flows, and specific design patterns of the BookRate project.

---

## 1. Project Overview & Core Workflow
BookRate is a multi-platform book rating aggregator. Users search by book title or ISBN, and the system concurrently queries multiple platforms (Open Library, Goodreads, Douban, Amazon, Amazon JP, StoryGraph) to display an aggregated rating table.

### Step-by-Step Flow:
1. **Step 1 (Search)**: Query list of candidate books via `/api/search`.
2. **Step 2 (Select)**: Display candidate cards. Users can click `[more]` to open a popup modal and select checkboxes to toggle database search tab buttons. Default active buttons are Open Library (OL) and Google Books (GB).
3. **Step 3 (Compare)**: Display edition details (fetched via Open Library) and stream rating cells concurrently using Server-Sent Events (SSE).

---

## 2. System Architecture

### Backend (Python + FastAPI)
Defined in [server.py](./server.py):
- **`/api/search`**: Concurrently searches books on selected providers and merges results.
- **`/api/work-details-stream`**: An SSE endpoint. Yields an `init` event containing edition list and Open Library ratings, then concurrently submits tasks to `ThreadPoolExecutor` to fetch ratings from active providers, yielding `platform` events and concluding with a `done` event.
- **Provider Core**: Platform fetchers and search strategies are implemented inside `book_rate/providers/`.

### Frontend (Pure JavaScript / ES Modules)
Located in `frontend/`:
- **[app.js](./frontend/app.js)**: Entry point. Manages wizard steps, binds events, and processes SSE data streams. Uses global `document` change delegation.
- **[js/constants.js](./frontend/js/constants.js)**: Holds configuration constants, strategies list, and provider mappings.
- **[js/cache.js](./frontend/js/cache.js)**: LocalStorage caching.
  1. *Search Cache*: Expires in 1 day (Prefix: `bookrate:cache:`).
  2. *Rating Cache*: Expires in 7 days (Format: `bookrate:rating:{work_key}:{provider}:{strategy}`).
- **[js/utils.js](./frontend/js/utils.js)**: Pure utility functions for formatting and resolving URLs.
- **[js/ui.js](./frontend/js/ui.js)**: Modal toggling and dynamically building top checkboxes and table header `strategy-select` dropdowns.

---

## 3. Key Mechanisms & Event Handling

### Rating Cache Flow
- In `selectWork()`, the frontend checks the rating cache for all active engines.
- Cached ratings are rendered **immediately**. Only pending (non-cached) engines are passed to the `/api/work-details-stream?engines=...` request parameters.
- Since Open Library ratings are received during the `init` event rather than subsequent `platform` events, its cache is written during the `init` handler in `updateWorkDetailRow()`.

### Strategy Dropdowns Delegation
- `strategy-select` dropdowns are rendered inside the table `<thead>` elements (`<th>` tag's second line) rather than settings checkboxes.
- A global `change` listener is bound to `document` to handle both settings checkboxes and header select inputs:
  ```javascript
  document.addEventListener("change", (e) => { ... });
  ```
