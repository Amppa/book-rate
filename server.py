from typing import List, Optional
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
import json
import os
import uvicorn

from book_rate.aggregator import BookAggregator

app = FastAPI(title="BookRate Aggregator")

# Initialize aggregator
google_key = os.environ.get("GOOGLE_BOOKS_API_KEY")
aggregator = BookAggregator(google_api_key=google_key)


@app.get("/api/search")
def api_search(
    q: str = Query(..., description="Search query"),
    page: int = Query(1, description="Page number"),
    google_key: str = Query(None, description="Optional Google Books API Key"),
    engines: str = Query("open_library,google_books,google_play,goodreads,storygraph,amazon,amazon_jp,douban,readmoo,books_tw", description="Comma-separated engines to use")
):
    print(f"\n[Search API] User query: '{q}', page: {page}, engines: '{engines}'")
    active_title_sources = [e.strip() for e in engines.split(",") if e.strip()]
    return aggregator.search_works(q, page=page, active_title_sources=active_title_sources, google_key=google_key)


@app.get("/api/work-details")
def api_work_details(
    work_id: str = Query(..., description="Work ID e.g. OL17267881W"),
    title: str = Query(None, description="Title of the work"),
    author: str = Query(None, description="Author of the work"),
    google_key: str = Query(None, description="Optional Google Books API Key"),
    engines: str = Query("open_library,google_books,google_play,goodreads,storygraph,amazon,amazon_jp,douban,readmoo,books_tw", description="Comma-separated score engines to fetch"),
    strategies: str = Query(None, description="JSON string of source search strategies"),
    search_name: str = Query(None, description="User input search name"),
    title_list: str = Query(None, description="List of book titles"),
    title_zh_list: str = Query(None, description="List of Asian/Chinese book titles"),
    author_list: str = Query(None, description="List of author names"),
    isbn_list: str = Query(None, description="List of ISBNs")
):
    print(f"\n[Details API] User locked work: '{work_id}' (Title: '{title}', Author: '{author}', Engines: '{engines}')")
    return aggregator.fetch_ratings_for_work(
        work_id=work_id,
        title=title,
        author=author,
        engines=engines,
        strategies=strategies,
        search_name=search_name,
        title_list=title_list,
        title_zh_list=title_zh_list,
        author_list=author_list,
        isbn_list=isbn_list,
        google_key=google_key
    )


@app.get("/api/work-editions")
def api_work_editions(
    work_id: str = Query(..., description="Work ID e.g. OL17267881W"),
):
    print(f"\n[Editions API] User requested editions for work: '{work_id}'")
    return aggregator.fetch_editions_for_work(work_id)


@app.get("/api/work-details-stream")
def api_work_details_stream(
    work_id: str = Query(..., description="Work ID e.g. OL17267881W"),
    title: str = Query(None, description="Title of the work"),
    author: str = Query(None, description="Author of the work"),
    google_key: str = Query(None, description="Optional Google Books API Key"),
    engines: str = Query("open_library,google_books,google_play,goodreads,storygraph,amazon,amazon_jp,douban,readmoo,books_tw", description="Comma-separated score engines to fetch"),
    strategies: str = Query(None, description="JSON string of source search strategies"),
    search_name: str = Query(None, description="User input search name"),
    title_list: str = Query(None, description="List of book titles"),
    title_zh_list: str = Query(None, description="List of Asian/Chinese book titles"),
    author_list: str = Query(None, description="List of author names"),
    isbn_list: str = Query(None, description="List of ISBNs")
):
    print(f"\n[Stream Details API] User locked work: '{work_id}' (Title: '{title}', Author: '{author}', Engines: '{engines}')")

    def event_generator():
        for event in aggregator.fetch_ratings_for_work_stream(
            work_id=work_id,
            title=title,
            author=author,
            engines=engines,
            strategies=strategies,
            search_name=search_name,
            title_list=title_list,
            title_zh_list=title_zh_list,
            author_list=author_list,
            isbn_list=isbn_list,
            google_key=google_key
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


from book_rate.models import RatingRequestPayload


@app.post("/api/work-details")
def api_work_details_post(payload: RatingRequestPayload):
    print(f"\n[POST Details API] User locked work: '{payload.work_id}' (Title: '{payload.title}', Author: '{payload.author}')")
    return aggregator.orchestrator.evaluate_all(payload)


@app.post("/api/work-details-stream")
def api_work_details_stream_post(payload: RatingRequestPayload):
    print(f"\n[POST Stream Details API] User locked work: '{payload.work_id}' (Title: '{payload.title}', Author: '{payload.author}')")

    def event_generator():
        for event in aggregator.orchestrator.evaluate_stream(payload):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")



# Serve the frontend prototype files
# Check if "frontend" folder exists, then mount it
frontend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
