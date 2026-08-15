from typing import List, Optional
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
import json
import os
import uvicorn
from concurrent.futures import ThreadPoolExecutor, as_completed

from book_rate.models import Work, Edition, SourceRating
from book_rate.aggregator import BookAggregator
from book_rate.sources.google_books import GoogleBooksSource

app = FastAPI(title="BookRate Aggregator")

# Initialize aggregator
google_key = os.environ.get("GOOGLE_BOOKS_API_KEY")
aggregator = BookAggregator(google_api_key=google_key)
open_library = aggregator.open_library
google_books = aggregator.google_books
goodreads = aggregator.goodreads
douban = aggregator.douban
amazon = aggregator.amazon
amazon_jp = aggregator.amazon_jp
storygraph = aggregator.storygraph
readmoo = aggregator.readmoo

# 書名資料庫的搜尋優先順序（OL / GB 未啟用時，僅取第一個命中的資料庫）
TITLE_SOURCES = ["goodreads", "storygraph", "amazon", "amazon_jp", "douban", "readmoo"]


def _author_list(work: Work) -> list:
    if work.author and work.author not in ["Unknown Author", "Unknown"]:
        return [a.strip() for a in work.author.split(",")]
    return ["Unknown"]


def _work_to_dict(work: Work) -> dict:
    status = None
    if work.work_id.startswith("gr:") and "Goodreads" in work.ratings:
        status = work.ratings["Goodreads"].status
    elif work.work_id.startswith("sg:") and "StoryGraph" in work.ratings:
        status = work.ratings["StoryGraph"].status
    return {
        "key": work.work_id,
        "title": work.title,
        "author_name": _author_list(work),
        "first_publish_year": work.first_publish_year,
        "edition_count": work.edition_count,
        "isbn": work.isbn,
        "status": status
    }


def _format_editions(editions_list) -> dict:
    entries = []
    seen_isbns = set()
    for ed in editions_list:
        isbn = ed.isbn_13 or ed.isbn_10
        if isbn:
            clean_isbn = isbn.strip().upper()
            if clean_isbn in seen_isbns:
                continue
            seen_isbns.add(clean_isbn)

        langs = []
        if ed.language:
            for l in ed.language.split(","):
                clean_l = l.strip()
                if clean_l:
                    langs.append({"key": f"/languages/{clean_l}"})
        
        entries.append({
            "title": ed.title,
            "publish_date": ed.publish_year if ed.publish_year else None,
            "publishers": [ed.publisher] if ed.publisher else [],
            "languages": langs,
            "isbn_13": ed.isbn_13,
            "isbn_10": ed.isbn_10
        })
        
    return {
        "size": len(entries),
        "entries": entries
    }

@app.get("/api/search")
def api_search(
    q: str = Query(..., description="Search query"),
    page: int = Query(1, description="Page number"),
    google_key: str = Query(None, description="Optional Google Books API Key"),
    engines: str = Query("open_library,google_books,goodreads,storygraph,amazon,amazon_jp,douban,readmoo", description="Comma-separated engines to use")
):
    print(f"\n[Search API] User query: '{q}', page: {page}, engines: '{engines}'")
    active_title_sources = [e.strip() for e in engines.split(",") if e.strip()]

    works = []
    if "open_library" in active_title_sources:
        works = open_library.search_works(q, limit=10, page=page, include_details=False)
    
    gb_works = []
    if "google_books" in active_title_sources:
        gb_source = GoogleBooksSource(api_key=google_key) if google_key else google_books
        if "open_library" not in active_title_sources:
            gb_works = gb_source.search_works(q, limit=10, page=page)
        elif page == 1:
            gb_works = gb_source.search_works(q, limit=10, page=1)

    # 其他資料庫：依優先順序僅取第一個命中的資料庫（避免重複的 not-in 條件鏈）
    extra_works = []
    if "open_library" not in active_title_sources and "google_books" not in active_title_sources:
        source_map = {
            "goodreads": goodreads,
            "douban": douban,
            "storygraph": storygraph,
            "amazon": amazon,
            "amazon_jp": amazon_jp,
            "readmoo": readmoo,
        }
        for source in TITLE_SOURCES:
            if source in active_title_sources:
                extra_works = source_map[source].search_works(q, limit=10, page=page)
                break

    results = [_work_to_dict(w) for w in works]
    existing_keys = {
        (r["title"].lower().strip(), "".join(r["author_name"]).lower().strip())
        for r in results
    }

    for w in list(gb_works) + list(extra_works):
        key_tuple = (w.title.lower().strip(), "".join(_author_list(w)).lower().strip())
        if key_tuple not in existing_keys:
            results.append(_work_to_dict(w))
            existing_keys.add(key_tuple)

    return results


