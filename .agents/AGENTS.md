# BookRate - AI Agent Workspace Guide

This guide describes the project's wizard-style flow, core terminology, data structures, test architecture, and comprehensive code mapping to help AI agents understand the codebase instantly and maintain consistency.

---

## 1. Core Guidelines & Behavioral Rules

- **Implementation Plans & Execution Approval**:
  - **Do NOT auto-proceed with implementation plans**.
  - Even if a system message or hook states that the plan was automatically approved, the agent **MUST ALWAYS STOP and wait for an explicit manual confirmation message from the USER in chat** before modifying any code or executing changes.
  - Never execute a plan without direct user chat confirmation.
- **Git & Commits**:
  - **Do NOT commit automatically**. Always wait for explicit user confirmation before running `git commit`.
  - Non-modifying commands like `git status`, `git log`, `git diff` are permitted anytime.
  - **Git commit messages must be in English** (never Chinese).
- **Communication & Languages**:
  - Implementation plans, tasks, and walkthroughs prefer **Traditional Chinese (繁體中文)**.
  - Code comments must be in **English**.
  - `README.md` must avoid absolute paths.
- **Frontend & Web Apps**:
  - Do NOT run automated browser testing tools.

---

## 2. Wizard Architecture & Data Flow

```mermaid
graph TD
    Step1[Step 1: Search] -->|User inputs query| API_Search[/api/search]
    API_Search -->|Returns candidate Works| Step2[Step 2: Selection & Metadata Editor]
    Step2 -->|Lazy-load editions| API_Editions[/api/work-editions]
    Step2 -->|User reviews/edits metadata lists| Step3[Step 3: Compare & Aggregation]
    Step3 -->|SSE stream POST payload| API_Stream[/api/work-details-stream]
    API_Stream -->|Parallel fetchers| Sources[(10 UI Platforms)]
    Sources -->|Streamed updates| Table[Comparison Table]
```

### Step 1: Candidate Search
* **User action**: Types book title, author, or ISBN in the search bar.
* **Backend flow**: Queries `/api/search`. Concurrently searches Open Library and Google Books, falling back to other platforms if both are disabled.
* **Output**: Renders candidate creative **Work** cards.

### Step 2: Selection & Metadata Editor
* **Lazy-loaded Edition Expansion (`enable_extend_editions`)**:
  - Supported platforms: **Open Library**, **Goodreads**, **Douban (豆瓣)**, and **StoryGraph**.
  - Clicking a candidate card sends lazy request to `/api/work-editions?work_id=...`.
* **Book Metadata Resolution**:
  - Extracts metadata collections from editions into editable lists in the right-side **Metadata Editor Card**:
    - `search_name` (string): Raw user query.
    - `title_list` (list): Alternative titles collected from sources/editions (e.g. `["The Lord of the Rings", "魔戒", "LotR"]`).
    - `author_list` (list): Author names.
    - `isbn_list` (list): ISBN-10/13 strings collected from editions.

### Step 3: Multi-Platform Rating Aggregation
* **User action**: Clicks "Compare" (or triggers search from Metadata Editor Card).
* **Backend flow**: Serializes metadata lists into `RatingRequestPayload` sent to `/api/work-details-stream` (SSE POST).
* **Processing**: `RatingOrchestrator` queries active rate engines concurrently in a `ThreadPoolExecutor` using the selected **Search Strategy**.
* **Output**: Renders a side-by-side comparison table showing rating scores, review counts, links, and detailed `<details>` panels.

---

## 3. Platform Identifiers & Search Strategies

