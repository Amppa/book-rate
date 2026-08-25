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

## 2. Wizard Steps (Step 1, Step 2, Step 3)

The user interface follows a 3-step wizard workflow designed to search, review, and aggregate ratings.

```mermaid
graph TD
    Step1[Step 1: Search] -->|User inputs query| API_Search[/api/search]
    API_Search -->|Returns candidate Works| Step2[Step 2: Selection & Metadata Editor]
    Step2 -->|User reviews/edits metadata lists| Step3[Step 3: Compare & Aggregation]
    Step3 -->|SSE stream request| API_Stream[/api/work-details-stream]
    API_Stream -->|Parallel fetchers| Sources[(10 UI Platforms)]
    Sources -->|Streamed updates| Table[Comparison Table]
```

### Step 1: Search
* **User action**: Types a search query (book title, author, or ISBN) in the search bar.
* **Backend flow**: Frontend queries `/api/search` with active engines. The backend concurrently searches Open Library and Google Books, falling back to other platforms only if both are disabled.
* **Output**: Renders a list of candidate book cards representing abstract creative **Works**.

### Step 2: Selection & Metadata Editor
* **User action**: Clicks on a candidate book card from Step 1, or expands a card to view/select published editions.
* **On-Demand Edition Expansion (`enable_extend_editions`)**:
  - Supported platforms: **Open Library**, **Goodreads**, **Douban (豆瓣)**, and **StoryGraph**.
  - Clicking on a candidate card sends a lazy-loaded request to `/api/work-editions?work_id=...` to fetch published editions on-demand without slowing down the initial search.
* **Data resolution**:
  1. Frontend fetches published editions of the selected Work.
  2. The frontend extracts specific **Book Metadata** lists (alternative English titles, Asian/Chinese titles, author list, ISBNs) from the editions.
* **Interface**: Displays a **Metadata Editor Card** in the right-hand panel. The user can review, add, edit, or remove items from these metadata lists before submitting.

### Step 3: Compare & Aggregation
* **User action**: Clicks "Compare" (or triggers search from the Metadata Editor Card).
* **Backend flow**: Frontend serializes the reviewed metadata lists and requests the SSE stream endpoint `/api/work-details-stream` (or `/api/work-details`) via POST payload.
* **Processing**: The backend queries the active rating sources concurrently under a `ThreadPoolExecutor`. Each source evaluates the user's selected **Search Strategy** (specified in the column header dropdowns of the comparison table) to find the best matching book on that platform.
* **Output**: Renders a side-by-side comparison table showing ratings, review counts, matching links, and search queries for each platform.

---

## 3. Terminology & Source Identifiers

### Platform Identifiers & Prefixes
* **Open Library**: `open_library` (`ol`)
* **Google Books**: `google_books` (`gb`)
* **Google Play**: `google_play` (`gp` / `gp:`)
* **Goodreads**: `goodreads` (`gr` / `gr:`)
* **StoryGraph**: `storygraph` (`sg` / `sg:`)
* **Amazon US**: `amazon` (`am` / `am:`)
* **Amazon JP**: `amazon_jp` (`amjp` / `amjp:`)
* **Douban (豆瓣)**: `douban` (`db` / `db:`)
* **Douban API (豆瓣 API)**: `douban_api` (`dbapi` / `dbapi:`)
* **Readmoo (讀墨)**: `readmoo` (`rm` / `rm:`)
* **Books.com.tw (博客來)**: `books_tw` (`bk` / `bk:`)

### Title Provider vs. Rate Provider
* **Title Provider (or Title Source)**:
  * Used in **Step 1 (Multi-edition search)** to locate candidate books (`Work` objects) for the active tab (e.g. `open_library`, `goodreads`, `douban`, `storygraph`).
* **Rate Provider (or Rating Source/Engine)**:
  * Used in **Step 3 (Quick search & Compare)** to fetch score ratings and review counts for a specific work.
  * Supported platforms: 10 UI platforms & 11 adapters implementing the `BaseSource` class.

