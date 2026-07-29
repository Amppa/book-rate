from fastapi import FastAPI, Query, HTTPException
from fastapi.staticfiles import StaticFiles
import os
import uvicorn

from book_rate.aggregator import BookAggregator
from book_rate.models import Work, Edition, PlatformRating
from book_rate.providers.google_books import GoogleBooksProvider

app = FastAPI(title="BookRate Aggregator")

# Initialize aggregator
google_key = os.environ.get("GOOGLE_BOOKS_API_KEY")
aggregator = BookAggregator(google_api_key=google_key)
open_library = aggregator.open_library
google_books = aggregator.google_books

@app.get("/api/search")
def api_search(
    q: str = Query(..., description="Search query"),
    page: int = Query(1, description="Page number"),
    google_key: str = Query(None, description="Optional Google Books API Key"),
    engines: str = Query("open_library,google_books", description="Comma-separated engines to use")
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
        
    results = []
    # Add Open Library works
    for w in works:
        results.append({
            "key": w.work_id,
            "title": w.title,
            "author_name": [a.strip() for a in w.author.split(",")] if w.author and w.author != "Unknown Author" else ["資料未提供"],
            "first_publish_year": w.first_publish_year,
            "edition_count": w.edition_count
        })
        
    # Add Google Books works, avoiding obvious duplicates by title/author
    existing_keys = {
        (r["title"].lower().strip(), "".join(r["author_name"]).lower().strip())
        for r in results
    }
    
    for w in gb_works:
        author_list = [a.strip() for a in w.author.split(",")] if w.author and w.author != "Unknown Author" else ["資料未提供"]
        key_tuple = (w.title.lower().strip(), "".join(author_list).lower().strip())
        if key_tuple not in existing_keys:
            results.append({
                "key": w.work_id,
                "title": w.title,
                "author_name": author_list,
                "first_publish_year": w.first_publish_year,
                "edition_count": w.edition_count
            })
            existing_keys.add(key_tuple)
            
    return results

@app.get("/api/work-details")
def api_work_details(
    work_id: str = Query(..., description="Work ID e.g. OL17267881W"),
    title: str = Query(None, description="Title of the work"),
    author: str = Query(None, description="Author of the work"),
    google_key: str = Query(None, description="Optional Google Books API Key")
):
    print(f"\n[Details API] User locked work: '{work_id}' (Title: '{title}', Author: '{author}')")
    gb_provider = GoogleBooksProvider(api_key=google_key) if google_key else google_books
    
    if work_id.startswith("gb:"):
        volume_id = work_id[3:]
        gb_work = gb_provider.fetch_volume_by_id(volume_id)
        
        ol_work_mapped = None
        isbn = None
        if gb_work and gb_work.editions:
            isbn = gb_work.editions[0].isbn_13 or gb_work.editions[0].isbn_10
            
        if isbn:
            ol_works_by_isbn = open_library.search_works(f"isbn:{isbn}", limit=1)
            if ol_works_by_isbn:
                ol_work_mapped = ol_works_by_isbn[0]
                
        # Try to map by original English title and English author
        if not ol_work_mapped and gb_work and gb_work.original_title:
            import re
            q_ol = gb_work.original_title
            
            # Extract English name from author string if present (e.g. "James Clear")
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
            elif gb_work.author and gb_work.author not in ["Unknown Author", "資料未提供"]:
                q_ol += f" {gb_work.author}"
                
            print(f"[Details API] Attempting Open Library mapping with query: '{q_ol}'")
            ol_works_by_orig = open_library.search_works(q_ol, limit=1)
            if ol_works_by_orig:
                ol_work_mapped = ol_works_by_orig[0]

        # Fallback to Chinese title and author
        if not ol_work_mapped and title:
            q_title = title
            if author and author != "Unknown Author" and author != "資料未提供":
                q_title += f" {author}"
            ol_works_by_title = open_library.search_works(q_title, limit=1)
            if ol_works_by_title:
                ol_work_mapped = ol_works_by_title[0]
                
        if ol_work_mapped:
            ol_rating = open_library.fetch_ratings(ol_work_mapped)
            ol_editions = open_library.fetch_editions(ol_work_mapped.work_id, limit=100)
        else:
            ol_rating = None
            ol_editions = []
            
        if not ol_editions and gb_work and gb_work.editions:
            ol_editions = gb_work.editions
            
        ratings_dict = {
            "average": ol_rating.rate if ol_rating and ol_rating.rate is not None else 0,
            "count": ol_rating.rating_count if ol_rating and ol_rating.rating_count is not None else 0
        }
        
        entries = []
        for ed in ol_editions:
            langs = []
            if ed.language:
                for l in ed.language.split(","):
                    clean_l = l.strip()
                    if clean_l:
                        langs.append({"key": f"/languages/{clean_l}"})
            
            entries.append({
                "title": ed.title,
                "publish_date": ed.publish_year if ed.publish_year else "出版年未提供",
                "publishers": [ed.publisher] if ed.publisher else [],
                "languages": langs
            })
            
        editions_dict = {
            "size": len(ol_editions),
            "entries": entries
        }
        
        gb_rating = gb_work.ratings.get("Google Books") if gb_work else None
        google_dict = {
            "average": gb_rating.rate if gb_rating and gb_rating.rate is not None else 0,
            "count": gb_rating.rating_count if gb_rating and gb_rating.rating_count is not None else 0,
            "title": (gb_rating.title if gb_rating else None) or title or (gb_work.title if gb_work else ""),
            "quota_exceeded": gb_provider.quota_exceeded
        }
        
        return {
            "ratings": ratings_dict,
            "editions": editions_dict,
            "google": google_dict
        }
        
    else:
        # Ensure work_id starts with /works/
        full_work_id = work_id if work_id.startswith("/works/") else f"/works/{work_id}"
        
        # 1. Fetch Open Library Ratings
        ol_rating = open_library.fetch_ratings(Work(work_id=full_work_id, title="", author=""))
        ratings_dict = {
            "average": ol_rating.rate if ol_rating.rate is not None else 0,
            "count": ol_rating.rating_count if ol_rating.rating_count is not None else 0
        }
        
        # 2. Fetch Open Library Editions (limit 100 as per frontend)
        editions = open_library.fetch_editions(full_work_id, limit=100)
        
        entries = []
        for ed in editions:
            langs = []
            if ed.language:
                for l in ed.language.split(","):
                    clean_l = l.strip()
                    if clean_l:
                        langs.append({"key": f"/languages/{clean_l}"})
            
            entries.append({
                "title": ed.title,
                "publish_date": ed.publish_year if ed.publish_year else "出版年未提供",
                "publishers": [ed.publisher] if ed.publisher else [],
                "languages": langs
            })
            
        editions_dict = {
            "size": len(editions),
            "entries": entries
        }
        
        # 3. Create Work object to query Google Books rating
        dummy_work = Work(
            work_id=full_work_id,
            title=title or "",
            author=author or "",
            editions=editions
        )
        
        gb_rating = gb_provider.fetch_ratings(dummy_work)
        google_dict = {
            "average": gb_rating.rate if gb_rating.rate is not None else 0,
            "count": gb_rating.rating_count if gb_rating.rating_count is not None else 0,
            "title": gb_rating.title or dummy_work.title,
            "quota_exceeded": gb_provider.quota_exceeded
        }
        
        return {
            "ratings": ratings_dict,
            "editions": editions_dict,
            "google": google_dict
        }

# Serve the frontend prototype files
# Check if "frontend" folder exists, then mount it
frontend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
