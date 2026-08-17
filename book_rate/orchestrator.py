import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, Generator, List, Optional, Tuple, Any

from book_rate.models import Work, SourceRating, SourceStatus, RatingRequestPayload
from book_rate.registry import SourceRegistry
from book_rate.sources.base import BaseSource
from book_rate.work_preparer import WorkPreparer
from book_rate.utils.formatters import format_rating_response, format_editions

logger = logging.getLogger(__name__)


class RatingOrchestrator:
    """
    Orchestrates concurrent rating evaluation across active sources in parallel.
    Unifies synchronous aggregation and Server-Sent Events (SSE) streaming responses.
    """

    def __init__(
        self,
        registry: Optional[SourceRegistry] = None,
        source_instances: Optional[Dict[str, BaseSource]] = None,
        resolve_work_fn: Optional[Callable] = None
    ):
        self.registry = registry or SourceRegistry()
        self.source_instances = source_instances or {}
        self._work_preparer = WorkPreparer(registry=self.registry, source_instances=self.source_instances)
        self.resolve_work_fn = resolve_work_fn

    def _get_source(self, key: str, **kwargs) -> Optional[BaseSource]:
        return self.source_instances.get(key) or self.registry.create_source(key, **kwargs)

    def _fetch_rating_for_engine(
        self,
        engine_key: str,
        target_work: Work,
        strategy: Optional[str],
        ol_rating: Optional[SourceRating],
        google_key: Optional[str]
    ) -> Tuple[str, dict]:
        engine_key_clean = engine_key.strip()
        fallback_title = target_work.title or "Unknown"

        if engine_key_clean == "open_library" and ol_rating and ol_rating.rate is not None:
            return engine_key_clean, format_rating_response(engine_key_clean, ol_rating, fallback_title)

        source_inst = self._get_source(engine_key_clean, api_key=google_key if engine_key_clean == "google_books" else None)
        if not source_inst:
            return engine_key_clean, format_rating_response(engine_key_clean, None, fallback_title)

        try:
            rating = source_inst.fetch_ratings(target_work, strategy=strategy)
            quota_exceeded = getattr(source_inst, "quota_exceeded", False)
            return engine_key_clean, format_rating_response(engine_key_clean, rating, fallback_title, quota_exceeded=quota_exceeded)
        except Exception as e:
            logger.error(f"Error fetching rating from {engine_key_clean}: {e}")
            err_rating = SourceRating(source_name=engine_key_clean, status=SourceStatus.ERROR, error_message=str(e))
            return engine_key_clean, format_rating_response(engine_key_clean, err_rating, fallback_title)

    def prepare_target_work(
        self, req: RatingRequestPayload, active_title_sources: List[str]
    ) -> Tuple[Optional[SourceRating], List[Any], Work, Dict[str, str]]:
        if self.resolve_work_fn:
            return self.resolve_work_fn(
                work_id=req.work_id,
                title=req.title or "",
                author=req.author or "",
                active_title_sources=active_title_sources,
                google_key=req.google_key
            )

        return self._work_preparer.resolve_work_editions_and_ol_rating(
            work_id=req.work_id,
            title=req.title or "",
            author=req.author or "",
            active_title_sources=active_title_sources,
            google_key=req.google_key
        )

    def evaluate_all(self, req: RatingRequestPayload) -> dict:
        active_title_sources = req.engines if req.engines else self.registry.list_source_keys()
        ol_rating, editions, target_work, crawler_status = self.prepare_target_work(req, active_title_sources)

        # Merge user edited metadata into target_work
        if req.search_name:
            target_work.search_name = req.search_name
        if req.title_list:
            target_work.title_list = req.title_list
        if req.title_zh_list:
            target_work.title_zh_list = req.title_zh_list
        if req.author_list:
            target_work.author_list = req.author_list
        if req.isbn_list:
            target_work.isbn_list = req.isbn_list

        active_rate_sources = req.engines if req.engines else self.registry.list_source_keys()
        ratings_res: Dict[str, dict] = {}

        with ThreadPoolExecutor(max_workers=len(active_rate_sources) or 1) as executor:
            future_to_engine = {
                executor.submit(
                    self._fetch_rating_for_engine,
                    e_key, target_work, req.strategies.get(e_key), ol_rating, req.google_key
                ): e_key for e_key in active_rate_sources
            }
            for future in as_completed(future_to_engine):
                engine_key, res = future.result()
                ratings_res[engine_key] = res

        ol_average = ol_rating.rate if ol_rating and ol_rating.rate is not None else 0
        ol_count = ol_rating.rating_count if ol_rating and ol_rating.rating_count is not None else 0
        ol_url = ol_rating.url if ol_rating else None

        ol_rating_dict = {
            "average": ol_average,
            "count": ol_count,
            "url": ol_url
        }

        editions_dict = format_editions(editions)

        return {
            "work_id": req.work_id,
            "title": target_work.title,
            "author": target_work.author,
            "ratings": ratings_res,
            "crawler_status": crawler_status,
            "editions": editions_dict,
            "ol_rating": ol_rating_dict
        }

    def evaluate_stream(self, req: RatingRequestPayload) -> Generator[dict, None, None]:
        active_title_sources = req.engines if req.engines else self.registry.list_source_keys()
        ol_rating, editions, target_work, crawler_status = self.prepare_target_work(req, active_title_sources)

        if req.search_name:
            target_work.search_name = req.search_name
        if req.title_list:
            target_work.title_list = req.title_list
        if req.title_zh_list:
            target_work.title_zh_list = req.title_zh_list
        if req.author_list:
            target_work.author_list = req.author_list
        if req.isbn_list:
            target_work.isbn_list = req.isbn_list

        active_rate_sources = req.engines if req.engines else self.registry.list_source_keys()

        editions_dict = format_editions(editions)

        ratings_dict = {
            "average": ol_rating.rate if ol_rating and ol_rating.rate is not None else 0,
            "count": ol_rating.rating_count if ol_rating and ol_rating.rating_count is not None else 0,
            "url": ol_rating.url if ol_rating else None
        } if ol_rating else {"average": 0, "count": 0, "url": None}

        init_data = {
            "type": "init",
            "work_id": req.work_id,
            "title": target_work.title,
            "author": target_work.author,
            "ratings": ratings_dict,
            "editions": editions_dict,
            "crawler_status": crawler_status
        }
        yield init_data

        with ThreadPoolExecutor(max_workers=len(active_rate_sources) or 1) as executor:
            future_to_engine = {
                executor.submit(
                    self._fetch_rating_for_engine,
                    e_key, target_work, req.strategies.get(e_key), ol_rating, req.google_key
                ): e_key for e_key in active_rate_sources
            }
            for future in as_completed(future_to_engine):
                engine_key, res = future.result()
                yield {"type": "source", "source": engine_key, "data": res}

        yield {"type": "done"}