---

## 4. Book Metadata Structure

"Book Metadata" refers to the compiled metadata collections of an abstract `Work` generated from its list of published `Edition` records. These lists are reviewed and edited in **Step 2** and sent to the backend in **Step 3**:

* `search_name` (string): The initial search query entered in Step 1.
* `title_list` (list of strings): Alternative main/English titles (e.g. `["The Lord of the Rings", "LotR"]`).
* `title_zh_list` (list of strings): Alternative CJK/Asian/Chinese titles (e.g. `["魔戒", "指环王"]`).
* `author_list` (list of strings): Author names to combine with title queries.
* `isbn_list` (list of strings): List of all unique ISBN-10 or ISBN-13 strings collected from editions.

### Single-Book Detail Metadata (`to_book_info`)
In Step 3, each provider enriches the matched book with detailed metadata rendered in a collapsible `<details>` panel:
* Standard fields: `author`, `translator`, `publisher`, `publish_date`, `series`, `language`, `original_title`, `edition_count`, `isbn`, `asin`, `work_id`.
* Truncation: Values exceeding 50 characters are automatically truncated (`...`) with a hover tooltip.

---

## 5. Search Strategies

In Step 3, rate providers fetch ratings using one of 6 single-factor search strategies (configured per-provider in the comparison table headers):

1. `search_name`: Searches the platform exactly using the user's original query.
2. `title_list` (Short-circuit): Sequentially tries titles in `title_list`, short-circuiting on the first result that returns ratings.
3. `title_zh_list` (Short-circuit): Sequentially tries Asian/Chinese titles in `title_zh_list`, short-circuiting on the first rating result.
4. `title_list_full` (Full List): Queries all titles in `title_list`, displaying all matched results in a vertical list inside the cell (1-second delay between queries).
5. `title_zh_list_full` (Full List): Queries all titles in `title_zh_list`, displaying all matched results in a vertical list inside the cell (1-second delay).
6. `isbn` (Short-circuit): Sequentially tries clean ISBNs in `isbn_list`, short-circuiting on the first result.
7. `source_id`: Direct identifier lookup (e.g., Goodreads ID, Google Books volume ID, Douban subject ID, StoryGraph UUID) if known.
8. `title_author` (Default fallback): Combines the main title with the first author's name.

---

## 6. Key Mechanisms & Event Handling

### Rating Cache Flow
* In `selectWork()`, the frontend checks the rating cache (`localStorage` `bookrate:rating:...`) for all active engines.
* Cached ratings are rendered **immediately**. Only pending (non-cached) engines are passed to the POST stream payload request.
* Since Open Library ratings are received during the `init` event rather than subsequent `platform` events, its cache is written during the `init` handler in `updateWorkDetailRow()`.

### Strategy Dropdowns Delegation
* `strategy-select` dropdowns are rendered inside the table `<thead>` elements.
* A global `change` listener is bound to `document` to handle both settings checkboxes and header select inputs.

### Anti-Bot & Fingerprint Bypassing
* `BaseSource._fetch_html` uses `requests.Session` with browser headers and automatically falls back to Windows `curl.exe` subprocess calls to bypass strict Cloudflare/WAF TLS fingerprinting.
* Domain rate limiting (`DomainRateLimiter`) applies configurable cooldowns (e.g. 1.0s for Douban, Amazon, Amazon JP, Books.com.tw) to prevent rate limits.

---

## 7. Test Architecture

* **Mock Unit Tests (`pytest`)**:
  - Live-network tests carry the `live` marker. Default `pytest` runs the offline tier only; run `pytest -m live` for real HTTP integration tests.
  - Mock tests are guaranteed offline: `tests/conftest.py` blocks sockets and subprocesses unless a test is marked `live`.
  - Active test suite:
    - **`tests/test_all_sources.py`**: Unit tests for all 11 source adapters, compact number parsing (`_parse_compact_number`), and edge cases.
    - **`tests/test_models.py`**: Model dataclasses.
    - **`tests/test_resolver.py`**: ID prefixes and work resolvers.
    - **`tests/test_aggregator.py`**: Aggregator coordination.
    - **`tests/test_server.py`**: FastAPI routes & SSE streaming.
    - **`tests/test_concurrency.py`**: Concurrency and curl isolation.
    - **`tests/test_cooldown_and_headers.py`**: Domain rate limiting and cooldowns.
    - **`tests/test_text_parser.py`**: Clean text, author cleaning, and schema parsers.
    - **`tests/test_metadata_contract.py`**: Metadata contract models, merging, and first available fetchers.
