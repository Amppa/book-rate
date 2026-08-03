from typing import List, Optional
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
import json
import os
import uvicorn
from concurrent.futures import ThreadPoolExecutor, as_completed

from book_rate.models import Work, Edition, PlatformRating
from book_rate.aggregator import BookAggregator
from book_rate.providers.google_books import GoogleBooksProvider

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

def _format_editions(editions_list) -> dict:
    entries = []
    for ed in editions_list:
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
        "size": len(editions_list),
        "entries": entries
    }

@app.get("/api/search")
def api_search(
    q: str = Query(..., description="Search query"),
    page: int = Query(1, description="Page number"),
    google_key: str = Query(None, description="Optional Google Books API Key"),
    engines: str = Query("open_library,google_books,goodreads,douban,storygraph,amazon_jp", description="Comma-separated engines to use")
):
    print(f"\n[Search API] User query: '{q}', page: {page}, engines: '{engines}'")
    active_engines = [e.strip() for e in engines.split(",") if e.strip()]

    works = []
    if "open_library" in active_engines:
        works = open_library.search_works(q, limit=10, page=page, include_details=False)
    
    gb_works = []
    if "google_books" in active_engines:
        gb_provider = GoogleBooksProvider(api_key=google_key) if google_key else google_books
        if "open_library" not in active_engines:
            gb_works = gb_provider.search_works(q, limit=10, page=page)
        elif page == 1:
            gb_works = gb_provider.search_works(q, limit=10, page=1)
            
    gr_works = []
    if "goodreads" in active_engines and "open_library" not in active_engines and "google_books" not in active_engines:
        gr_works = goodreads.search_works(q, limit=10, page=page)
        
    db_works = []
    if "douban" in active_engines and "open_library" not in active_engines and "google_books" not in active_engines and "goodreads" not in active_engines:
        db_works = douban.search_works(q, limit=10, page=page)

    sg_works = []
    if "storygraph" in active_engines and "open_library" not in active_engines and "google_books" not in active_engines and "goodreads" not in active_engines and "douban" not in active_engines:
        sg_works = storygraph.search_works(q, limit=10, page=page)

    amjp_works = []
    if "amazon_jp" in active_engines and "open_library" not in active_engines and "google_books" not in active_engines and "goodreads" not in active_engines and "douban" not in active_engines and "storygraph" not in active_engines:
        amjp_works = amazon_jp.search_works(q, limit=10, page=page)

    rm_works = []
    if "readmoo" in active_engines and "open_library" not in active_engines and "google_books" not in active_engines and "goodreads" not in active_engines and "douban" not in active_engines and "storygraph" not in active_engines and "amazon_jp" not in active_engines:
        rm_works = readmoo.search_works(q, limit=10, page=page)

    results = []
    # Add Open Library works
    for w in works:
        results.append({
            "key": w.work_id,
            "title": w.title,
            "author_name": [a.strip() for a in w.author.split(",")] if w.author and w.author not in ["Unknown Author", "Unknown"] else ["Unknown"],
            "first_publish_year": w.first_publish_year,
            "edition_count": w.edition_count,
            "isbn": w.isbn
        })
        
    existing_keys = {
        (r["title"].lower().strip(), "".join(r["author_name"]).lower().strip())
        for r in results
    }
    
    for extra_works in [gb_works, gr_works, db_works, sg_works, amjp_works, rm_works]:
        for w in extra_works:
            author_list = [a.strip() for a in w.author.split(",")] if w.author and w.author not in ["Unknown Author", "Unknown"] else ["Unknown"]
            key_tuple = (w.title.lower().strip(), "".join(author_list).lower().strip())
            if key_tuple not in existing_keys:
                results.append({
                    "key": w.work_id,
                    "title": w.title,
                    "author_name": author_list,
                    "first_publish_year": w.first_publish_year,
                    "edition_count": w.edition_count,
                    "isbn": w.isbn
                })
                existing_keys.add(key_tuple)
            
    return results


def _find_ol_work(isbn: Optional[str], title: Optional[str], author: Optional[str], active_engines: list) -> Optional[Work]:
    """Helper to map any provider book (ISBN/title/author) to Open Library Work."""
    if "open_library" not in active_engines:
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


