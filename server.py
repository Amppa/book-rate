from typing import List, Optional
from fastapi import FastAPI, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
import json
import os
import uvicorn

from book_rate.aggregator import BookAggregator
from book_rate.sources.base import SourceNetworkError

app = FastAPI(title="BookRate Aggregator")

# Initialize aggregator
google_key = os.environ.get("GOOGLE_BOOKS_API_KEY")
aggregator = BookAggregator(google_api_key=google_key)


@app.get("/api/search")
def api_search(
    q: str = Query(..., description="Search query"),
    page: int = Query(1, description="Page number"),
    google_key: str = Query(None, description="Optional Google Books API Key"),
    engines: str = Query("open_library,google_books,google_play,goodreads,storygraph,amazon,amazon_jp,douban,douban_api,readmoo,books_tw", description="Comma-separated engines to use"),
    cooldown: Optional[float] = Query(None, description="Optional minimum request cooldown in seconds")
):
    print(f"\n[Search API] User query: '{q}', page: {page}, engines: '{engines}', cooldown: {cooldown}")
    active_title_sources = [e.strip() for e in engines.split(",") if e.strip()]
    if cooldown is not None:
        for e_key in active_title_sources:
            inst = aggregator.source_instances.get(e_key)
            if inst and hasattr(inst, "cooldown"):
                inst.cooldown = cooldown
    try:
        return aggregator.search_works(q, page=page, active_title_sources=active_title_sources, google_key=google_key)
    except SourceNetworkError as sne:
        status = getattr(sne, "status_code", 403) or 403
        raise HTTPException(status_code=status, detail=str(sne))

@app.get("/api/work-editions")
def api_work_editions(
    work_id: str = Query(..., description="Work ID e.g. OL17267881W"),
):
    print(f"\n[Editions API] User requested editions for work: '{work_id}'")
    return aggregator.fetch_editions_for_work(work_id)


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



@app.get("/api/source-status")
def api_source_status(
    engines: str = Query("open_library,google_books,google_play,goodreads,douban,amazon,amazon_jp,storygraph,readmoo,books_tw", description="Comma-separated engines to check")
):
    from concurrent.futures import ThreadPoolExecutor
    print(f"\n[Source Status API] Engines to check: '{engines}'")
    active_engines = [e.strip() for e in engines.split(",") if e.strip()]
    results = {}

    def check_engine(key):
        source_inst = aggregator.source_instances.get(key)
        if not source_inst:
            return key, {"status": "failed", "message": "Unknown engine"}
        try:
            is_ok, msg = source_inst.check_connectivity()
            return key, {
                "status": "ok" if is_ok else "failed",
                "message": msg
            }
        except Exception as e:
            return key, {
                "status": "failed",
                "message": f"Check Error: {str(e)}"
            }

    with ThreadPoolExecutor(max_workers=len(active_engines) or 1) as executor:
        futures = [executor.submit(check_engine, e_key) for e_key in active_engines]
        for future in futures:
            key, res = future.result()
            results[key] = res

    return results


# Serve the frontend prototype files
# Check if "frontend" folder exists, then mount it
frontend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
