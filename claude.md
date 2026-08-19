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

### Acronyms & Identifiers of Rating Providers:
- Open Library: `open_library` (`ol`)
- Google Books: `google_books` (`gb`)
- Google Play: `google_play` (`gp`)
- Goodreads: `goodreads` (`gr`)
- Amazon: `amazon` (`am`)
- Amazon JP: `amazon_jp` (`amjp`)
- Douban: `douban` (`db`)
- Douban API: `douban_api` (`dbapi`) (hidden in frontend UI but active as fallback title source)
- StoryGraph: `storygraph` (`sg`)
- Readmoo: `readmoo` (`rm`)
- Books.com.tw (博客來): `books_tw` (`bk`)

---

## 2. System Architecture

### Backend (Python + FastAPI)
Defined in [server.py](server.py):
- **`GET /api/search`**: Concurrently searches books on selected providers and merges results.
- **`GET /api/work-editions`**: Fetches all published editions for a target book.
- **`POST /api/work-details`**: Synchronously retrieves and aggregates ratings for a work using a JSON payload.
- **`POST /api/work-details-stream`**: An SSE endpoint that accepts a JSON payload, yields an `init` event (containing edition list and Open Library ratings), concurrently queries active providers, and yields individual `source` event updates.
- **`GET /api/source-status`**: Concurrently checks the real-time connectivity and health status of selected rating providers.

- **Modular Core Component Blocks**:
  - **[work_preparer.py](book_rate/work_preparer.py)**:
    - `WorkPreparer`: Assembles candidate `Work` objects and resolves published `Edition` records.
  - **[resolver.py](book_rate/resolver.py)**:
    - `WorkResolver`: Handles candidate work discovery across active title sources.
    - `EditionResolver`: Resolves target book edition lists from work IDs using prefix matching (e.g. `gr:`, `gb:`, `play:`, `db:`, `bk:`).
  - **[orchestrator.py](book_rate/orchestrator.py)**:
    - `RatingOrchestrator`: Coordinates concurrent rating queries under a `ThreadPoolExecutor` and prepares/yields SSE responses.
  - **[registry.py](book_rate/registry.py)**:
    - `SourceRegistry`: Registry containing all 11 adapters and their respective title query priority.
- **Sources Core**: Platform scrapers and API fetchers are implemented in [book_rate/sources/](book_rate/sources/):
  - **[base.py](book_rate/sources/base.py)**: Implements `BaseSource`, providing a shared HTTP fetcher that executes `curl.exe` to bypass Cloudflare TLS fingerprinting checks on Windows. Also manages query matching across 6 strategies:
    1. `search_name`: Pure keyword search from Step 1, with no author combined.
    2. `title_list`: Sequential search of English/main titles (short-circuit).
    3. `title_zh_list`: Sequential search of Asian/Chinese titles (short-circuit).
    4. `title_list_full`: Full sequential search of English/main titles with 1s delay.
    5. `title_zh_list_full`: Full sequential search of Asian/Chinese titles with 1s delay.
    6. `isbn`: Sequential search of clean ISBNs (short-circuit).
  - **Adapters**: `amazon.py`, `books_tw.py`, `douban.py`, `goodreads.py`, `google_books.py`, `google_play.py`, `open_library.py`, `readmoo.py`, `storygraph.py`.
  - **[models.py](book_rate/models.py)**:
    - `Work`: Holds metadata lists (`search_name`, `title_list`, `title_zh_list`, `author_list`, `isbn_list`).
    - `SourceRating`: Represents standard rating records (includes a `results` list for full strategies).
    - `RatingRequestPayload`: The Pydantic model representing POST query details.
    - `SourceStatus`: Enum tracking operational search states (`SUCCESS`, `NOT_FOUND`, `ERROR`, `TIMEOUT`).

### Frontend (Pure JavaScript / ES Modules)
Located in `frontend/`:
- **[app.js](frontend/app.js)**: Entry point. Manages wizard steps, binds events, and parses SSE data streams.
- **[js/api.js](frontend/js/api.js)**: API Client module containing `fetchSearchWorks`, `fetchWorkEditions`, `streamWorkDetailsPost`, and `fetchSourceStatus`.
- **[js/constants.js](frontend/js/constants.js)**: Holds configuration constants, 6 search strategies list, and 11 sources configuration mappings.
- **[js/cache.js](frontend/js/cache.js)**: LocalStorage caching for ratings (`bookrate:rating:...`) and source status (`bookrate:source-status`).
- **[js/ui.js](frontend/js/ui.js)**: Header controls, settings, source connectivity status indicators, dynamically building top checkboxes and table header strategy dropdowns.
- **[js/ratings.js](frontend/js/ratings.js)**: Rating comparison table cell and tooltip rendering logic.
- **[js/candidates.js](frontend/js/candidates.js)**: Step 2 metadata card rendering and candidate card interaction.
- **[js/wizard.js](frontend/js/wizard.js)**: Wizard step rendering and state transitions.
- **[js/modals.js](frontend/js/modals.js)**: Modal windows (e.g. edition lists, raw response inspection).
- **[js/history.js](frontend/js/history.js)**: Search history persistence and UI chips.

---

## 3. Key Mechanisms & Event Handling

### Rating Cache Flow
- In `selectWork()`, the frontend checks the rating cache for all active engines.
- Cached ratings are rendered **immediately**. Only pending (non-cached) engines are passed to the POST stream payload request.
- Since Open Library ratings are received during the `init` event rather than subsequent `platform` events, its cache is written during the `init` handler in `updateWorkDetailRow()`.

### Strategy Dropdowns Delegation
- `strategy-select` dropdowns are rendered inside the table `<thead>` elements.
- A global `change` listener is bound to `document` to handle both settings checkboxes and header select inputs.