def _find_ol_work(isbn: Optional[str], title: Optional[str], author: Optional[str], active_title_sources: list) -> Optional[Work]:
    """Helper to map any source book (ISBN/title/author) to Open Library Work."""
    if "open_library" not in active_title_sources:
        return None
    if isbn:
        ol_works = open_library.search_works(f"isbn:{isbn}", limit=1)
        if ol_works:
            return ol_works[0]
    clean_author = ""
    if author and author not in ["Unknown Author", "Unknown"]:
        clean_author = author.split(",")[0].strip()
    if title:
        q = f"{title} {clean_author}".strip()
        ol_works = open_library.search_works(q, limit=1)
        if ol_works:
            return ol_works[0]
        ol_works_title = open_library.search_works(title, limit=1)
        if ol_works_title:
            return ol_works_title[0]
    return None


def _fallback_edition_list(
    edition_id: str,
    title: str,
    isbn: Optional[str] = None,
    pub_year: Optional[str] = None,
) -> list:
    """Build a single fallback Edition list when no OL editions could be resolved."""
    ed = Edition(
        edition_id=edition_id,
        title=title,
        publish_year=pub_year,
        isbn_13=isbn if isbn and len(isbn) == 13 else None,
        isbn_10=isbn if isbn and len(isbn) == 10 else None,
    )
    return [ed]


def _apply_ol_mapping(
    isbn: Optional[str],
    title: str,
    author: str,
    active_title_sources: list,
) -> tuple[SourceRating, list]:
    """Map a source book to an Open Library Work; return (ol_rating, editions)."""
    ol_work_mapped = _find_ol_work(isbn, title, author, active_title_sources)
    if ol_work_mapped:
        ol_rating = open_library.fetch_ratings(ol_work_mapped)
        return ol_rating, open_library.fetch_editions(ol_work_mapped.work_id, limit=100)
    return SourceRating("Open Library"), []


