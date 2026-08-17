# BookRate Project Guide

This doc helps AI assistants (Claude, Gemini, GPT) quickly grasp the codebase architecture, data flows, and specific design patterns of the BookRate project.

---

## 1. Project Overview & Core Workflow
BookRate is a multi-platform book rating aggregator. 
Users search by book title, author, or ISBN.
The system concurrently queries multiple platforms (Open Library, Google Books, Google Play Books, Goodreads, Douban, Amazon, Amazon JP, StoryGraph, Readmoo, Books.com.tw) to display an aggregated rating table.

### Step-by-Step Flow:
1. **Step 1 (Search)**: Input book title or ISBN. Query list of candidate books via `/api/search`.
2. **Step 2 (Select)**: Users can toggle databases to search. Displays a candidate list of cards. The right-hand panel displays a metadata editor card.
3. **Step 3 (Compare)**: Collecting book metadata from Open Library (or current active source). 
Fetch ratings from platforms/providers using 6 distinct single-factor search strategies.

### Acronym of Rating Providers:
- Open Library: OL
- Google Books: GB
- Google Play: GP
- Goodreads: GR
- Amazon: AM
- Amazon JP: AM_JP
- Douban: DB
- Douban API: DBAPI (hidden in frontend UI but active as a fallback title source)
- StoryGraph: SG
- Readmoo: RM
- Books.com.tw (博客來): BK

---

## 2. System Architecture

### Backend (Python + FastAPI)
Defined in [server.py](file:///c:/Users/flow/Documents/我的git/book-rate/server.py):
- **`/api/search`**: Concurrently searches books on selected providers and merges results.
- **`/api/work-editions`**: Fetches all published editions for a target book.
- **POST `/api/work-details`**: Synchronously retrieves and aggregates ratings for a work using a JSON payload.
- **POST `/api/work-details-stream`**: An SSE endpoint that accepts a JSON payload, yields an `init` event (containing edition list and Open Library ratings), concurrently queries active providers, and yields individual `source` event updates.

- **Modular Core Component Blocks**:
  - **[resolver.py](file:///c:/Users/flow/Documents/我的git/book-rate/book_rate/resolver.py)**:
    - [WorkResolver](file:///c:/Users/flow/Documents/我的git/book-rate/book_rate/resolver.py#L10): Handles candidate work discovery across active title sources.
    - [EditionResolver](file:///c:/Users/flow/Documents/我的git/book-rate/book_rate/resolver.py#L73): Resolves target book edition lists from work IDs using prefix matching (e.g. `gr:`, `gb:`, `play:`, `db:`, `bk:`).
  - **[orchestrator.py](file:///c:/Users/flow/Documents/我的git/book-rate/book_rate/orchestrator.py)**:
    - [RatingOrchestrator](file:///c:/Users/flow/Documents/我的git/book-rate/book_rate/orchestrator.py#L13): Coordinates concurrent rating queries under a `ThreadPoolExecutor` and prepares/yields responses.
  - **[registry.py](file:///c:/Users/flow/Documents/我的git/book-rate/book_rate/registry.py)**:
    - [SourceRegistry](file:///c:/Users/flow/Documents/我的git/book-rate/book_rate/registry.py#L19): Registry containing all 11 adapters and their respective title query priority.
- **Sources Core**: Platform scrapers and API fetchers are implemented in [book_rate/sources/](file:///c:/Users/flow/Documents/我的git/book-rate/book_rate/sources/):
  - **[base.py](file:///c:/Users/flow/Documents/我的git/book-rate/book_rate/sources/base.py)**: Implements [BaseSource](file:///c:/Users/flow/Documents/我的git/book-rate/book_rate/sources/base.py#L29), providing a shared HTTP fetcher that executes `curl.exe` to bypass Cloudflare TLS fingerprinting checks on Windows. Also manages query matching across 6 strategies:
    1. `search_name`: Pure keyword search from Step 1, with no author combined.
    2. `title_list`: Sequential search of English/main titles (short-circuit).
    3. `title_zh_list`: Sequential search of Asian/Chinese titles (short-circuit).
    4. `title_list_full`: Full sequential search of English/main titles with 1s delay.
    5. `title_zh_list_full`: Full sequential search of Asian/Chinese titles with 1s delay.
    6. `isbn`: Sequential search of clean ISBNs (short-circuit).
  - **[models.py](file:///c:/Users/flow/Documents/我的git/book-rate/book_rate/models.py)**:
    - [Work](file:///c:/Users/flow/Documents/我的git/book-rate/book_rate/models.py#L71): Holds metadata lists (`search_name`, `title_list`, `title_zh_list`, `author_list`, `isbn_list`).
    - [SourceRating](file:///c:/Users/flow/Documents/我的git/book-rate/book_rate/models.py#L34): Represents standard rating records (includes a `results` list for full strategies).
    - [RatingRequestPayload](file:///c:/Users/flow/Documents/我的git/book-rate/book_rate/models.py#L18): The Pydantic model representing POST query details.
    - [SourceStatus](file:///c:/Users/flow/Documents/我的git/book-rate/book_rate/models.py#L7): Enum tracking operational search states.

### Frontend (Pure JavaScript / ES Modules)
Located in `frontend/`:
- **[app.js](file:///c:/Users/flow/Documents/我的git/book-rate/frontend/app.js)**: Entry point. Manages wizard steps, binds events, and parses SSE data streams.
- **[js/api.js](file:///c:/Users/flow/Documents/我的git/book-rate/frontend/js/api.js)**: API Client module containing `fetchSearchWorks`, `fetchWorkEditions`, and `streamWorkDetailsPost` (which implements POST SSE reading chunks via readers and text decoders).
- **[js/constants.js](file:///c:/Users/flow/Documents/我的git/book-rate/frontend/js/constants.js)**: Holds configuration constants, 6 search strategies list, and 11 sources configuration mappings.
- **[js/cache.js](file:///c:/Users/flow/Documents/我的git/book-rate/frontend/js/cache.js)**: LocalStorage caching.
  - *Rating Cache*: format `bookrate:rating:{work_key}:{provider}:{strategy}`.
- **[js/ui.js](file:///c:/Users/flow/Documents/我的git/book-rate/frontend/js/ui.js)**: Modal toggling and dynamically building top checkboxes and table header strategy dropdowns. Excludes `douban_api` from checkboxes/UI mapping.
- **[js/ratings.js](file:///c:/Users/flow/Documents/我的git/book-rate/frontend/js/ratings.js)**: Table cell and tooltip rendering logic. Excludes `douban_api` from the rating table cells.

---

## 3. Key Mechanisms & Event Handling

### Rating Cache Flow
- In `selectWork()`, the frontend checks the rating cache for all active engines.
- Cached ratings are rendered **immediately**. Only pending (non-cached) engines are passed to the POST stream payload request.
- Since Open Library ratings are received during the `init` event rather than subsequent `platform` events, its cache is written during the `init` handler in `updateWorkDetailRow()`.

### Strategy Dropdowns Delegation
- `strategy-select` dropdowns are rendered inside the table `<thead>` elements.
- A global `change` listener is bound to `document` to handle both settings checkboxes and header select inputs.