* **Live Network Tests**:
  - **`tests/live_test_network.py`**: Real HTTP request integration tests. Run via `pytest -m live`.

---

## 8. Codebase Mapping

### Backend (Python + FastAPI)
* **[server.py](../server.py)**: Hosts API endpoints (`GET /api/search`, `GET /api/work-editions`, `POST /api/work-details`, `POST /api/work-details-stream`, `GET /api/source-status`).
* **[book_rate/models.py](../book_rate/models.py)**: Dataclasses for `Work`, `Edition`, `SourceRating`, `SourceStatus`, and `RatingRequestPayload`.
* **[book_rate/aggregator.py](../book_rate/aggregator.py)**: Main coordinator instantiating adapters and providing query interfaces.
* **[book_rate/orchestrator.py](../book_rate/orchestrator.py)**: Orchestrates concurrent rating execution and SSE streaming events.
* **[book_rate/resolver.py](../book_rate/resolver.py)**: Implements `WorkResolver` and `EditionResolver`.
* **[book_rate/registry.py](../book_rate/registry.py)**: Central registry discovering and instantiating 11 source adapters.
* **[book_rate/work_preparer.py](../book_rate/work_preparer.py)**: Candidate work creation and edition resolution.
* **[book_rate/sources/base.py](../book_rate/sources/base.py)**: The `BaseSource` class implementing the execution of `SearchStrategy` and fallback query matching logic.
* **[book_rate/sources/](../book_rate/sources/)**: Individual crawler and API fetcher modules (`amazon.py`, `books_tw.py`, `douban.py`, `goodreads.py`, `google_books.py`, `google_play.py`, `open_library.py`, `readmoo.py`, `storygraph.py`).

### Frontend (Pure JavaScript / CSS / HTML)
* **[frontend/index.html](../frontend/index.html)**: Main UI layout, search inputs, wizard panels, modals, and ratings comparison table.
* **[frontend/app.js](../frontend/app.js)**: Orchestrates wizard state transitions and handles server-sent events (SSE) parsing.
* **[frontend/js/wizard.js](../frontend/js/wizard.js)**: Renders step sections and wizard step progression.
* **[frontend/js/candidates.js](../frontend/js/candidates.js)**: Handles rendering search results and metadata card editing fields for Step 2.
* **[frontend/js/ratings.js](../frontend/js/ratings.js)**: Renders comparison table rows, dropdowns, and rating details.
* **[frontend/js/rating-renderer.js](../frontend/js/rating-renderer.js)**: Centralizes rating score display resolution, status badges, and cell rendering.
* **[frontend/js/result-details.js](../frontend/js/result-details.js)**: Renders collapsible metadata panel (`<details>`), ASIN, field labels, and global toggle button.
* **[frontend/js/constants.js](../frontend/js/constants.js)**: Configurations for search strategies, defaults, and API engine codes.
* **[frontend/js/cache.js](../frontend/js/cache.js)**: Manages localStorage caching for rating records and source connectivity status.
* **[frontend/js/api.js](../frontend/js/api.js)**: Client HTTP/SSE network handler functions.
* **[frontend/js/ui.js](../frontend/js/ui.js)**: Header controls, strategy dropdowns, source connectivity badges.
* **[frontend/js/modals.js](../frontend/js/modals.js)**: Dynamic modal manager for editions and raw response payloads.
* **[frontend/js/history.js](../frontend/js/history.js)**: Client search history manager.