def _resolve_work_editions_and_ol_rating(
    work_id: str,
    title: str,
    author: str,
    active_engines: list,
    gb_provider: Optional[GoogleBooksProvider] = None
) -> tuple[PlatformRating, list, Work]:
    """Helper to resolve Open Library rating, editions, and target Work object for any work_id (OL, GB, GR, DB, SG, AMJP, RM)."""
    ol_rating = PlatformRating("Open Library")
    editions = []
    resolved_title = title or ""
    resolved_author = author or ""
    resolved_isbn = None

    if work_id.startswith("gb:"):
        volume_id = work_id[3:]
        provider = gb_provider or google_books
        gb_work = provider.fetch_volume_by_id(volume_id)
        if gb_work:
            resolved_title = gb_work.title or title or "Unknown"
            resolved_author = gb_work.author or author or "Unknown"
            if gb_work.editions:
                resolved_isbn = gb_work.editions[0].isbn_13 or gb_work.editions[0].isbn_10

        ol_work_mapped = _find_ol_work(resolved_isbn, resolved_title, resolved_author, active_engines)
        if ol_work_mapped:
            ol_rating = open_library.fetch_ratings(ol_work_mapped)
            editions = open_library.fetch_editions(ol_work_mapped.work_id, limit=100)

        if not editions and gb_work and gb_work.editions:
            editions = gb_work.editions

        if not editions:
            ed = Edition(
                edition_id=volume_id,
                title=resolved_title,
                publish_year=str(gb_work.first_publish_year) if gb_work and gb_work.first_publish_year else None,
                isbn_13=resolved_isbn if resolved_isbn and len(resolved_isbn) == 13 else None,
                isbn_10=resolved_isbn if resolved_isbn and len(resolved_isbn) == 10 else None
            )
            editions = [ed]

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

        return ol_rating, editions, target_work

    elif work_id.startswith("db:"):
        sub_id = work_id[3:]
        details = douban.fetch_subject_details(sub_id)
        resolved_isbn = details.get("isbn")
        pub_year = details.get("pub_year")
        resolved_title = details.get("title") or title or "Unknown"

        ol_work_mapped = _find_ol_work(resolved_isbn, resolved_title, resolved_author, active_engines)
        if ol_work_mapped:
            ol_rating = open_library.fetch_ratings(ol_work_mapped)
            editions = open_library.fetch_editions(ol_work_mapped.work_id, limit=100)

        if not editions:
            ed = Edition(
                edition_id=sub_id,
                title=resolved_title,
                publish_year=pub_year,
                isbn_13=resolved_isbn if resolved_isbn and len(resolved_isbn) == 13 else None,
                isbn_10=resolved_isbn if resolved_isbn and len(resolved_isbn) == 10 else None
            )
            editions = [ed]

        target_work = Work(
            work_id=work_id,
            title=resolved_title,
            author=resolved_author,
            editions=editions,
            isbn=resolved_isbn
        )
        return ol_rating, editions, target_work

    elif work_id.startswith("gr:"):
        book_id = work_id[3:]
        details = goodreads.fetch_book_details(book_id)
        resolved_isbn = details.get("isbn")
        pub_year = details.get("pub_year")

        ol_work_mapped = _find_ol_work(resolved_isbn, resolved_title, resolved_author, active_engines)
        if ol_work_mapped:
            ol_rating = open_library.fetch_ratings(ol_work_mapped)
            editions = open_library.fetch_editions(ol_work_mapped.work_id, limit=100)

        if not editions:
            ed = Edition(
                edition_id=book_id,
                title=resolved_title or "Unknown",
                publish_year=pub_year,
                isbn_13=resolved_isbn if resolved_isbn and len(resolved_isbn) == 13 else None,
                isbn_10=resolved_isbn if resolved_isbn and len(resolved_isbn) == 10 else None
            )
            editions = [ed]

        target_work = Work(
            work_id=work_id,
            title=resolved_title,
            author=resolved_author,
            editions=editions,
            isbn=resolved_isbn
        )
        return ol_rating, editions, target_work

    elif work_id.startswith("sg:"):
        book_id = work_id[3:]
        ol_work_mapped = _find_ol_work(None, resolved_title, resolved_author, active_engines)
        if ol_work_mapped:
            ol_rating = open_library.fetch_ratings(ol_work_mapped)
            editions = open_library.fetch_editions(ol_work_mapped.work_id, limit=100)

        if not editions:
            ed = Edition(
                edition_id=book_id,
                title=resolved_title or "Unknown"
            )
            editions = [ed]

        target_work = Work(
            work_id=work_id,
            title=resolved_title,
            author=resolved_author,
            editions=editions
        )
        return ol_rating, editions, target_work

    elif work_id.startswith("amjp:"):
        book_id = work_id[5:]
        ol_work_mapped = _find_ol_work(None, resolved_title, resolved_author, active_engines)
        if ol_work_mapped:
            ol_rating = open_library.fetch_ratings(ol_work_mapped)
            editions = open_library.fetch_editions(ol_work_mapped.work_id, limit=100)

        if not editions:
            ed = Edition(
                edition_id=book_id,
                title=resolved_title or "Unknown"
            )
            editions = [ed]

        target_work = Work(
            work_id=work_id,
            title=resolved_title,
            author=resolved_author,
            editions=editions
        )
        return ol_rating, editions, target_work

    elif work_id.startswith("rm:"):
        book_id = work_id[3:]
        ol_work_mapped = _find_ol_work(None, resolved_title, resolved_author, active_engines)
        if ol_work_mapped:
            ol_rating = open_library.fetch_ratings(ol_work_mapped)
            editions = open_library.fetch_editions(ol_work_mapped.work_id, limit=100)

        if not editions:
            ed = Edition(
                edition_id=book_id,
                title=resolved_title or "Unknown"
            )
            editions = [ed]

        target_work = Work(
            work_id=work_id,
            title=resolved_title,
            author=resolved_author,
            editions=editions
        )
        return ol_rating, editions, target_work

    else:
        full_work_id = work_id if work_id.startswith("/works/") else f"/works/{work_id}"
        if "open_library" in active_engines:
            ol_rating = open_library.fetch_ratings(Work(work_id=full_work_id, title="", author=""))
        else:
            ol_rating = PlatformRating(platform_name="Open Library")
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
        return ol_rating, editions, target_work


