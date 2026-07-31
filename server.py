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
storygraph = aggregator.storygraph

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
    engines: str = Query("open_library,google_books,goodreads,douban,storygraph", description="Comma-separated engines to use")
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
    
    for extra_works in [gb_works, gr_works, db_works, sg_works]:
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


def _resolve_work_editions_and_ol_rating(work_id: str, title: str, author: str, active_engines: list) -> tuple[PlatformRating, list]:
    """Helper to resolve Open Library rating and editions for any work_id (OL, GB, GR, DB, SG)."""
    if work_id.startswith("db:"):
        sub_id = work_id[3:]
        details = douban.fetch_subject_details(sub_id)
        isbn = details.get("isbn")
        pub_year = details.get("pub_year")
        
        ol_work_mapped = _find_ol_work(isbn, title, author, active_engines)
        if ol_work_mapped:
            ol_rating = open_library.fetch_ratings(ol_work_mapped)
            editions = open_library.fetch_editions(ol_work_mapped.work_id, limit=100)
        else:
            ol_rating = PlatformRating("Open Library")
            editions = []

        if not editions:
            ed = Edition(
                edition_id=sub_id,
                title=details.get("title") or title or "Unknown",
                publish_year=pub_year,
                isbn_13=isbn if isbn and len(isbn) == 13 else None,
                isbn_10=isbn if isbn and len(isbn) == 10 else None
            )
            editions = [ed]
        return ol_rating, editions

    elif work_id.startswith("gr:"):
        book_id = work_id[3:]
        details = goodreads.fetch_book_details(book_id)
        isbn = details.get("isbn")
        pub_year = details.get("pub_year")

        ol_work_mapped = _find_ol_work(isbn, title, author, active_engines)
        if ol_work_mapped:
            ol_rating = open_library.fetch_ratings(ol_work_mapped)
            editions = open_library.fetch_editions(ol_work_mapped.work_id, limit=100)
        else:
            ol_rating = PlatformRating("Open Library")
            editions = []

        if not editions:
            ed = Edition(
                edition_id=book_id,
                title=title or "Unknown",
                publish_year=pub_year,
                isbn_13=isbn if isbn and len(isbn) == 13 else None,
                isbn_10=isbn if isbn and len(isbn) == 10 else None
            )
            editions = [ed]
        return ol_rating, editions

    elif work_id.startswith("sg:"):
        book_id = work_id[3:]
        ol_work_mapped = _find_ol_work(None, title, author, active_engines)
        if ol_work_mapped:
            ol_rating = open_library.fetch_ratings(ol_work_mapped)
            editions = open_library.fetch_editions(ol_work_mapped.work_id, limit=100)
        else:
            ol_rating = PlatformRating("Open Library")
            editions = []

        if not editions:
            ed = Edition(
                edition_id=book_id,
                title=title or "Unknown",
                publish_year=None,
                isbn_13=None,
                isbn_10=None
            )
            editions = [ed]
        return ol_rating, editions

    else:
        full_work_id = work_id if work_id.startswith("/works/") else f"/works/{work_id}"
        if "open_library" in active_engines:
            ol_rating = open_library.fetch_ratings(Work(work_id=full_work_id, title="", author=""))
        else:
            ol_rating = PlatformRating(platform_name="Open Library")
        editions = open_library.fetch_editions(full_work_id, limit=100)
        return ol_rating, editions


