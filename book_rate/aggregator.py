import logging
import json
import re
import html
from typing import List, Optional, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

from book_rate.models import Work, Edition, SourceRating
from book_rate.utils.isbn import clean_isbn
from book_rate.sources.open_library import OpenLibrarySource
from book_rate.sources.google_books import GoogleBooksSource
from book_rate.sources.goodreads import GoodreadsSource
from book_rate.sources.douban import DoubanSource
from book_rate.sources.amazon import AmazonSource
from book_rate.sources.amazon_jp import AmazonJPSource
from book_rate.sources.storygraph import StoryGraphSource
from book_rate.sources.readmoo import ReadmooSource
from book_rate.sources.books_tw import BooksTwSource

logger = logging.getLogger(__name__)


class BookAggregator:
    """Aggregates book works, editions, and ratings across multiple sources."""

    TITLE_SOURCES = ["goodreads", "storygraph", "amazon", "amazon_jp", "douban", "readmoo", "books_tw"]
    DEFAULT_EDITION_LIMIT = 2000

    def __init__(self, google_api_key: Optional[str] = None):
        self.open_library = OpenLibrarySource()
        self.google_books = GoogleBooksSource(api_key=google_api_key)
        self.goodreads = GoodreadsSource()
        self.douban = DoubanSource()
        self.amazon = AmazonSource()
        self.amazon_jp = AmazonJPSource()
        self.storygraph = StoryGraphSource()
        self.readmoo = ReadmooSource()
        self.books_tw = BooksTwSource()

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

    def _author_list(self, work: Work) -> list:
        if work.author and work.author not in ["Unknown Author", "Unknown"]:
            return [a.strip() for a in work.author.split(",")]
        return ["Unknown"]

    def _work_to_dict(self, work: Work) -> dict:
        status = None
        if work.work_id.startswith("gr:") and "Goodreads" in work.ratings:
            status = work.ratings["Goodreads"].status
        elif work.work_id.startswith("sg:") and "StoryGraph" in work.ratings:
            status = work.ratings["StoryGraph"].status
        return {
            "key": work.work_id,
            "title": work.title,
            "author_name": self._author_list(work),
            "first_publish_year": work.first_publish_year,
            "edition_count": work.edition_count,
            "isbn": work.isbn,
            "status": status
        }

    def _format_editions(self, editions_list) -> dict:
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
            "size": len(entries),
            "entries": entries
        }

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

    def _format_rating_response(self, source_key: str, s_rating: SourceRating, fallback_title: str, quota_exceeded: bool = False) -> dict:
        return {
            "average": s_rating.rate if s_rating and s_rating.rate is not None else 0,
            "count": s_rating.rating_count if s_rating and s_rating.rating_count is not None else 0,
            "title": (s_rating.title if s_rating else None) or fallback_title,
            "url": s_rating.url if s_rating else None,
            "source": source_key,
            "strategy": s_rating.strategy if s_rating else None,
            "query": s_rating.query if s_rating else "",
            "status": s_rating.status if s_rating else "NO_MATCH",
            "quota_exceeded": quota_exceeded,
            "results": s_rating.results if s_rating else []
        }

    def resolve_source_and_id(self, work_id: str):
        prefix_map = {
            "gr:": self.goodreads,
            "sg:": self.storygraph,
            "db:": self.douban,
            "am:": self.amazon,
            "amjp:": self.amazon_jp,
            "rm:": self.readmoo,
            "gb:": self.google_books,
        }
        for prefix, source in prefix_map.items():
            if work_id.startswith(prefix):
                return source, work_id, self.DEFAULT_EDITION_LIMIT

        if work_id.startswith(("/works/", "OL")) or ":" not in work_id:
            full_id = work_id if work_id.startswith("/works/") else f"/works/{work_id}"
            return self.open_library, full_id, self.DEFAULT_EDITION_LIMIT

        return None, work_id, 0

    def fetch_editions_for_work(self, work_id: str) -> dict:
        source, formatted_id, limit = self.resolve_source_and_id(work_id)
        editions = []
        if source and hasattr(source, "fetch_editions"):
            try:
                editions = source.fetch_editions(formatted_id, limit=limit)
            except Exception as e:
                logger.warning(f"Error fetching editions from {source.name}: {e}")
        return self._format_editions(editions)

    def _find_ol_work(self, isbn: Optional[str], title: Optional[str], author: Optional[str], active_title_sources: list) -> Optional[Work]:
        if "open_library" not in active_title_sources:
            return None
        if isbn:
            ol_works = self.open_library.search_works(f"isbn:{isbn}", limit=1)
            if ol_works:
                return ol_works[0]
        clean_author = ""
        if author and author not in ["Unknown Author", "Unknown"]:
            clean_author = author.split(",")[0].strip()
        if title:
            q = f"{title} {clean_author}".strip()
            ol_works = self.open_library.search_works(q, limit=1)
            if ol_works:
                return ol_works[0]
            ol_works_title = self.open_library.search_works(title, limit=1)
            if ol_works_title:
                return ol_works_title[0]
        return None

    def _fallback_edition_list(self, edition_id: str, title: str, isbn: Optional[str] = None, pub_year: Optional[str] = None) -> list:
        ed = Edition(
            edition_id=edition_id,
            title=title,
            publish_year=pub_year,
            isbn_13=isbn if isbn and len(isbn) == 13 else None,
            isbn_10=isbn if isbn and len(isbn) == 10 else None,
        )
        return [ed]

    def _apply_ol_mapping(self, isbn: Optional[str], title: str, author: str, active_title_sources: list) -> tuple[SourceRating, list]:
        ol_work_mapped = self._find_ol_work(isbn, title, author, active_title_sources)
        if ol_work_mapped:
            ol_rating = self.open_library.fetch_ratings(ol_work_mapped)
            return ol_rating, self.open_library.fetch_editions(ol_work_mapped.work_id, limit=self.DEFAULT_EDITION_LIMIT)
        return SourceRating("Open Library"), []

    def resolve_work_editions_and_ol_rating(
        self,
        work_id: str,
        title: str,
        author: str,
        active_title_sources: list,
        gb_source: Optional[GoogleBooksSource] = None
    ) -> tuple[SourceRating, list, Work, dict]:
        ol_rating = SourceRating("Open Library")
        editions = []
        resolved_title = title or ""
        resolved_author = author or ""
        resolved_isbn = None
        crawler_status = {}

        if work_id.startswith("gb:"):
            volume_id = work_id[3:]
            source = gb_source or self.google_books
            gb_work = source.fetch_volume_by_id(volume_id)
            crawler_status["google_books"] = "Normal" if gb_work else "Volume not found"
            if gb_work:
                resolved_title = gb_work.title or title or "Unknown"
                resolved_author = gb_work.author or author or "Unknown"
                if gb_work.editions:
                    resolved_isbn = gb_work.editions[0].isbn_13 or gb_work.editions[0].isbn_10

            ol_rating, editions = self._apply_ol_mapping(resolved_isbn, resolved_title, resolved_author, active_title_sources)

            if not editions and gb_work and gb_work.editions:
                editions = gb_work.editions

            if not editions:
                editions = self._fallback_edition_list(
                    volume_id,
                    resolved_title,
                    isbn=resolved_isbn,
                    pub_year=str(gb_work.first_publish_year) if gb_work and gb_work.first_publish_year else None,
                )

            target_work = Work(
                work_id=work_id,
                title=resolved_title,
                author=resolved_author,
                first_publish_year=gb_work.first_publish_year if gb_work else None,
                edition_count=len(editions),
                editions=editions,
                isbn=resolved_isbn
            )
            if gb_work and "Google Books" in gb_work.ratings:
                target_work.ratings["Google Books"] = gb_work.ratings["Google Books"]

            return ol_rating, editions, target_work, crawler_status

        if work_id.startswith("db:"):
            sub_id = work_id[3:]
            details = self.douban.fetch_subject_details(sub_id)
            crawler_status["douban"] = "Normal" if details.get("isbn") else "Details not found"
            resolved_isbn = details.get("isbn")
            pub_year = details.get("pub_year")
            resolved_title = details.get("title") or title or "Unknown"

            ol_rating, editions = self._apply_ol_mapping(resolved_isbn, resolved_title, resolved_author, active_title_sources)

            if not editions:
                editions = self._fallback_edition_list(sub_id, resolved_title, isbn=resolved_isbn, pub_year=pub_year)

            target_work = Work(
                work_id=work_id,
                title=resolved_title,
                author=resolved_author,
                editions=editions,
                isbn=resolved_isbn,
                edition_count=details.get("editions_count") or (len(editions) if editions else None)
            )
            return ol_rating, editions, target_work, crawler_status

        if work_id.startswith("gr:"):
            raw_id = work_id[3:]
            is_work = raw_id.startswith("work/")
            if is_work:
                parts = raw_id.split("/")
                numeric_id = parts[1] if len(parts) > 1 else raw_id
            else:
                numeric_id = raw_id.split("/")[-1] if "/" in raw_id else raw_id

            resolved_isbn = None
            pub_year = None
            gr_editions = []
            details = {}

            if is_work:
                gr_editions = self.goodreads.fetch_editions(numeric_id, limit=self.DEFAULT_EDITION_LIMIT)
                crawler_status["goodreads"] = "Normal" if gr_editions else "No editions found"
                if gr_editions:
                    first_isbn_ed = next((ed for ed in gr_editions if ed.isbn_13 or ed.isbn_10), gr_editions[0])
                    resolved_isbn = first_isbn_ed.isbn_13 or first_isbn_ed.isbn_10
                    pub_year = first_isbn_ed.publish_year
                    if not resolved_title:
                        resolved_title = first_isbn_ed.title
            else:
                details = self.goodreads.fetch_book_details(numeric_id)
                crawler_status["goodreads"] = details.get("crawler_status") or "Normal"
                resolved_isbn = details.get("isbn")
                pub_year = details.get("pub_year")
                if details.get("title") and not resolved_title:
                    resolved_title = details.get("title")
                if details.get("author") and not resolved_author:
                    resolved_author = details.get("author")

            ol_rating, ol_editions = self._apply_ol_mapping(resolved_isbn, resolved_title, resolved_author, active_title_sources)

            if ol_editions:
                editions = ol_editions
            else:
                if is_work:
                    editions = gr_editions
                else:
                    gr_work_id = details.get("work_id")
                    if gr_work_id:
                        editions = self.goodreads.fetch_editions(gr_work_id, limit=self.DEFAULT_EDITION_LIMIT)

            if not editions:
                editions = self._fallback_edition_list(
                    numeric_id, resolved_title or "Unknown", isbn=resolved_isbn, pub_year=pub_year
                )

            target_work = Work(
                work_id=work_id,
                title=resolved_title,
                author=resolved_author,
                editions=editions,
                isbn=resolved_isbn,
                edition_count=details.get("editions_count") or (len(editions) if editions else None)
            )
            return ol_rating, editions, target_work, crawler_status

        if work_id.startswith("sg:"):
            book_id = work_id[3:]
            details = self.storygraph.fetch_book_details(book_id)
            crawler_status["storygraph"] = details.get("crawler_status") or "Normal"
            resolved_isbn = details.get("isbn")
            pub_year = details.get("pub_year")

            if details.get("title") and not resolved_title:
                resolved_title = details.get("title")
            if details.get("author") and not resolved_author:
                resolved_author = details.get("author")

            ol_rating, editions = self._apply_ol_mapping(resolved_isbn, resolved_title, resolved_author, active_title_sources)

            if not editions:
                editions = self._fallback_edition_list(
                    book_id, resolved_title or "Unknown", isbn=resolved_isbn, pub_year=pub_year
                )

            target_work = Work(
                work_id=work_id,
                title=resolved_title,
                author=resolved_author,
                editions=editions,
                isbn=resolved_isbn,
                edition_count=details.get("editions_count") or (len(editions) if editions else None)
            )
            return ol_rating, editions, target_work, crawler_status

        if work_id.startswith(("am:", "amjp:", "rm:", "bk:")):
            book_id = work_id.split(":", 1)[1]
            prov_name = work_id.split(":", 1)[0]
            crawler_status[prov_name] = "Normal"
            ol_rating, editions = self._apply_ol_mapping(None, resolved_title, resolved_author, active_title_sources)

            if not editions:
                editions = self._fallback_edition_list(book_id, resolved_title or "Unknown")

            target_work = Work(
                work_id=work_id,
                title=resolved_title,
                author=resolved_author,
                editions=editions
            )
            return ol_rating, editions, target_work, crawler_status

        # Open Library work ID
        full_work_id = work_id if work_id.startswith("/works/") else f"/works/{work_id}"
        crawler_status["open_library"] = "Normal"
        if "open_library" in active_title_sources:
            ol_rating = self.open_library.fetch_ratings(Work(work_id=full_work_id, title="", author=""))
        else:
            ol_rating = SourceRating(source_name="Open Library")
        editions = self.open_library.fetch_editions(full_work_id, limit=self.DEFAULT_EDITION_LIMIT)
        if editions:
            for ed in editions:
                if ed.isbn_13 or ed.isbn_10:
                    resolved_isbn = ed.isbn_13 or ed.isbn_10
                    break

        target_work = Work(
            work_id=full_work_id,
            title=resolved_title,
            author=resolved_author,
            editions=editions,
            isbn=resolved_isbn
        )
        return ol_rating, editions, target_work, crawler_status

    def _build_source_instances(self, gb_source: GoogleBooksSource) -> dict:
        return {
            "google_books": gb_source,
            "goodreads": self.goodreads,
            "douban": self.douban,
            "amazon": self.amazon,
            "amazon_jp": self.amazon_jp,
            "storygraph": self.storygraph,
            "readmoo": self.readmoo,
            "books_tw": self.books_tw,
        }

    def search_works(self, q: str, page: int = 1, active_title_sources: List[str] = [], google_key: Optional[str] = None) -> List[dict]:
        works = []
        if "open_library" in active_title_sources:
            works = self.open_library.search_works(q, limit=10, page=page, include_details=False)
        
        gb_works = []
        gb_source = GoogleBooksSource(api_key=google_key) if google_key else self.google_books
        if "google_books" in active_title_sources:
            if "open_library" not in active_title_sources:
                gb_works = gb_source.search_works(q, limit=10, page=page)
            elif page == 1:
                gb_works = gb_source.search_works(q, limit=10, page=1)

        extra_works = []
        if "open_library" not in active_title_sources and "google_books" not in active_title_sources:
            source_map = {
                "goodreads": self.goodreads,
                "douban": self.douban,
                "storygraph": self.storygraph,
                "amazon": self.amazon,
                "amazon_jp": self.amazon_jp,
                "readmoo": self.readmoo,
            }
            for source in self.TITLE_SOURCES:
                if source in active_title_sources:
                    extra_works = source_map[source].search_works(q, limit=10, page=page)
                    break

        results = [self._work_to_dict(w) for w in works]
        existing_keys = {
            (r["title"].lower().strip(), "".join(r["author_name"]).lower().strip())
            for r in results
        }

        for w in list(gb_works) + list(extra_works):
            key_tuple = (w.title.lower().strip(), "".join(self._author_list(w)).lower().strip())
            if key_tuple not in existing_keys:
                results.append(self._work_to_dict(w))
                existing_keys.add(key_tuple)

        return results

    def fetch_ratings_for_work(
        self,
        work_id: str,
        title: Optional[str],
        author: Optional[str],
        engines: str,
        strategies: Optional[str],
        search_name: Optional[str],
        title_list: Optional[str],
        title_zh_list: Optional[str],
        author_list: Optional[str],
        isbn_list: Optional[str],
        google_key: Optional[str] = None
    ) -> dict:
        active_rate_sources = [e.strip() for e in engines.split(",") if e.strip()]
        gb_source = GoogleBooksSource(api_key=google_key) if google_key else self.google_books

        strat_dict = {}
        if strategies:
            try:
                strat_dict = json.loads(strategies)
            except Exception:
                pass

        ol_rating, editions, target_work, crawler_status = self.resolve_work_editions_and_ol_rating(
            work_id, title or "", author or "", active_rate_sources, gb_source=gb_source
        )

        target_work.search_name = search_name
        target_work.title_list = self.parse_json_list(title_list)
        target_work.title_zh_list = self.parse_json_list(title_zh_list)
        target_work.author_list = self.parse_json_list(author_list)
        target_work.isbn_list = self.parse_json_list(isbn_list)

        ratings_dict = {
            "average": ol_rating.rate if ol_rating and ol_rating.rate is not None else 0,
            "count": ol_rating.rating_count if ol_rating and ol_rating.rating_count is not None else 0,
            "url": ol_rating.url if ol_rating else None
        }
        editions_dict = self._format_editions(editions)

        result_payload = {
            "ratings": ratings_dict,
            "editions": editions_dict,
            "crawler_status": crawler_status
        }

        fut_dict = {}
        source_instances = self._build_source_instances(gb_source)

        with ThreadPoolExecutor(max_workers=7) as executor:
            for p_key, p_inst in source_instances.items():
                if p_key in active_rate_sources:
                    p_strat = strat_dict.get(p_key)
                    fut_dict[p_key] = executor.submit(p_inst.fetch_ratings, target_work, strategy=p_strat)

            for p_key, fut in fut_dict.items():
                try:
                    p_rating = fut.result()
                    quota = p_key == "google_books" and gb_source.quota_exceeded
                    result_payload[p_key] = self._format_rating_response(p_key, p_rating, target_work.title, quota_exceeded=quota)
                except Exception:
                    result_payload[p_key] = {
                        "average": 0, "count": 0, "title": target_work.title, "url": None,
                        "source": p_key, "strategy": strat_dict.get(p_key), "query": "", "status": "ERROR",
                        "results": []
                    }

        return result_payload

    def fetch_ratings_for_work_stream(
        self,
        work_id: str,
        title: Optional[str],
        author: Optional[str],
        engines: str,
        strategies: Optional[str],
        search_name: Optional[str],
        title_list: Optional[str],
        title_zh_list: Optional[str],
        author_list: Optional[str],
        isbn_list: Optional[str],
        google_key: Optional[str] = None
    ):
        active_rate_sources = [e.strip() for e in engines.split(",") if e.strip()]
        gb_source = GoogleBooksSource(api_key=google_key) if google_key else self.google_books

        strat_dict = {}
        if strategies:
            try:
                strat_dict = json.loads(strategies)
            except Exception:
                pass

        ol_rating, editions, target_work, crawler_status = self.resolve_work_editions_and_ol_rating(
            work_id, title or "", author or "", active_rate_sources, gb_source=gb_source
        )

        target_work.search_name = search_name
        target_work.title_list = self.parse_json_list(title_list)
        target_work.title_zh_list = self.parse_json_list(title_zh_list)
        target_work.author_list = self.parse_json_list(author_list)
        target_work.isbn_list = self.parse_json_list(isbn_list)

        ratings_dict = {
            "average": ol_rating.rate if ol_rating and ol_rating.rate is not None else 0,
            "count": ol_rating.rating_count if ol_rating and ol_rating.rating_count is not None else 0,
            "url": ol_rating.url if ol_rating else None
        }
        editions_dict = self._format_editions(editions)

        init_data = {
            "type": "init",
            "ratings": ratings_dict,
            "editions": editions_dict,
            "crawler_status": crawler_status
        }
        yield init_data

        fut_map = {}
        source_instances = self._build_source_instances(gb_source)

        with ThreadPoolExecutor(max_workers=7) as executor:
            for p_key, p_inst in source_instances.items():
                if p_key in active_rate_sources:
                    p_strat = strat_dict.get(p_key)
                    fut = executor.submit(p_inst.fetch_ratings, target_work, strategy=p_strat)
                    fut_map[fut] = p_key

            for fut in as_completed(fut_map):
                p_key = fut_map[fut]
                try:
                    p_rating = fut.result()
                    quota = p_key == "google_books" and gb_source.quota_exceeded
                    p_dict = self._format_rating_response(p_key, p_rating, target_work.title, quota_exceeded=quota)
                except Exception:
                    p_dict = {
                        "average": 0, "count": 0, "title": target_work.title, "url": None,
                        "source": p_key, "strategy": strat_dict.get(p_key), "query": "", "status": "ERROR",
                        "results": []
                    }

                yield {"type": "source", "source": p_key, "data": p_dict}

        yield {"type": "done"}
