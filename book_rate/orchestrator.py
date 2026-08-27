import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Generator, List, Optional, Tuple, Any

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
        work_preparer: Optional[WorkPreparer] = None
    ):
        self.registry = registry or SourceRegistry()
        self.source_instances = source_instances or {}
        # BookAggregator injects its single shared WorkPreparer here so both
        # layers operate on the same instance; standalone use builds one.
        self._work_preparer = work_preparer or WorkPreparer(registry=self.registry, source_instances=self.source_instances)

    def _get_source(self, key: str, **kwargs) -> Optional[BaseSource]:
        return self.source_instances.get(key) or self.registry.create_source(key, **kwargs)

    def _fetch_rating_for_engine(
        self,
        engine_key: str,
        target_work: Work,
        strategy: Optional[str],
        ol_rating: Optional[SourceRating],
        google_key: Optional[str],
        cooldown: Optional[float] = None
    ) -> Tuple[str, dict]:
        engine_key_clean = engine_key.strip()
        fallback_title = target_work.title or "Unknown"

        if engine_key_clean == "open_library" and ol_rating and ol_rating.rate is not None:
            return engine_key_clean, format_rating_response(engine_key_clean, ol_rating, fallback_title)

        if engine_key_clean == "google_books" and google_key:
            # Per-request keyed instance: the shared instance was built
            # with the env key (or none) and must not be mutated across requests.
            source_inst = self.registry.create_source("google_books", api_key=google_key)
        else:
            source_inst = self._get_source(engine_key_clean)
        if not source_inst:
            return engine_key_clean, format_rating_response(engine_key_clean, None, fallback_title)

        if cooldown is not None and hasattr(source_inst, "cooldown"):
            source_inst.cooldown = cooldown

        try:
            rating = source_inst.fetch_ratings(target_work, strategy=strategy)
            quota_exceeded = getattr(source_inst, "quota_exceeded", False)
            return engine_key_clean, format_rating_response(engine_key_clean, rating, fallback_title, quota_exceeded=quota_exceeded)
        except Exception as e:
            logger.error(f"Error fetching rating from {engine_key_clean}: {e}")
            err_rating = SourceRating(source_name=engine_key_clean, status=SourceStatus.ERROR.value, error_message=str(e))
            return engine_key_clean, format_rating_response(engine_key_clean, err_rating, fallback_title)

    def prepare_target_work(
        self, req: RatingRequestPayload, active_title_sources: List[str]
    ) -> Tuple[Optional[SourceRating], List[Any], Work, Dict[str, str]]:
        return self._work_preparer.resolve_work_editions_and_ol_rating(
            work_id=req.work_id,
            title=req.title or "",
            author=req.author or "",
            active_title_sources=active_title_sources,
            google_key=req.google_key
        )

    def _prepare_context(self, req: RatingRequestPayload) -> dict:
        """Shared setup for the sync and streaming evaluation paths."""
        active_sources = req.engines if req.engines else self.registry.list_source_keys()
        ol_rating, editions, target_work, crawler_status = self.prepare_target_work(req, active_sources)

        # Merge user edited metadata into target_work
        for field_name in ("search_name", "title_list", "title_zh_list", "author_list", "isbn_list"):
            value = getattr(req, field_name, None)
            if value:
                setattr(target_work, field_name, value)

        return {
            "active_sources": active_sources,
            "ol_rating": ol_rating,
            "editions": editions,
            "target_work": target_work,
            "crawler_status": crawler_status,
            "editions_dict": format_editions(editions),
            "ol_payload": self._ol_rating_payload(ol_rating),
        }

    @staticmethod
    def _ol_rating_payload(ol_rating: Optional[SourceRating]) -> dict:
        if not ol_rating:
            return {"average": 0, "count": 0, "url": None}
        return {
            "average": ol_rating.rate if ol_rating.rate is not None else 0,
            "count": ol_rating.rating_count if ol_rating.rating_count is not None else 0,
            "url": ol_rating.url,
        }

    def _run_engines(self, ctx: dict, req: RatingRequestPayload):
        """Submit every engine concurrently and yield (engine_key, result) pairs."""
        executor = ThreadPoolExecutor(max_workers=len(ctx["active_sources"]) or 1)
        future_to_engine = {}
        try:
            future_to_engine = {
                executor.submit(
                    self._fetch_rating_for_engine,
                    e_key, ctx["target_work"], req.strategies.get(e_key),
                    ctx["ol_rating"], req.google_key, req.cooldown
                ): e_key for e_key in ctx["active_sources"]
            }
            for future in as_completed(future_to_engine):
                yield future.result()
        finally:
            for f in future_to_engine:
                f.cancel()
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                executor.shutdown(wait=False)

    def evaluate_all(self, req: RatingRequestPayload) -> dict:
        ctx = self._prepare_context(req)

        ratings_res: Dict[str, dict] = {}
        for engine_key, res in self._run_engines(ctx, req):
            ratings_res[engine_key] = res

        return {
            "work_id": req.work_id,
            "title": ctx["target_work"].title,
            "author": ctx["target_work"].author,
            "ratings": ratings_res,
            "crawler_status": ctx["crawler_status"],
            "editions": ctx["editions_dict"],
            "ol_rating": ctx["ol_payload"],
        }

    def evaluate_stream(self, req: RatingRequestPayload) -> Generator[dict, None, None]:
        ctx = self._prepare_context(req)

        yield {
            "type": "init",
            "work_id": req.work_id,
            "title": ctx["target_work"].title,
            "author": ctx["target_work"].author,
            "ratings": ctx["ol_payload"],
            "editions": ctx["editions_dict"],
            "crawler_status": ctx["crawler_status"]
        }

        for engine_key, res in self._run_engines(ctx, req):
            yield {"type": "source", "source": engine_key, "data": res}

        yield {"type": "done"}
