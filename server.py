from fastapi import FastAPI, Query, HTTPException
from fastapi.staticfiles import StaticFiles
import os
import uvicorn

from aggregator import BookAggregator
from models import Work, Edition, PlatformRating

app = FastAPI(title="Book Score Aggregator")

# Initialize aggregator
google_key = os.environ.get("GOOGLE_BOOKS_API_KEY")
aggregator = BookAggregator(google_api_key=google_key)
open_library = aggregator.open_library
google_books = aggregator.google_books

@app.get("/api/search")
def api_search(q: str = Query(..., description="Search query")):
    # Call OL search works without fetching editions/ratings
    works = open_library.search_works(q, limit=10, include_details=False)
    
    results = []
    for w in works:
        results.append({
            "key": w.work_id,
            "title": w.title,
            "author_name": [a.strip() for a in w.author.split(",")] if w.author and w.author != "Unknown Author" else ["資料未提供"],
            "first_publish_year": w.first_publish_year,
            "edition_count": w.edition_count
        })
    return results

@app.get("/api/work-details")
def api_work_details(
    work_id: str = Query(..., description="Work ID e.g. OL17267881W"),
    title: str = Query(None, description="Title of the work"),
    author: str = Query(None, description="Author of the work")
):
    # Ensure work_id starts with /works/
    full_work_id = work_id if work_id.startswith("/works/") else f"/works/{work_id}"
    
    # 1. Fetch Open Library Ratings
    ol_rating = open_library.fetch_ratings(Work(work_id=full_work_id, title="", author=""))
    ratings_dict = {
        "average": ol_rating.score if ol_rating.score is not None else 0,
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
    
    gb_rating = google_books.fetch_ratings(dummy_work)
    google_dict = {
        "average": gb_rating.score if gb_rating.score is not None else 0,
        "count": gb_rating.rating_count if gb_rating.rating_count is not None else 0,
        "title": gb_rating.title or dummy_work.title
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