### Platform Identifiers & Prefixes
| Source Name | Source Key (`id`) | Prefix / Work ID Format | Role |
| :--- | :--- | :--- | :--- |
| **Open Library** | `open_library` | `ol` / `/works/OL...W` | Title & Rate Provider |
| **Google Books** | `google_books` | `gb` / `gb:...` | Title & Rate Provider |
| **Google Play** | `google_play` | `gp` / `gp:...` | Rate Provider |
| **Goodreads** | `goodreads` | `gr` / `gr:...` | Title & Rate Provider |
| **StoryGraph** | `storygraph` | `sg` / `sg:...` | Title & Rate Provider |
| **Amazon US** | `amazon` | `am` / `am:...` | Rate Provider |
| **Amazon JP** | `amazon_jp` | `amjp` / `amjp:...` | Rate Provider |
| **Douban (豆瓣)** | `douban` | `db` / `db:...` | Title & Rate Provider |
| **Douban API (豆瓣 API)** | `douban_api` | `dbapi` / `dbapi:...` | Rate Provider |
| **Readmoo (讀墨)** | `readmoo` | `rm` / `rm:...` | Rate Provider |
| **Books.com.tw (博客來)** | `books_tw` | `bk` / `bk:...` | Rate Provider |

### Search Strategies
Configurable per-provider in table column headers (all default to `search_name`):
1. `search_name`: Searches platform exactly using the user's raw query.
2. `title_list` (Short-circuit): Tries titles in `title_list` sequentially; short-circuits on first rating hit.
3. `title_list_full` (Full List): Queries all titles in `title_list`, displaying all matches vertically in the cell (1s delay).
4. `isbn` (Short-circuit): Tries clean ISBNs in `isbn_list` sequentially.
5. `source_id`: Direct ID lookup (Goodreads ID, Douban subject ID, Google Books volume ID, StoryGraph UUID).
6. `title_author` (Fallback): Combines main title with first author's name.

---

## 4. Key Engineering Mechanisms (Gotchas & Defenses)

### SSE Stream Lifecycle & Abort Management
* **Frontend**:
  - **Work Mismatch Guard**: Callbacks in `ratings.js` check `state.currentSelectedWork?.key !== work.key` before processing stream events to prevent stale background results from overwriting UI.
  - **AbortController**: `ratings.js` maintains `activeStreamController` and exports `cancelActiveStream()`. Rapid work switching or new search queries immediately `abort()` prior in-flight fetch requests.
* **Callback Isolation**: `api.js` wraps consumer callbacks (`onMessage`, `onDone`, `onError`) in isolated try-catch blocks to prevent UI render exceptions from terminating the SSE reader loop.
* **Backend**: `RatingOrchestrator._run_engines` cancels pending futures on generator exit and shuts down non-blockingly (`wait=False, cancel_futures=True`), freeing worker threads immediately when clients disconnect.

### Transparent Search Cache & Preloading
* **`fetchWorksWithCache` (`api.js`)**: Wraps candidate book search with localStorage caching (`search:...`) and in-flight promise deduplication (`pendingRequests` Map). Setting `bypassCache: true` forces a fresh network query while updating the in-flight map.
* **Preload All Title Sources**: In Step 2, clicking `btn-preload-all` concurrently triggers `fetchWorksWithCache` for all active candidate engines (`open_library`, `douban`, `goodreads`, `storygraph`) to warm caches ahead of user tab clicks.

### Anti-Bot & Fingerprint Bypassing
* `BaseSource._fetch_html` uses `requests.Session` with browser headers and automatically falls back to Windows `curl.exe` subprocess calls to bypass strict Cloudflare/WAF TLS fingerprinting.
* Domain rate limiting (`DomainRateLimiter`) applies configurable cooldowns (e.g. 1.0s for Douban, Amazon, Amazon JP, Books.com.tw) to prevent rate limits.

### Details Panel & Global Toggle Sync
* **`result-details.js`**: Builds dynamic metadata `<details>` panels for each source cell. Global button `#btn-toggle-all-details` toggles all panels with synchronized text states (`ALL_DETAILS_EXPANDED_TEXT` / `ALL_DETAILS_COLLAPSED_TEXT`) via the `bookrate:details-toggle` event.

