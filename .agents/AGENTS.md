# BookRate - AI Agent Workspace Guide

This guide describes the project's wizard-style flow, core terminology, data structures, and code mapping to help AI agents understand the codebase instantly and maintain consistency.

---

## 1. Wizard Steps (Step 1, Step 2, Step 3)

The user interface follows a 3-step wizard workflow designed to search, review, and aggregate ratings.

```mermaid
graph TD
    Step1[Step 1: Search] -->|User inputs query| API_Search[/api/search]
    API_Search -->|Returns candidate Works| Step2[Step 2: Selection & Metadata Editor]
    Step2 -->|User reviews/edits metadata lists| Step3[Step 3: Compare & Aggregation]
    Step3 -->|SSE stream request| API_Stream[/api/work-details-stream]
    API_Stream -->|Parallel fetchers| Sources[(8 Platforms)]
    Sources -->|Streamed updates| Table[Comparison Table]
```

### Step 1: Search
* **User action**: Types a search query (book title, author, or ISBN) in the search bar.
* **Backend flow**: Frontend queries `/api/search` with active engines. The backend concurrently searches Open Library and Google Books, falling back to other platforms only if both are disabled.
* **Output**: Renders a list of candidate book cards representing abstract creative **Works**.

### Step 2: Selection & Metadata Editor
* **User action**: Clicks on a candidate book card from Step 1.
* **Data resolution**:
  1. Frontend fetches all published editions of the selected Work (via Open Library `/api/work-editions` or via the `init` SSE event of `/api/work-details-stream`).
  2. The frontend extracts specific **Book Metadata** lists (alternative English titles, Asian/Chinese titles, author list, ISBNs) from all editions of the work.
* **Interface**: Displays a **Metadata Editor Card** in the right-hand panel. The user can review, add, edit, or remove items from these metadata lists before submitting.

### Step 3: Compare & Aggregation
* **User action**: Clicks "Compare" (or triggers search from the Metadata Editor Card).
* **Backend flow**: Frontend serializes the reviewed metadata lists and requests the SSE stream endpoint `/api/work-details-stream` (or `/api/work-details`).
* **Processing**: The backend queries the 8 active rating sources concurrently under a ThreadPoolExecutor. Each source evaluates the user's selected **Search Strategy** (specified in the column header dropdowns of the comparison table) to find the best matching book on that platform.
* **Output**: Renders a side-by-side comparison table showing ratings, review counts, matching links, and search queries for each platform.

---

## 2. Terminology: Title Provider vs. Rate Provider

The codebase distinguishes between engines used for finding *candidate books* and engines used for retrieving *ratings*.

* **Title Provider (or Title Source)**:
  * Used in **Step 1** to locate and map search queries to candidate books (`Work` objects).
  * Main title providers: Open Library (`open_library`) and Google Books (`google_books`).
  * Fallbacks: If Open Library and Google Books are inactive, the backend queries the first active platform in the priority list `TITLE_SOURCES = ["goodreads", "storygraph", "amazon", "amazon_jp", "douban", "readmoo"]`.
* **Rate Provider (or Rating Source/Engine)**:
  * Used in **Step 3** to fetch score ratings and review counts for a specific work.
  * Supported platforms (8 total): Open Library, Google Books, Goodreads, Douban, Amazon, Amazon JP, StoryGraph, and Readmoo.
  * All rate providers implement the `BaseSource` class and support multiple search strategies to query rating endpoints.

---

## 3. Book Metadata Structure

"Book Metadata" refers to the compiled metadata collections of an abstract `Work` generated from its list of published `Edition` records. These lists are reviewed and edited in **Step 2** and sent to the backend in **Step 3**:

* `search_name` (string): The initial search query entered in Step 1.
* `title_list` (list of strings): Alternative main/English titles (e.g. `["The Lord of the Rings", "LotR"]`).
* `title_zh_list` (list of strings): Alternative CJK/Asian/Chinese titles (e.g. `["魔戒", "指环王"]`).
* `author_list` (list of strings): Author names to combine with title queries.
* `isbn_list` (list of strings): List of all unique ISBN-10 or ISBN-13 strings collected from editions.

---

## 4. Search Strategies

In Step 3, rate providers fetch ratings using one of 6 single-factor search strategies. The strategy is configured per-provider in the comparison table headers:

1. `search_name`: Searches the platform exactly using the user's original query.
2. `title_list` (Short-circuit): Sequentially tries titles in `title_list`, short-circuiting on the first result that returns ratings.
3. `title_zh_list` (Short-circuit): Sequentially tries Asian/Chinese titles in `title_zh_list`, short-circuiting on the first rating result.
4. `title_list_full` (Full List): Queries all titles in `title_list`, displaying all matched results in a vertical list inside the cell (1-second delay between queries).
5. `title_zh_list_full` (Full List): Queries all titles in `title_zh_list`, displaying all matched results in a vertical list inside the cell (1-second delay).
6. `isbn` (Short-circuit): Sequentially tries clean ISBNs in `isbn_list`, short-circuiting on the first result.
7. `source_id`: Direct identifier lookup (e.g., Goodreads ID, Google Books volume ID, Douban subject ID) if known.
8. `title_author` (Default fallback): Combines the main title with the first author's name.

---

## 5. Codebase Mapping

### Backend (Python + FastAPI)
* **[server.py](../server.py)**: The entry point. Hosts API endpoints (`/api/search`, `/api/work-details`, `/api/work-details-stream`, `/api/work-editions`).
* **[book_rate/models.py](../book_rate/models.py)**: Dataclasses for `Work`, `Edition`, and `SourceRating`.
* **[book_rate/aggregator.py](../book_rate/aggregator.py)**: Instantiates and groups rating sources.
* **[book_rate/sources/base.py](../book_rate/sources/base.py)**: The `BaseSource` class implementing the execution of `SearchStrategy` and fallback query matching logic.
* **[book_rate/sources/](../book_rate/sources/)**: Individual crawler and API fetcher modules for each platform (e.g., `douban.py`, `goodreads.py`, `google_books.py`, `open_library.py`).

### Frontend (Pure JavaScript / CSS / HTML)
* **[frontend/index.html](../frontend/index.html)**: Main UI layout, containing search inputs, wizard steps panels, and the ratings comparison table.
* **[frontend/app.js](../frontend/app.js)**: Orchestrates wizard state transitions and handles server-sent events (SSE) parsing.
* **[frontend/js/wizard.js](../frontend/js/wizard.js)**: Renders step sections and wizard step progression.
* **[frontend/js/candidates.js](../frontend/js/candidates.js)**: Handles rendering search results and metadata card editing fields for Step 2.
* **[frontend/js/ratings.js](../frontend/js/ratings.js)**: Renders comparison table rows, dropdowns, and rating details.
* **[frontend/js/constants.js](../frontend/js/constants.js)**: Configurations for search strategies, defaults, and API engine codes.
* **[frontend/js/cache.js](../frontend/js/cache.js)**: Manages localStorage caching for rating records.