def _resolve_work_editions_and_ol_rating(
    work_id: str,
    title: str,
    author: str,
    active_title_sources: list,
    gb_source: Optional[GoogleBooksSource] = None
) -> tuple[SourceRating, list, Work, dict]:
    """Resolve Open Library rating, editions, and target Work for any work_id (OL, GB, GR, DB, SG, AMJP, RM)."""
    ol_rating = SourceRating("Open Library")
    editions = []
    resolved_title = title or ""
    resolved_author = author or ""
    resolved_isbn = None
    crawler_status = {}

    if work_id.startswith("gb:"):
        volume_id = work_id[3:]
        source = gb_source or google_books
        gb_work = source.fetch_volume_by_id(volume_id)
        crawler_status["google_books"] = "Normal" if gb_work else "Volume not found"
        if gb_work:
            resolved_title = gb_work.title or title or "Unknown"
            resolved_author = gb_work.author or author or "Unknown"
            if gb_work.editions:
                resolved_isbn = gb_work.editions[0].isbn_13 or gb_work.editions[0].isbn_10

        ol_rating, editions = _apply_ol_mapping(resolved_isbn, resolved_title, resolved_author, active_title_sources)

        if not editions and gb_work and gb_work.editions:
            editions = gb_work.editions

        if not editions:
            editions = _fallback_edition_list(
                volume_id,
                resolved_title,
                isbn=resolved_isbn,
                pub_year=str(gb_work.first_publish_year) if gb_work and gb_work.first_publish_year else None,
            )

        target_work = Work(
            work_id=work_id,
            title=resolved_title,
            author=resolved_author,
            first_publish_year=gb_work.first_publish_year if gb_work else None,
            edition_count=len(editions),
            editions=editions,
            isbn=resolved_isbn
        )
        if gb_work and "Google Books" in gb_work.ratings:
            target_work.ratings["Google Books"] = gb_work.ratings["Google Books"]

        return ol_rating, editions, target_work, crawler_status

    if work_id.startswith("db:"):
        sub_id = work_id[3:]
        details = douban.fetch_subject_details(sub_id)
        crawler_status["douban"] = "Normal" if details.get("isbn") else "Details not found"
        resolved_isbn = details.get("isbn")
        pub_year = details.get("pub_year")
        resolved_title = details.get("title") or title or "Unknown"

        ol_rating, editions = _apply_ol_mapping(resolved_isbn, resolved_title, resolved_author, active_title_sources)

        if not editions:
            editions = _fallback_edition_list(sub_id, resolved_title, isbn=resolved_isbn, pub_year=pub_year)

        target_work = Work(
            work_id=work_id,
            title=resolved_title,
            author=resolved_author,
            editions=editions,
            isbn=resolved_isbn,
            edition_count=details.get("editions_count") or (len(editions) if editions else None)
        )
        return ol_rating, editions, target_work, crawler_status

    if work_id.startswith("gr:"):
        book_id = work_id[3:]
        details = goodreads.fetch_book_details(book_id)
        crawler_status["goodreads"] = details.get("crawler_status") or "Normal"
        resolved_isbn = details.get("isbn")
        pub_year = details.get("pub_year")

        if details.get("title") and not resolved_title:
            resolved_title = details.get("title")
        if details.get("author") and not resolved_author:
            resolved_author = details.get("author")

        ol_rating, editions = _apply_ol_mapping(resolved_isbn, resolved_title, resolved_author, active_title_sources)

        if not editions:
            gr_work_id = details.get("work_id")
            if gr_work_id:
                editions = goodreads.fetch_editions(gr_work_id, limit=100)

        if not editions:
            editions = _fallback_edition_list(
                book_id, resolved_title or "Unknown", isbn=resolved_isbn, pub_year=pub_year
            )

        target_work = Work(
            work_id=work_id,
            title=resolved_title,
            author=resolved_author,
            editions=editions,
            isbn=resolved_isbn,
            edition_count=details.get("editions_count") or (len(editions) if editions else None)
        )
        return ol_rating, editions, target_work, crawler_status

    if work_id.startswith("sg:"):
        book_id = work_id[3:]
        details = storygraph.fetch_book_details(book_id)
        crawler_status["storygraph"] = details.get("crawler_status") or "Normal"
        resolved_isbn = details.get("isbn")
        pub_year = details.get("pub_year")

        if details.get("title") and not resolved_title:
            resolved_title = details.get("title")
        if details.get("author") and not resolved_author:
            resolved_author = details.get("author")

        ol_rating, editions = _apply_ol_mapping(resolved_isbn, resolved_title, resolved_author, active_title_sources)

        if not editions:
            editions = _fallback_edition_list(
                book_id, resolved_title or "Unknown", isbn=resolved_isbn, pub_year=pub_year
            )

        target_work = Work(
            work_id=work_id,
            title=resolved_title,
            author=resolved_author,
            editions=editions,
            isbn=resolved_isbn,
            edition_count=details.get("editions_count") or (len(editions) if editions else None)
        )
        return ol_rating, editions, target_work, crawler_status

    # 純 ID 型 source（AM / AMJP / RM）：僅靠 title/author 對應 OL，無 ISBN 提取
    if work_id.startswith(("am:", "amjp:", "rm:")):
        book_id = work_id.split(":", 1)[1]
        prov_name = work_id.split(":", 1)[0]
        crawler_status[prov_name] = "Normal"
        ol_rating, editions = _apply_ol_mapping(None, resolved_title, resolved_author, active_title_sources)

        if not editions:
            editions = _fallback_edition_list(book_id, resolved_title or "Unknown")

        target_work = Work(
            work_id=work_id,
            title=resolved_title,
            author=resolved_author,
            editions=editions
        )
        return ol_rating, editions, target_work, crawler_status

    # Open Library work ID
    full_work_id = work_id if work_id.startswith("/works/") else f"/works/{work_id}"
    crawler_status["open_library"] = "Normal"
    if "open_library" in active_title_sources:
        ol_rating = open_library.fetch_ratings(Work(work_id=full_work_id, title="", author=""))
    else:
        ol_rating = SourceRating(source_name="Open Library")
    editions = open_library.fetch_editions(full_work_id, limit=100)
    if editions:
        for ed in editions:
            if ed.isbn_13 or ed.isbn_10:
                resolved_isbn = ed.isbn_13 or ed.isbn_10
                break

    target_work = Work(
        work_id=full_work_id,
        title=resolved_title,
        author=resolved_author,
        editions=editions,
        isbn=resolved_isbn
    )
    return ol_rating, editions, target_work, crawler_status


def _build_source_instances(gb_source: GoogleBooksSource) -> dict:
    """Source key -> instance map used by both rating endpoints."""
    return {
        "google_books": gb_source,
        "goodreads": goodreads,
        "douban": douban,
        "amazon": amazon,
        "amazon_jp": amazon_jp,
        "storygraph": storygraph,
        "readmoo": readmoo,
    }


