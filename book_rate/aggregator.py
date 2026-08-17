import logging
import json
from typing import List, Optional

from book_rate.models import Work, Edition, SourceRating, RatingRequestPayload
from book_rate.registry import SourceRegistry
from book_rate.resolver import WorkResolver, EditionResolver
from book_rate.orchestrator import RatingOrchestrator
from book_rate.work_preparer import WorkPreparer
from book_rate.sources.google_books import GoogleBooksSource
from book_rate.utils.formatters import (
    extract_author_list,
    format_work_to_dict,
    format_editions
)

logger = logging.getLogger(__name__)


class BookAggregator:
    """Aggregates book works, editions, and ratings across multiple sources."""

    TITLE_SOURCES = SourceRegistry.TITLE_SOURCES
    DEFAULT_EDITION_LIMIT = 2000

    def __init__(self, google_api_key: Optional[str] = None):
        self.google_api_key = google_api_key
        self.registry = SourceRegistry()
        self.open_library = self.registry.create_source("open_library")
        self.google_books = self.registry.create_source("google_books", api_key=google_api_key)
        self.google_play = self.registry.create_source("google_play")
        self.goodreads = self.registry.create_source("goodreads")
        self.douban = self.registry.create_source("douban")
        self.amazon = self.registry.create_source("amazon")
        self.amazon_jp = self.registry.create_source("amazon_jp")
        self.storygraph = self.registry.create_source("storygraph")
        self.readmoo = self.registry.create_source("readmoo")
        self.books_tw = self.registry.create_source("books_tw")

        self.source_instances = {
            "open_library": self.open_library,
            "google_books": self.google_books,
            "google_play": self.google_play,
            "goodreads": self.goodreads,
            "douban": self.douban,
            "amazon": self.amazon,
            "amazon_jp": self.amazon_jp,
            "storygraph": self.storygraph,
            "readmoo": self.readmoo,
            "books_tw": self.books_tw,
        }

        self.work_resolver = WorkResolver(registry=self.registry, source_instances=self.source_instances)
        self.edition_resolver = EditionResolver(registry=self.registry, source_instances=self.source_instances)
        self.work_preparer = WorkPreparer(registry=self.registry, source_instances=self.source_instances)

        self.orchestrator = RatingOrchestrator(
            registry=self.registry,
            source_instances=self.source_instances,
            resolve_work_fn=lambda *args, **kwargs: self.resolve_work_editions_and_ol_rating(*args, **kwargs)
        )

    def aggregate_by_title(self, title_query: str, limit: int = 5) -> List[Work]:
        """
        Search for a book by title, resolve corresponding Works and Editions,
        and fetch rating metrics across all sources.
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

    def parse_json_list(self, param_str: Optional[str]) -> list:
        if not param_str:
            return []
        try:
            data = json.loads(param_str)
            if isinstance(data, list):
                return [str(item).strip() for item in data if item]
        except Exception:
            pass
        return [item.strip() for item in param_str.split(",") if item.strip()]

    def resolve_source_and_id(self, work_id: str):
        return self.edition_resolver.resolve_source_and_id(work_id)

    def fetch_editions_for_work(self, work_id: str) -> dict:
        editions = self.edition_resolver.fetch_editions_for_work(work_id)
        return format_editions(editions)

    def resolve_work_editions_and_ol_rating(
        self,
        work_id: str,
        title: str,
        author: str,
        active_title_sources: list,
        gb_source: Optional[GoogleBooksSource] = None,
        google_key: Optional[str] = None
    ) -> tuple[SourceRating, list, Work, dict]:
        return self.work_preparer.resolve_work_editions_and_ol_rating(
            work_id=work_id,
            title=title,
            author=author,
            active_title_sources=active_title_sources,
            gb_source=gb_source,
            google_key=google_key
        )

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

    def _build_payload(
        self,
        work_id: str,
        title: Optional[str] = None,
        author: Optional[str] = None,
        engines: str = "",
        strategies: Optional[str] = None,
        search_name: Optional[str] = None,
        title_list: Optional[str] = None,
        title_zh_list: Optional[str] = None,
        author_list: Optional[str] = None,
        isbn_list: Optional[str] = None,
        google_key: Optional[str] = None
    ) -> RatingRequestPayload:
        active_rate_sources = [e.strip() for e in engines.split(",") if e.strip()] if engines else self.registry.list_source_keys()

        strat_dict = {}
        if strategies:
            try:
                strat_dict = json.loads(strategies)
            except Exception:
                pass

        return RatingRequestPayload(
            work_id=work_id,
            title=title,
            author=author,
            google_key=google_key or self.google_api_key,
            engines=active_rate_sources,
            strategies=strat_dict,
            search_name=search_name,
            title_list=self.parse_json_list(title_list),
            title_zh_list=self.parse_json_list(title_zh_list),
            author_list=self.parse_json_list(author_list),
            isbn_list=self.parse_json_list(isbn_list)
        )

    def fetch_ratings_for_work(
        self,
        work_id: str,
        title: Optional[str] = None,
        author: Optional[str] = None,
        engines: str = "",
        strategies: Optional[str] = None,
        search_name: Optional[str] = None,
        title_list: Optional[str] = None,
        title_zh_list: Optional[str] = None,
        author_list: Optional[str] = None,
        isbn_list: Optional[str] = None,
        google_key: Optional[str] = None
    ) -> dict:
        req = self._build_payload(
            work_id=work_id, title=title, author=author, engines=engines,
            strategies=strategies, search_name=search_name, title_list=title_list,
            title_zh_list=title_zh_list, author_list=author_list, isbn_list=isbn_list,
            google_key=google_key
        )
        orchestrated = self.orchestrator.evaluate_all(req)

        ol_rating_dict = orchestrated.get("ol_rating") or {"average": 0, "count": 0, "url": None}

        result_payload = {
            "ratings": ol_rating_dict,
            "editions": orchestrated.get("editions"),
            "crawler_status": orchestrated.get("crawler_status")
        }
        for k, v in orchestrated.get("ratings", {}).items():
            result_payload[k] = v

        return result_payload

    def fetch_ratings_for_work_stream(
        self,
        work_id: str,
        title: Optional[str] = None,
        author: Optional[str] = None,
        engines: str = "",
        strategies: Optional[str] = None,
        search_name: Optional[str] = None,
        title_list: Optional[str] = None,
        title_zh_list: Optional[str] = None,
        author_list: Optional[str] = None,
        isbn_list: Optional[str] = None,
        google_key: Optional[str] = None
    ):
        req = self._build_payload(
            work_id=work_id, title=title, author=author, engines=engines,
            strategies=strategies, search_name=search_name, title_list=title_list,
            title_zh_list=title_zh_list, author_list=author_list, isbn_list=isbn_list,
            google_key=google_key
        )
        for event in self.orchestrator.evaluate_stream(req):
            yield event