@app.get("/api/work-details")
def api_work_details(
    work_id: str = Query(..., description="Work ID e.g. OL17267881W"),
    title: str = Query(None, description="Title of the work"),
    author: str = Query(None, description="Author of the work"),
    google_key: str = Query(None, description="Optional Google Books API Key"),
    engines: str = Query("open_library,google_books,goodreads,douban,amazon,storygraph", description="Comma-separated score engines to fetch")
):
    print(f"\n[Details API] User locked work: '{work_id}' (Title: '{title}', Author: '{author}', Engines: '{engines}')")
    active_engines = [e.strip() for e in engines.split(",") if e.strip()]
    gb_provider = GoogleBooksProvider(api_key=google_key) if google_key else google_books

    if work_id.startswith("gb:"):
        volume_id = work_id[3:]
        gb_work = gb_provider.fetch_volume_by_id(volume_id)

        ol_work_mapped = None
        isbn = None
        if gb_work and gb_work.editions:
            isbn = gb_work.editions[0].isbn_13 or gb_work.editions[0].isbn_10

        if isbn and "open_library" in active_engines:
            ol_works_by_isbn = open_library.search_works(f"isbn:{isbn}", limit=1)
            if ol_works_by_isbn:
                ol_work_mapped = ol_works_by_isbn[0]

        if not ol_work_mapped and gb_work and gb_work.original_title and "open_library" in active_engines:
            import re
            q_ol = gb_work.original_title

            eng_author = None
            for a in gb_work.author.split(","):
                author_matches = re.findall(r'([a-zA-Z\s\-]+)', a)
                for am in author_matches:
                    am_clean = am.strip()
                    if len(am_clean.split()) >= 2:
                        eng_author = am_clean
                        break
                if eng_author:
                    break

            if eng_author:
                q_ol += f" {eng_author}"
            elif gb_work.author and gb_work.author not in ["Unknown Author", "Unknown"]:
                q_ol += f" {gb_work.author}"

            ol_works_by_orig = open_library.search_works(q_ol, limit=1)
            if ol_works_by_orig:
                ol_work_mapped = ol_works_by_orig[0]

        if not ol_work_mapped and title and "open_library" in active_engines:
            q_title = title
            if author and author not in ["Unknown Author", "Unknown"]:
                q_title += f" {author}"
            ol_works_by_title = open_library.search_works(q_title, limit=1)
            if ol_works_by_title:
                ol_work_mapped = ol_works_by_title[0]

        if ol_work_mapped and "open_library" in active_engines:
            ol_rating = open_library.fetch_ratings(ol_work_mapped)
            ol_editions = open_library.fetch_editions(ol_work_mapped.work_id, limit=100)
        else:
            ol_rating = None
            ol_editions = []

        if not ol_editions and gb_work and gb_work.editions:
            ol_editions = gb_work.editions

        ratings_dict = {
            "average": ol_rating.rate if ol_rating and ol_rating.rate is not None else 0,
            "count": ol_rating.rating_count if ol_rating and ol_rating.rating_count is not None else 0,
            "url": ol_rating.url if ol_rating else None
        }

        editions_dict = _format_editions(ol_editions)

        gb_rating = gb_work.ratings.get("Google Books") if (gb_work and "google_books" in active_engines) else None
        google_dict = {
            "average": gb_rating.rate if gb_rating and gb_rating.rate is not None else 0,
            "count": gb_rating.rating_count if gb_rating and gb_rating.rating_count is not None else 0,
            "title": (gb_rating.title if gb_rating else None) or title or (gb_work.title if gb_work else ""),
            "url": gb_rating.url if gb_rating else None,
            "quota_exceeded": gb_provider.quota_exceeded
        }

        target_work = Work(
            work_id=work_id,
            title=title or (gb_work.title if gb_work else ""),
            author=author or (gb_work.author if gb_work else ""),
            original_title=gb_work.original_title if gb_work else None,
            editions=ol_editions or (gb_work.editions if gb_work else [])
        )

        fut_dict = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            if "goodreads" in active_engines:
                fut_dict["gr"] = executor.submit(goodreads.fetch_ratings, target_work)
            if "douban" in active_engines:
                fut_dict["db"] = executor.submit(douban.fetch_ratings, target_work)
            if "amazon" in active_engines:
                fut_dict["am"] = executor.submit(amazon.fetch_ratings, target_work)
            if "storygraph" in active_engines:
                fut_dict["sg"] = executor.submit(storygraph.fetch_ratings, target_work)

            gr_rating = fut_dict["gr"].result() if "gr" in fut_dict else None
            db_rating = fut_dict["db"].result() if "db" in fut_dict else None
            am_rating = fut_dict["am"].result() if "am" in fut_dict else None
            sg_rating = fut_dict["sg"].result() if "sg" in fut_dict else None

        goodreads_dict = {
            "average": gr_rating.rate if gr_rating and gr_rating.rate is not None else 0,
            "count": gr_rating.rating_count if gr_rating and gr_rating.rating_count is not None else 0,
            "title": (gr_rating.title if gr_rating else None) or target_work.title,
            "url": gr_rating.url if gr_rating else None
        }

        douban_dict = {
            "average": db_rating.rate if db_rating and db_rating.rate is not None else 0,
            "count": db_rating.rating_count if db_rating and db_rating.rating_count is not None else 0,
            "title": (db_rating.title if db_rating else None) or target_work.title,
            "url": db_rating.url if db_rating else None
        }

        amazon_dict = {
            "average": am_rating.rate if am_rating and am_rating.rate is not None else 0,
            "count": am_rating.rating_count if am_rating and am_rating.rating_count is not None else 0,
            "title": (am_rating.title if am_rating else None) or target_work.title,
            "url": am_rating.url if am_rating else None
        }

        storygraph_dict = {
            "average": sg_rating.rate if sg_rating and sg_rating.rate is not None else 0,
            "count": sg_rating.rating_count if sg_rating and sg_rating.rating_count is not None else 0,
            "title": (sg_rating.title if sg_rating else None) or target_work.title,
            "url": sg_rating.url if sg_rating else None
        }

        return {
            "ratings": ratings_dict,
            "editions": editions_dict,
            "google": google_dict,
            "goodreads": goodreads_dict,
            "douban": douban_dict,
            "amazon": amazon_dict,
            "storygraph": storygraph_dict
        }

    else:
        ol_rating, editions = _resolve_work_editions_and_ol_rating(work_id, title or "", author or "", active_engines)

        ratings_dict = {
            "average": ol_rating.rate if ol_rating and ol_rating.rate is not None else 0,
            "count": ol_rating.rating_count if ol_rating and ol_rating.rating_count is not None else 0,
            "url": ol_rating.url if ol_rating else None
        }

        editions_dict = _format_editions(editions)

        dummy_work = Work(
            work_id=work_id,
            title=title or "",
            author=author or "",
            editions=editions
        )

        fut_dict = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            if "google_books" in active_engines:
                fut_dict["gb"] = executor.submit(gb_provider.fetch_ratings, dummy_work)
            if "goodreads" in active_engines:
                fut_dict["gr"] = executor.submit(goodreads.fetch_ratings, dummy_work)
            if "douban" in active_engines:
                fut_dict["db"] = executor.submit(douban.fetch_ratings, dummy_work)
            if "amazon" in active_engines:
                fut_dict["am"] = executor.submit(amazon.fetch_ratings, dummy_work)
            if "storygraph" in active_engines:
                fut_dict["sg"] = executor.submit(storygraph.fetch_ratings, dummy_work)

            gb_rating = fut_dict["gb"].result() if "gb" in fut_dict else None
            gr_rating = fut_dict["gr"].result() if "gr" in fut_dict else None
            db_rating = fut_dict["db"].result() if "db" in fut_dict else None
            am_rating = fut_dict["am"].result() if "am" in fut_dict else None
            sg_rating = fut_dict["sg"].result() if "sg" in fut_dict else None

        google_dict = {
            "average": gb_rating.rate if gb_rating and gb_rating.rate is not None else 0,
            "count": gb_rating.rating_count if gb_rating and gb_rating.rating_count is not None else 0,
            "title": (gb_rating.title if gb_rating else None) or dummy_work.title,
            "url": gb_rating.url if gb_rating else None,
            "quota_exceeded": gb_provider.quota_exceeded
        }

        goodreads_dict = {
            "average": gr_rating.rate if gr_rating and gr_rating.rate is not None else 0,
            "count": gr_rating.rating_count if gr_rating and gr_rating.rating_count is not None else 0,
            "title": (gr_rating.title if gr_rating else None) or dummy_work.title,
            "url": gr_rating.url if gr_rating else None
        }

        douban_dict = {
            "average": db_rating.rate if db_rating and db_rating.rate is not None else 0,
            "count": db_rating.rating_count if db_rating and db_rating.rating_count is not None else 0,
            "title": (db_rating.title if db_rating else None) or dummy_work.title,
            "url": db_rating.url if db_rating else None
        }

        amazon_dict = {
            "average": am_rating.rate if am_rating and am_rating.rate is not None else 0,
            "count": am_rating.rating_count if am_rating and am_rating.rating_count is not None else 0,
            "title": (am_rating.title if am_rating else None) or dummy_work.title,
            "url": am_rating.url if am_rating else None
        }

        storygraph_dict = {
            "average": sg_rating.rate if sg_rating and sg_rating.rate is not None else 0,
            "count": sg_rating.rating_count if sg_rating and sg_rating.rating_count is not None else 0,
            "title": (sg_rating.title if sg_rating else None) or dummy_work.title,
            "url": sg_rating.url if sg_rating else None
        }

        return {
            "ratings": ratings_dict,
            "editions": editions_dict,
            "google": google_dict,
            "goodreads": goodreads_dict,
            "douban": douban_dict,
            "amazon": amazon_dict,
            "storygraph": storygraph_dict
        }


