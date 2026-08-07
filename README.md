# BookRate 📚

A Python tool and framework for searching books by title (including Chinese titles), discovering abstract **Works** and their specific language **Editions**, and aggregating ratings and review counts across multiple platforms (Open Library, Google Books).

---

## Key Features

- **Work & Edition Modeling**: Maps specific book editions (ISBNs, published languages, publishers) to abstract **Works** (Open Library `/works/OL...W` architecture).
- **Multi-Provider Aggregation**: Fetches and aggregates score ratings and rating counts across 8 different platforms: Open Library, Google Books, Goodreads, Douban, Amazon, Amazon JP, StoryGraph, and Readmoo.
- **Granular Search Strategy Configuration**: Allows selecting from 6 distinct search strategies for each platform in the comparison table:
  1. **User input title**: Search exactly by Step 1 query.
  2. **Book list title (Short-circuit)**: Sequentially tries English/main titles, stops on first match.
  3. **Asian book list title (Short-circuit)**: Sequentially tries CJK/Asian titles, stops on first match.
  4. **Book list title (Full)**: Queries all book titles, displaying all results in a vertical list inside the cell (1-second query delay).
  5. **Asian book list title (Full)**: Queries all Asian titles, displaying all results in a vertical list inside the cell (1-second query delay).
  6. **ISBN**: Sequentially tries cleaned ISBNs, stops on first match.
- **Wizard-Style Web UI**: Features a 3-step search, review (metadata editing card), and rating comparison flow.
- **Flexible CLI & Table Formatting**: Outputs formatted Markdown tables, colored terminal tables (powered by `rich`), CSV, or JSON exports.
- **Rating Cache Flow**: Locally caches fetched ratings based on work key, platform, and selected strategy to prevent duplicate queries and optimize page speed.

---

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-username/bookrate.git
   cd bookrate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

## Quick Start

### Running the Web Interface

Start the local FastAPI server hosting the web application:
```bash
python server.py
```
Then open your browser and navigate to `http://127.0.0.1:8000`.

#### Setting Google Books API Key

You can configure a Google Books API Key in two ways to avoid hitting rate limits:

**1. Directly on the Web UI (Stored in Browser)**
- Expand the **⚙️ Google Books API Key Settings** details panel at the top-right corner.
- Input your key and click **Save**. It will be saved locally in your browser's `localStorage` and sent with requests.

**2. Via Server-side Environment Variables**
- Set the API key before running `server.py`:
  ```bash
  # Windows (PowerShell)
  $env:GOOGLE_BOOKS_API_KEY="your_api_key"
  python server.py

  # macOS / Linux
  export GOOGLE_BOOKS_API_KEY="your_api_key"
  python server.py
  ```


### Basic CLI Search

Search for a book by title:
```bash
python main.py "快思慢想"
```

Output:
```markdown
| 書名 | 原作者 | work | Open Library 分數／人數 | Google Books 分數／人數 |
| --- | --- | --- | --- | --- |
| 快思慢想 | 丹尼爾·卡內曼 (Daniel Kahneman) | /works/OL27479W | 4.15 / 2200 reviews | 4.30 / 350 reviews |
```

### Detailed Edition Breakdown

Use `--editions` flag to display all cataloged editions for each work:
```bash
python main.py "Atomic Habits" --editions
```

### Output Formats

Export output to Markdown, JSON, or CSV:
```bash
python main.py "原子習慣" -f markdown
python main.py "原子習慣" -f json
python main.py "原子習慣" -f csv
```

### Passing Google Books API Key

To bypass default IP rate limits on Google Books API, provide an API key via environment variable or CLI argument:
```bash
export GOOGLE_BOOKS_API_KEY="your_api_key_here"
python main.py "快思慢想"
```
Or directly:
```bash
python main.py "快思慢想" --google-key "your_api_key_here"
```

---

## Project Architecture

```
bookrate/
├── book_rate/           # Core python package
│   ├── __init__.py
│   ├── models.py        # Dataclasses: Work, Edition, PlatformRating
│   ├── aggregator.py    # BookAggregator class combining provider data
│   ├── formatters.py    # Markdown, Rich Table, CSV, JSON formatters
│   └── providers/
│       ├── __init__.py
│       ├── base.py      # Abstract BaseProvider interface
│       ├── open_library.py # Open Library API provider
│       └── google_books.py # Google Books API provider
├── frontend/            # Web frontend files (HTML, CSS, JS)
├── tests/
│   └── test_aggregator.py # Unit tests
├── main.py              # CLI entry point
├── server.py            # FastAPI Web Server entry point
└── requirements.txt     # Python dependencies (requests, rich, fastapi, uvicorn)
```

---

## Running Tests

### Standard Fast Unit Tests (Offline, ~0.04s)

Run standard unit tests and edge cases (mocked HTTP requests):
```bash
python -m unittest discover tests
```

### Live Network Integration Tests (Optional, Real HTTP Requests)

To test live HTTP requests against actual external provider APIs (Open Library, Google Books, Goodreads, Douban, Amazon):
```bash
python -m unittest tests/live_test_network.py
```

---

## License

MIT License
