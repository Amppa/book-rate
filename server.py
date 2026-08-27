import json
import logging
import os
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Header
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from book_rate.aggregator import BookAggregator
from book_rate.models import RatingRequestPayload
from book_rate.registry import SourceRegistry
from book_rate.sources.base import SourceNetworkError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="BookRate Aggregator")

# Initialize aggregator
google_key = os.environ.get("GOOGLE_BOOKS_API_KEY")
aggregator = BookAggregator(google_api_key=google_key)

# Default engine list shared by API endpoints when clients omit engines.
DEFAULT_ENGINES_CSV = SourceRegistry.default_engines_csv()


@app.get("/api/search")
def api_search(
    q: str = Query(..., description="Search query"),
    page: int = Query(1, description="Page number"),
    x_google_key: Optional[str] = Header(None, alias="X-Google-Key", description="Optional Google Books API Key (Header)"),
    engines: str = Query(DEFAULT_ENGINES_CSV, description="Comma-separated engines to use")
):
    logger.info("[Search API] q='%s', page=%s, engines='%s'", q, page, engines)
    active_title_sources = [e.strip() for e in engines.split(",") if e.strip()]
    try:
        return aggregator.search_works(q, page=page, active_title_sources=active_title_sources, google_key=x_google_key)
    except SourceNetworkError as sne:
        status = getattr(sne, "status_code", 403) or 403
        raise HTTPException(status_code=status, detail=str(sne))


@app.get("/api/work-editions")
def api_work_editions(
    work_id: str = Query(..., description="Work ID e.g. OL17267881W"),
):
    logger.info("[Editions API] requested editions for work '%s'", work_id)
    return aggregator.fetch_editions_for_work(work_id)


@app.post("/api/work-details")
def api_work_details_post(payload: RatingRequestPayload):
    logger.info("[POST Details API] locked work '%s' (title='%s', author='%s')", payload.work_id, payload.title, payload.author)
    return aggregator.evaluate_ratings(payload)


@app.post("/api/work-details-stream")
def api_work_details_stream_post(payload: RatingRequestPayload):
    logger.info("[POST Stream Details API] locked work '%s' (title='%s', author='%s')", payload.work_id, payload.title, payload.author)

    def event_generator():
        for event in aggregator.stream_rating_events(payload):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/source-status")
def api_source_status(
    engines: str = Query(DEFAULT_ENGINES_CSV, description="Comma-separated engines to check")
):
    logger.info("[Source Status API] engines='%s'", engines)
    active_engines = [e.strip() for e in engines.split(",") if e.strip()]
    return aggregator.check_source_status(active_engines)


# Serve the frontend prototype files
frontend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")


if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
