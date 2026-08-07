# BookRate Project Guide

This doc helps AI assistants (Claude, Gemini, GPT) quickly grasp the codebase architecture, data flows, and specific design patterns of the BookRate project.

---

## 1. Project Overview & Core Workflow
BookRate is a multi-platform book rating aggregator. 
Users search by book title or ISBN.
The system concurrently queries multiple platforms (Open Library, Google Books, Goodreads, Douban, Amazon, Amazon JP, StoryGraph, Readmoo) to display an aggregated rating table.

### Step-by-Step Flow:
1. **Step 1 (Search)**: Input book title or ISBN. Query list of candidate books via `/api/search`.
2. **Step 2 (Select)**: Users can toggle databases to search. Displays a candidate list of cards. The right-hand panel displays a metadata editor card.
3. **Step 3 (Compare)**: Collecting book metadata from Open Library. 
Fetch ratings from platforms/providers using 6 distinct single-factor search strategies.

### Acronym of Rating Providers:
- Open Library: OL
- Google Books: GB
- Goodreads: GR
- Amazon: AM
- Amazon JP: AM_JP
- Douban: DB
- StoryGraph: SG
- Readmoo: RM

---

## 2. System Architecture

### Backend (Python + FastAPI)
Defined in [server.py](./server.py):
- **`/api/search`**: Concurrently searches books on selected providers and merges results.
- **`/api/work-details-stream`**: An SSE endpoint. Yields an `init` event containing edition list and Open Library ratings, then concurrently submits tasks to `ThreadPoolExecutor` to fetch ratings from active providers, yielding `platform` events and concluding with a `done` event.
- **Provider Core**: Platform fetchers and search strategies are implemented inside `book_rate/providers/`.
  - **[base.py](./book_rate/providers/base.py)**: Implements `_fetch_ratings` which performs query matching for 6 different strategies:
    1. `search_name`: Pure keyword search from Step 1, with no author combined.
    2. `title_list`: Sequential search of English/main titles (short-circuit).
    3. `title_zh_list`: Sequential search of Asian/Chinese titles (short-circuit).
    4. `title_list_full`: Full sequential search of English/main titles with 1s delay (`time.sleep(1.0)`).
    5. `title_zh_list_full`: Full sequential search of Asian/Chinese titles with 1s delay (`time.sleep(1.0)`).
    6. `isbn`: Sequential search of clean ISBNs (short-circuit).
  - **[models.py](./book_rate/models.py)**: Extends `Work` with `search_name`, `title_list`, `title_zh_list`, `author_list`, `isbn_list` fields, and `PlatformRating` with `results` list to support full strategies.

### Frontend (Pure JavaScript / ES Modules)
Located in `frontend/`:
- **[app.js](./frontend/app.js)**: Entry point. Manages wizard steps, binds events, and processes SSE data streams. Parses step 3 metadata using `getStep3Metadata()`, serializes them as JSON query strings, and sends them to the backend details endpoint.
  - **Multi-Result Layout**: In `renderPlatformCell()`, if `data.results` is present, renders a compact list of results (`1.`, `2.`, `3.`, `4.`) with links and hovering tooltips displaying query terms.
- **[js/constants.js](./frontend/js/constants.js)**: Holds configuration constants, 6 search strategies list, and provider default strategy mappings.
- **[js/cache.js](./frontend/js/cache.js)**: LocalStorage caching.
  - *Rating Cache*: format `bookrate:rating:{work_key}:{provider}:{strategy}`.
- **[js/ui.js](./frontend/js/ui.js)**: Modal toggling and dynamically building top checkboxes and table header strategy dropdowns.

---

## 3. Key Mechanisms & Event Handling

### Rating Cache Flow
- In `selectWork()`, the frontend checks the rating cache for all active engines.
- Cached ratings are rendered **immediately**. Only pending (non-cached) engines are passed to the `/api/work-details-stream?engines=...` request parameters.
- Since Open Library ratings are received during the `init` event rather than subsequent `platform` events, its cache is written during the `init` handler in `updateWorkDetailRow()`.

### Strategy Dropdowns Delegation
- `strategy-select` dropdowns are rendered inside the table `<thead>` elements.
- A global `change` listener is bound to `document` to handle both settings checkboxes and header select inputs.