@app.get("/api/work-details-stream")
def api_work_details_stream(
    work_id: str = Query(..., description="Work ID e.g. OL17267881W"),
    title: str = Query(None, description="Title of the work"),
    author: str = Query(None, description="Author of the work"),
    google_key: str = Query(None, description="Optional Google Books API Key"),
    engines: str = Query("open_library,google_books,goodreads,douban,amazon,storygraph", description="Comma-separated score engines to fetch")
):
    print(f"\n[Stream Details API] User locked work: '{work_id}' (Title: '{title}', Author: '{author}', Engines: '{engines}')")
    active_engines = [e.strip() for e in engines.split(",") if e.strip()]
    gb_provider = GoogleBooksProvider(api_key=google_key) if google_key else google_books

    def event_generator():
        target_work = None
        if work_id.startswith("gb:"):
            volume_id = work_id[3:]
            gb_work = gb_provider.fetch_volume_by_id(volume_id)

            ol_work_mapped = None
            isbn = None
            if gb_work and gb_work.editions:
                isbn = gb_work.editions[0].isbn_13 or gb_work.editions[0].isbn_10

            if isbn and "open_library" in active_engines:
                ol_works_by_isbn = open_library.search_works(f"isbn:{isbn}", limit=1)
                if ol_works_by_isbn:
                    ol_work_mapped = ol_works_by_isbn[0]

            if not ol_work_mapped and gb_work and gb_work.original_title and "open_library" in active_engines:
                import re
                q_ol = gb_work.original_title
                eng_author = None
                for a in gb_work.author.split(","):
                    author_matches = re.findall(r'([a-zA-Z\s\-]+)', a)
                    for am in author_matches:
                        am_clean = am.strip()
                        if len(am_clean.split()) >= 2:
                            eng_author = am_clean
                            break
                    if eng_author:
                        break
                if eng_author:
                    q_ol += f" {eng_author}"
                elif gb_work.author and gb_work.author not in ["Unknown Author", "Unknown"]:
                    q_ol += f" {gb_work.author}"

                ol_works_by_orig = open_library.search_works(q_ol, limit=1)
                if ol_works_by_orig:
                    ol_work_mapped = ol_works_by_orig[0]

            if not ol_work_mapped and title and "open_library" in active_engines:
                q_title = title
                if author and author not in ["Unknown Author", "Unknown"]:
                    q_title += f" {author}"
                ol_works_by_title = open_library.search_works(q_title, limit=1)
                if ol_works_by_title:
                    ol_work_mapped = ol_works_by_title[0]

            if ol_work_mapped and "open_library" in active_engines:
                ol_rating = open_library.fetch_ratings(ol_work_mapped)
                ol_editions = open_library.fetch_editions(ol_work_mapped.work_id, limit=100)
            else:
                ol_rating = None
                ol_editions = []

            if not ol_editions and gb_work and gb_work.editions:
                ol_editions = gb_work.editions

            ratings_dict = {
                "average": ol_rating.rate if ol_rating and ol_rating.rate is not None else 0,
                "count": ol_rating.rating_count if ol_rating and ol_rating.rating_count is not None else 0,
                "url": ol_rating.url if ol_rating else None
            }
            editions_dict = _format_editions(ol_editions)

            gb_rating = gb_work.ratings.get("Google Books") if (gb_work and "google_books" in active_engines) else None
            google_dict = {
                "average": gb_rating.rate if gb_rating and gb_rating.rate is not None else 0,
                "count": gb_rating.rating_count if gb_rating and gb_rating.rating_count is not None else 0,
                "title": (gb_rating.title if gb_rating else None) or title or (gb_work.title if gb_work else ""),
                "url": gb_rating.url if gb_rating else None,
                "quota_exceeded": gb_provider.quota_exceeded
            }

            target_work = Work(
                work_id=work_id,
                title=title or (gb_work.title if gb_work else ""),
                author=author or (gb_work.author if gb_work else ""),
                original_title=gb_work.original_title if gb_work else None,
                editions=ol_editions or (gb_work.editions if gb_work else [])
            )

            init_data = {
                "type": "init",
                "ratings": ratings_dict,
                "editions": editions_dict,
                "google": google_dict
            }
            yield f"data: {json.dumps(init_data)}\n\n"
        else:
            ol_rating, editions = _resolve_work_editions_and_ol_rating(work_id, title or "", author or "", active_engines)

            ratings_dict = {
                "average": ol_rating.rate if ol_rating and ol_rating.rate is not None else 0,
                "count": ol_rating.rating_count if ol_rating and ol_rating.rating_count is not None else 0,
                "url": ol_rating.url if ol_rating else None
            }

            editions_dict = _format_editions(editions)

            target_work = Work(
                work_id=work_id,
                title=title or "",
                author=author or "",
                editions=editions
            )

            init_data = {
                "type": "init",
                "ratings": ratings_dict,
                "editions": editions_dict
            }
            yield f"data: {json.dumps(init_data)}\n\n"

        # Submit provider tasks to ThreadPoolExecutor and stream each platform as it finishes!
        fut_map = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            if "google_books" in active_engines and not work_id.startswith("gb:"):
                fut_map[executor.submit(gb_provider.fetch_ratings, target_work)] = "google_books"
            if "goodreads" in active_engines:
                fut_map[executor.submit(goodreads.fetch_ratings, target_work)] = "goodreads"
            if "douban" in active_engines:
                fut_map[executor.submit(douban.fetch_ratings, target_work)] = "douban"
            if "amazon" in active_engines:
                fut_map[executor.submit(amazon.fetch_ratings, target_work)] = "amazon"
            if "storygraph" in active_engines:
                fut_map[executor.submit(storygraph.fetch_ratings, target_work)] = "storygraph"

            for fut in as_completed(fut_map):
                p_key = fut_map[fut]
                try:
                    p_rating = fut.result()
                    p_dict = {
                        "average": p_rating.rate if p_rating and p_rating.rate is not None else 0,
                        "count": p_rating.rating_count if p_rating and p_rating.rating_count is not None else 0,
                        "title": (p_rating.title if p_rating else None) or target_work.title,
                        "url": p_rating.url if p_rating else None
                    }
                    if p_key == "google_books":
                        p_dict["quota_exceeded"] = gb_provider.quota_exceeded
                except Exception as e:
                    p_dict = {"average": 0, "count": 0, "title": target_work.title, "url": None}

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