def parse_json_list(param_str: Optional[str]) -> list:
    if not param_str:
        return []
    try:
        data = json.loads(param_str)
        if isinstance(data, list):
            return [str(item).strip() for item in data if item]
    except Exception:
        pass
    return [item.strip() for item in param_str.split(",") if item.strip()]


def _format_rating_response(source_key: str, s_rating: SourceRating, fallback_title: str, quota_exceeded: bool = False) -> dict:
    return {
        "average": s_rating.rate if s_rating and s_rating.rate is not None else 0,
        "count": s_rating.rating_count if s_rating and s_rating.rating_count is not None else 0,
        "title": (s_rating.title if s_rating else None) or fallback_title,
        "url": s_rating.url if s_rating else None,
        "source": source_key,
        "strategy": s_rating.strategy if s_rating else None,
        "query": s_rating.query if s_rating else "",
        "status": s_rating.status if s_rating else "NO_MATCH",
        "quota_exceeded": quota_exceeded,
        "results": s_rating.results if s_rating else []
    }


@app.get("/api/work-details")
def api_work_details(
    work_id: str = Query(..., description="Work ID e.g. OL17267881W"),
    title: str = Query(None, description="Title of the work"),
    author: str = Query(None, description="Author of the work"),
    google_key: str = Query(None, description="Optional Google Books API Key"),
    engines: str = Query("open_library,google_books,goodreads,storygraph,amazon,amazon_jp,douban,readmoo", description="Comma-separated score engines to fetch"),
    strategies: str = Query(None, description="JSON string of source search strategies"),
    search_name: str = Query(None, description="User input search name"),
    title_list: str = Query(None, description="List of book titles"),
    title_zh_list: str = Query(None, description="List of Asian/Chinese book titles"),
    author_list: str = Query(None, description="List of author names"),
    isbn_list: str = Query(None, description="List of ISBNs")
):
    print(f"\n[Details API] User locked work: '{work_id}' (Title: '{title}', Author: '{author}', Engines: '{engines}')")
    active_rate_sources = [e.strip() for e in engines.split(",") if e.strip()]
    gb_source = GoogleBooksSource(api_key=google_key) if google_key else google_books

    strat_dict = {}
    if strategies:
        try:
            strat_dict = json.loads(strategies)
        except Exception:
            pass

    ol_rating, editions, target_work, crawler_status = _resolve_work_editions_and_ol_rating(
        work_id, title or "", author or "", active_rate_sources, gb_source=gb_source
    )

    target_work.search_name = search_name
    target_work.title_list = parse_json_list(title_list)
    target_work.title_zh_list = parse_json_list(title_zh_list)
    target_work.author_list = parse_json_list(author_list)
    target_work.isbn_list = parse_json_list(isbn_list)

    ratings_dict = {
        "average": ol_rating.rate if ol_rating and ol_rating.rate is not None else 0,
        "count": ol_rating.rating_count if ol_rating and ol_rating.rating_count is not None else 0,
        "url": ol_rating.url if ol_rating else None
    }
    editions_dict = _format_editions(editions)

    result_payload = {
        "ratings": ratings_dict,
        "editions": editions_dict,
        "crawler_status": crawler_status
    }

    fut_dict = {}
    source_instances = _build_source_instances(gb_source)

    with ThreadPoolExecutor(max_workers=7) as executor:
        for p_key, p_inst in source_instances.items():
            if p_key in active_rate_sources:
                p_strat = strat_dict.get(p_key)
                fut_dict[p_key] = executor.submit(p_inst.fetch_ratings, target_work, strategy=p_strat)

        for p_key, fut in fut_dict.items():
            try:
                p_rating = fut.result()
                quota = p_key == "google_books" and gb_source.quota_exceeded
                res_key = p_key
                result_payload[res_key] = _format_rating_response(p_key, p_rating, target_work.title, quota_exceeded=quota)
            except Exception as e:
                res_key = p_key
                result_payload[res_key] = {
                    "average": 0, "count": 0, "title": target_work.title, "url": None,
                    "source": p_key, "strategy": strat_dict.get(p_key), "query": "", "status": "ERROR",
                    "results": []
                }

    return result_payload


PREFIX_MAP = {
    "gr:": goodreads,
    "sg:": storygraph,
    "db:": douban,
    "am:": amazon,
    "amjp:": amazon_jp,
    "rm:": readmoo,
    "gb:": google_books,
}

