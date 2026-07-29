# Books Score Aggregator 📚

A Python tool and framework for searching books by title (including Chinese titles), discovering abstract **Works** and their specific language **Editions**, and aggregating rating scores and review counts across multiple platforms (Open Library, Google Books).

---

## Key Features

- **Work & Edition Modeling**: Maps specific book editions (ISBNs, published languages, publishers) to abstract **Works** (Open Library `/works/OL...W` architecture).
- **Multi-Provider Aggregation**: Fetches and aggregates score ratings and rating counts across APIs:
  - **Open Library API**: Work ratings (`average`, `count`) and Work editions list.
  - **Google Books API**: Volume `averageRating` and `ratingsCount` with optional API key support.
- **Chinese Title Support**: Smart search fallback strategies handling short Chinese queries (e.g. `三體`, `原子習慣`, `被討厭的勇氣`).
- **Flexible Table Formatting**: Outputs formatted Markdown tables, colored terminal tables (powered by `rich`), CSV, or JSON exports.

---

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-username/books-score.git
   cd books-score
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
Then open your browser and navigate to `http://localhost:8000`.

To secure and speed up queries with a Google Books API Key, set the environment variable:
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
python main.py "三體"
```

Output:
```markdown
| 書名 | 原作者 | work | Open Library 分數／人數 | Google Books 分數／人數 |
| --- | --- | --- | --- | --- |
| 三体 | 刘慈欣, Vincent Schmitt, Gwennaël Gaffric, Marc Simonetti | /works/OL17267881W | 3.93 / 216 reviews | 4.40 / 3200 reviews |
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
python main.py "三體"
```
Or directly:
```bash
python main.py "三體" --google-key "your_api_key_here"
```

---

## Project Architecture

```
books-score/
├── models.py            # Dataclasses: Work, Edition, PlatformRating
├── aggregator.py        # BookAggregator class combining provider data
├── formatters.py        # Markdown, Rich Table, CSV, JSON formatters
├── main.py              # CLI entry point with argparse
├── requirements.txt     # Python dependencies (requests, rich)
├── providers/
│   ├── base.py          # Abstract BaseProvider interface
│   ├── open_library.py  # Open Library Work/Edition & Rating API provider
│   └── google_books.py  # Google Books Volume & Rating API provider
└── tests/
    └── test_aggregator.py # Unit tests
```

---

## Running Tests

Run the test suite using `unittest`:
```bash
python -m unittest discover -s tests
```

---

## License

MIT License