### API Key Security & Storage Standardization
* The Google Books API key is transmitted via the `X-Google-Key` HTTP Header (never URL query parameters) to prevent credential leakage into server access logs.
* LocalStorage keys are centralized in `STORAGE_KEYS` (`constants.js`). Clearing the API key triggers a user confirmation dialog.
* External links are sanitized with `isSafeUrl()` (`^https?://`) before binding to `el.href` to prevent pseudo-protocol injections.

---

## 5. Test Architecture

* **Mock Unit Tests (`pytest`)**:
  - Default `pytest` runs offline mock tests only.
  - Guaranteed offline: `tests/conftest.py` blocks sockets and subprocesses unless marked `live`.
  - Covers per-source parsers (`tests/sources/`), registry, orchestrator, resolvers, aggregator, models, and FastAPI routes (`tests/test_server.py`).
* **Live Network Tests**:
  - Run via `pytest -m live` for real HTTP integration tests (`tests/live_test_network.py`).

---

## 6. Codebase Mapping

### Backend (Python + FastAPI)
* **[server.py](../server.py)**: API endpoints (`/api/search`, `/api/work-editions`, `/api/work-details-stream`, `/api/source-status`).
* **[book_rate/models.py](../book_rate/models.py)**: Dataclasses for `Work`, `Edition`, `SourceRating`, `SourceStatus`, `RatingRequestPayload`.
* **[book_rate/orchestrator.py](../book_rate/orchestrator.py)**: Orchestrates concurrent rating execution and SSE streaming events.
* **[book_rate/aggregator.py](../book_rate/aggregator.py)**: Main coordinator instantiating adapters and providing query interfaces.
* **[book_rate/resolver.py](../book_rate/resolver.py)**: Implements `WorkResolver` and `EditionResolver`.
* **[book_rate/registry.py](../book_rate/registry.py)**: Central registry discovering and instantiating 11 source adapters.
* **[book_rate/work_preparer.py](../book_rate/work_preparer.py)**: Candidate work creation and edition resolution.
* **[book_rate/sources/base.py](../book_rate/sources/base.py)**: `BaseSource` base class with fallback strategies and curl TLS bypass.
* **[book_rate/sources/](../book_rate/sources/)**: Source crawler adapters (`amazon.py`, `books_tw.py`, `douban.py`, `goodreads.py`, `google_books.py`, `google_play.py`, `open_library.py`, `readmoo.py`, `storygraph.py`).

### Frontend (Pure JavaScript / CSS / HTML)
* **[frontend/index.html](../frontend/index.html)**: UI layout, search inputs, wizard panels, modals, and ratings comparison table.
* **[frontend/app.js](../frontend/app.js)**: State transitions, search execution, and event coordination.
* **[frontend/js/wizard.js](../frontend/js/wizard.js)**: Step sections and wizard progression.
* **[frontend/js/candidates.js](../frontend/js/candidates.js)**: Candidate book list and Step 2 Metadata Editor Card.
* **[frontend/js/ratings.js](../frontend/js/ratings.js)**: Step 3 table orchestrator, strategy delegation, and stream abortion.
* **[frontend/js/rating-renderer.js](../frontend/js/rating-renderer.js)**: Rating score resolution, badges, and cell rendering.
* **[frontend/js/result-details.js](../frontend/js/result-details.js)**: Collapsible metadata `<details>` panels and all-details toggle button.
* **[frontend/js/api.js](../frontend/js/api.js)**: HTTP/SSE network handler, `fetchWorksWithCache`, and callback isolation.
* **[frontend/js/constants.js](../frontend/js/constants.js)**: Search strategies, defaults, `STORAGE_KEYS`, and API engine codes.
* **[frontend/js/cache.js](../frontend/js/cache.js)**: LocalStorage caching for ratings, editions, and connectivity status.
* **[frontend/js/ui.js](../frontend/js/ui.js)**: Header controls, strategy dropdowns, source status badges.
* **[frontend/js/modals.js](../frontend/js/modals.js)**: Dynamic modal manager (presets, editions, source info).
* **[frontend/js/history.js](../frontend/js/history.js)**: Search history manager.