def _format_rating_response(provider_key: str, p_rating: PlatformRating, fallback_title: str, quota_exceeded: bool = False) -> dict:
    return {
        "average": p_rating.rate if p_rating and p_rating.rate is not None else 0,
        "count": p_rating.rating_count if p_rating and p_rating.rating_count is not None else 0,
        "title": (p_rating.title if p_rating else None) or fallback_title,
        "url": p_rating.url if p_rating else None,
        "provider": provider_key,
        "strategy": p_rating.strategy if p_rating else None,
        "query": p_rating.query if p_rating else "",
        "status": p_rating.status if p_rating else "NO_MATCH",
        "quota_exceeded": quota_exceeded
    }


@app.get("/api/work-details")
def api_work_details(
    work_id: str = Query(..., description="Work ID e.g. OL17267881W"),
    title: str = Query(None, description="Title of the work"),
    author: str = Query(None, description="Author of the work"),
    google_key: str = Query(None, description="Optional Google Books API Key"),
    engines: str = Query("open_library,google_books,goodreads,douban,amazon,amazon_jp,storygraph", description="Comma-separated score engines to fetch"),
    strategies: str = Query(None, description="JSON string of provider search strategies")
):
    print(f"\n[Details API] User locked work: '{work_id}' (Title: '{title}', Author: '{author}', Engines: '{engines}')")
    active_engines = [e.strip() for e in engines.split(",") if e.strip()]
    gb_provider = GoogleBooksProvider(api_key=google_key) if google_key else google_books

    strat_dict = {}
    if strategies:
        try:
            strat_dict = json.loads(strategies)
        except Exception:
            pass

    ol_rating, editions, target_work = _resolve_work_editions_and_ol_rating(
        work_id, title or "", author or "", active_engines, gb_provider=gb_provider
    )

    ratings_dict = {
        "average": ol_rating.rate if ol_rating and ol_rating.rate is not None else 0,
        "count": ol_rating.rating_count if ol_rating and ol_rating.rating_count is not None else 0,
        "url": ol_rating.url if ol_rating else None
    }
    editions_dict = _format_editions(editions)

    result_payload = {
        "ratings": ratings_dict,
        "editions": editions_dict
    }

    fut_dict = {}
    prov_instances = {
        "google_books": gb_provider,
        "goodreads": goodreads,
        "douban": douban,
        "amazon": amazon,
        "amazon_jp": amazon_jp,
        "storygraph": storygraph,
        "readmoo": readmoo
    }

    with ThreadPoolExecutor(max_workers=7) as executor:
        for p_key, p_inst in prov_instances.items():
            if p_key in active_engines:
                p_strat = strat_dict.get(p_key)
                fut_dict[p_key] = executor.submit(p_inst.fetch_ratings, target_work, strategy=p_strat)

        for p_key, fut in fut_dict.items():
            try:
                p_rating = fut.result()
                quota = p_key == "google_books" and gb_provider.quota_exceeded
                res_key = "google" if p_key == "google_books" else p_key
                result_payload[res_key] = _format_rating_response(p_key, p_rating, target_work.title, quota_exceeded=quota)
            except Exception as e:
                res_key = "google" if p_key == "google_books" else p_key
                result_payload[res_key] = {
                    "average": 0, "count": 0, "title": target_work.title, "url": None,
                    "provider": p_key, "strategy": strat_dict.get(p_key), "query": "", "status": "ERROR"
                }

    return result_payload


