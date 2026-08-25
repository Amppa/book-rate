import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from book_rate.models import Work, Edition, SourceRating, RatingRequestPayload
from book_rate.registry import SourceRegistry
from book_rate.resolver import WorkResolver, EditionResolver
from book_rate.orchestrator import RatingOrchestrator
from book_rate.work_preparer import WorkPreparer
from book_rate.utils.formatters import (
    extract_author_list,
    format_work_to_dict,
    format_editions
)

logger = logging.getLogger(__name__)


class BookAggregator:
    """Aggregates book works, editions, and ratings across multiple sources."""

    DEFAULT_EDITION_LIMIT = 2000

    def __init__(self, google_api_key: Optional[str] = None):
        self.google_api_key = google_api_key
        self.registry = SourceRegistry()

        # Instantiate every registered adapter exactly once. Expose both the
        # keyed map (source_instances) and named attributes (self.open_library,
        # self.douban, ...) so existing callers and tests keep working.
        self.source_instances = {}
        for key in SourceRegistry.list_source_keys():
            kwargs = {"api_key": google_api_key} if key == "google_books" else {}
            instance = self.registry.create_source(key, **kwargs)
            self.source_instances[key] = instance
            setattr(self, key, instance)

        self.work_resolver = WorkResolver(registry=self.registry, source_instances=self.source_instances)
        self.edition_resolver = EditionResolver(registry=self.registry, source_instances=self.source_instances)
        self.work_preparer = WorkPreparer(registry=self.registry, source_instances=self.source_instances)

        # Single shared WorkPreparer: the orchestrator reuses this exact
        # instance instead of building its own behind a lambda hook.
        self.orchestrator = RatingOrchestrator(
            registry=self.registry,
            source_instances=self.source_instances,
            work_preparer=self.work_preparer
        )

    def aggregate_by_title(self, title_query: str, limit: int = 5) -> List[Work]:
        """
        Legacy bulk API: search by title and enrich Works with ratings from
        several sources sequentially. Kept because the live network tests
        still exercise it; prefer search_works() and the orchestrator flows
        for production paths.
        """
        clean_query = title_query.strip()
        if not clean_query:
            return []

        # 1. Primary search via Open Library for Work entities
        ol_works = self.open_library.search_works(clean_query, limit=limit)
        
        # 2. Search Google Books for additional works / volume ratings
        gb_works = self.google_books.search_works(clean_query, limit=limit)

        aggregated_works: List[Work] = []

        target_works = ol_works or gb_works

        for work in target_works:
            # Enrich with Google Books rating
            if self.google_books.name not in work.ratings:
                gb_rating = self.google_books.fetch_ratings(work)
                work.ratings[self.google_books.name] = gb_rating or SourceRating(source_name=self.google_books.name)

            # Enrich with Open Library rating
            if self.open_library.name not in work.ratings:
                ol_rating = self.open_library.fetch_ratings(work)
                work.ratings[self.open_library.name] = ol_rating or SourceRating(source_name=self.open_library.name)

            # Enrich with Goodreads rating
            if self.goodreads.name not in work.ratings:
                gr_rating = self.goodreads.fetch_ratings(work)
                work.ratings[self.goodreads.name] = gr_rating or SourceRating(source_name=self.goodreads.name)

            # Enrich with Douban rating
            if self.douban.name not in work.ratings:
                db_rating = self.douban.fetch_ratings(work)
                work.ratings[self.douban.name] = db_rating or SourceRating(source_name=self.douban.name)

            # Enrich with Amazon rating
            if self.amazon.name not in work.ratings:
                am_rating = self.amazon.fetch_ratings(work)
                work.ratings[self.amazon.name] = am_rating or SourceRating(source_name=self.amazon.name)

            # Enrich with Amazon JP rating
            if self.amazon_jp.name not in work.ratings:
                amjp_rating = self.amazon_jp.fetch_ratings(work)
                work.ratings[self.amazon_jp.name] = amjp_rating or SourceRating(source_name=self.amazon_jp.name)

            # Enrich with StoryGraph rating
            if self.storygraph.name not in work.ratings:
                sg_rating = self.storygraph.fetch_ratings(work)
                work.ratings[self.storygraph.name] = sg_rating or SourceRating(source_name=self.storygraph.name)

            # Enrich with Readmoo rating
            if self.readmoo.name not in work.ratings:
                rm_rating = self.readmoo.fetch_ratings(work)
                work.ratings[self.readmoo.name] = rm_rating or SourceRating(source_name=self.readmoo.name)

            aggregated_works.append(work)

        return aggregated_works

    def fetch_editions_for_work(self, work_id: str) -> dict:
        editions = self.edition_resolver.fetch_editions_for_work(work_id)
        return format_editions(editions)

    def search_works(self, q: str, page: int = 1, active_title_sources: Optional[List[str]] = None, google_key: Optional[str] = None) -> List[dict]:
        if active_title_sources is None:
            active_title_sources = []
        works = self.work_resolver.search_works(
            q=q,
            page=page,
            active_title_sources=active_title_sources,
            google_key=google_key
        )
        results = []
        existing_keys = set()
        for w in works:
            author_names = extract_author_list(w)
            key_tuple = (w.title.lower().strip(), "".join(author_names).lower().strip(), w.work_id)
            if key_tuple not in existing_keys:
                results.append(format_work_to_dict(w))
                existing_keys.add(key_tuple)

        return results

    def evaluate_ratings(self, payload: RatingRequestPayload) -> dict:
        """Synchronous multi-source rating aggregation for a locked work."""
        return self.orchestrator.evaluate_all(payload)

    def stream_rating_events(self, payload: RatingRequestPayload):
        """Yield SSE events for a locked work (init, per-source, done)."""
        yield from self.orchestrator.evaluate_stream(payload)

    def check_source_status(self, engine_keys):
        """Check connectivity of the given sources concurrently.

        Returns {engine_key: {"status": "ok"|"failed", "message": str}}.
        """
        def check_engine(key):
            source_inst = self.source_instances.get(key)
            if not source_inst:
                return key, {"status": "failed", "message": "Unknown engine"}
            try:
                is_ok, msg = source_inst.check_connectivity()
                return key, {"status": "ok" if is_ok else "failed", "message": msg}
            except Exception as e:
                return key, {"status": "failed", "message": f"Check Error: {e}"}

        results = {}
        with ThreadPoolExecutor(max_workers=len(engine_keys) or 1) as executor:
            futures = [executor.submit(check_engine, k) for k in engine_keys]
            for future in futures:
                key, res = future.result()
                results[key] = res
        return results