def resolve_source_and_id(work_id: str):
    for prefix, source in PREFIX_MAP.items():
        if work_id.startswith(prefix):
            return source, work_id, 1000

    if work_id.startswith(("/works/", "OL")) or ":" not in work_id:
        full_id = work_id if work_id.startswith("/works/") else f"/works/{work_id}"
        return open_library, full_id, 100

    return None, work_id, 0

@app.get("/api/work-editions")
def api_work_editions(
    work_id: str = Query(..., description="Work ID e.g. OL17267881W"),
):
    print(f"\n[Editions API] User requested editions for work: '{work_id}'")

    source, formatted_id, limit = resolve_source_and_id(work_id)
    editions = []

    if source and hasattr(source, "fetch_editions"):
        try:
            editions = source.fetch_editions(formatted_id, limit=limit)
        except Exception as e:
            print(f"[Editions API] Error fetching editions from {source.name}: {e}")

    return _format_editions(editions)


@app.get("/api/work-details-stream")
def api_work_details_stream(
    work_id: str = Query(..., description="Work ID e.g. OL17267881W"),
    title: str = Query(None, description="Title of the work"),
    author: str = Query(None, description="Author of the work"),
    google_key: str = Query(None, description="Optional Google Books API Key"),
    engines: str = Query("open_library,google_books,goodreads,storygraph,amazon,amazon_jp,douban,readmoo", description="Comma-separated score engines to fetch"),
    strategies: str = Query(None, description="JSON string of source search strategies"),
    search_name: str = Query(None, description="User input search name"),
    title_list: str = Query(None, description="List of book titles"),
    title_zh_list: str = Query(None, description="List of Asian/Chinese book titles"),
    author_list: str = Query(None, description="List of author names"),
    isbn_list: str = Query(None, description="List of ISBNs")
):
    print(f"\n[Stream Details API] User locked work: '{work_id}' (Title: '{title}', Author: '{author}', Engines: '{engines}')")
    active_rate_sources = [e.strip() for e in engines.split(",") if e.strip()]
    gb_source = GoogleBooksSource(api_key=google_key) if google_key else google_books

    strat_dict = {}
    if strategies:
        try:
            strat_dict = json.loads(strategies)
        except Exception:
            pass

    def event_generator():
        ol_rating, editions, target_work, crawler_status = _resolve_work_editions_and_ol_rating(
            work_id, title or "", author or "", active_rate_sources, gb_source=gb_source
        )

        target_work.search_name = search_name
        target_work.title_list = parse_json_list(title_list)
        target_work.title_zh_list = parse_json_list(title_zh_list)
        target_work.author_list = parse_json_list(author_list)
        target_work.isbn_list = parse_json_list(isbn_list)

        ratings_dict = {
            "average": ol_rating.rate if ol_rating and ol_rating.rate is not None else 0,
            "count": ol_rating.rating_count if ol_rating and ol_rating.rating_count is not None else 0,
            "url": ol_rating.url if ol_rating else None
        }
        editions_dict = _format_editions(editions)

        init_data = {
            "type": "init",
            "ratings": ratings_dict,
            "editions": editions_dict,
            "crawler_status": crawler_status
        }
        yield f"data: {json.dumps(init_data)}\n\n"

        fut_map = {}
        source_instances = _build_source_instances(gb_source)

        with ThreadPoolExecutor(max_workers=7) as executor:
            for p_key, p_inst in source_instances.items():
                if p_key in active_rate_sources:
                    p_strat = strat_dict.get(p_key)
                    fut = executor.submit(p_inst.fetch_ratings, target_work, strategy=p_strat)
                    fut_map[fut] = p_key

            for fut in as_completed(fut_map):
                p_key = fut_map[fut]
                try:
                    p_rating = fut.result()
                    quota = p_key == "google_books" and gb_source.quota_exceeded
                    p_dict = _format_rating_response(p_key, p_rating, target_work.title, quota_exceeded=quota)
                except Exception as e:
                    p_dict = {
                        "average": 0, "count": 0, "title": target_work.title, "url": None,
                        "source": p_key, "strategy": strat_dict.get(p_key), "query": "", "status": "ERROR",
                        "results": []
                    }

                yield f"data: {json.dumps({'type': 'source', 'source': p_key, 'data': p_dict})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# Serve the frontend prototype files
# Check if "frontend" folder exists, then mount it
frontend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