@app.get("/api/work-details-stream")
def api_work_details_stream(
    work_id: str = Query(..., description="Work ID e.g. OL17267881W"),
    title: str = Query(None, description="Title of the work"),
    author: str = Query(None, description="Author of the work"),
    google_key: str = Query(None, description="Optional Google Books API Key"),
    engines: str = Query("open_library,google_books,goodreads,douban,amazon,amazon_jp,storygraph", description="Comma-separated score engines to fetch"),
    strategies: str = Query(None, description="JSON string of provider search strategies")
):
    print(f"\n[Stream Details API] User locked work: '{work_id}' (Title: '{title}', Author: '{author}', Engines: '{engines}')")
    active_engines = [e.strip() for e in engines.split(",") if e.strip()]
    gb_provider = GoogleBooksProvider(api_key=google_key) if google_key else google_books

    strat_dict = {}
    if strategies:
        try:
            strat_dict = json.loads(strategies)
        except Exception:
            pass

    def event_generator():
        ol_rating, editions, target_work = _resolve_work_editions_and_ol_rating(
            work_id, title or "", author or "", active_engines, gb_provider=gb_provider
        )

        ratings_dict = {
            "average": ol_rating.rate if ol_rating and ol_rating.rate is not None else 0,
            "count": ol_rating.rating_count if ol_rating and ol_rating.rating_count is not None else 0,
            "url": ol_rating.url if ol_rating else None
        }
        editions_dict = _format_editions(editions)

        init_data = {
            "type": "init",
            "ratings": ratings_dict,
            "editions": editions_dict
        }
        yield f"data: {json.dumps(init_data)}\n\n"

        fut_map = {}
        prov_instances = {
            "google_books": gb_provider,
            "goodreads": goodreads,
            "douban": douban,
            "amazon": amazon,
            "amazon_jp": amazon_jp,
            "storygraph": storygraph,
            "readmoo": readmoo
        }

        with ThreadPoolExecutor(max_workers=7) as executor:
            for p_key, p_inst in prov_instances.items():
                if p_key in active_engines:
                    p_strat = strat_dict.get(p_key)
                    fut = executor.submit(p_inst.fetch_ratings, target_work, strategy=p_strat)
                    fut_map[fut] = p_key

            for fut in as_completed(fut_map):
                p_key = fut_map[fut]
                try:
                    p_rating = fut.result()
                    quota = p_key == "google_books" and gb_provider.quota_exceeded
                    p_dict = _format_rating_response(p_key, p_rating, target_work.title, quota_exceeded=quota)
                except Exception as e:
                    p_dict = {
                        "average": 0, "count": 0, "title": target_work.title, "url": None,
                        "provider": p_key, "strategy": strat_dict.get(p_key), "query": "", "status": "ERROR"
                    }

                yield f"data: {json.dumps({'type': 'platform', 'platform': p_key, 'data': p_dict})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# Serve the frontend prototype files
# Check if "frontend" folder exists, then mount it
frontend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
