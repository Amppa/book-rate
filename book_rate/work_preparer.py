import logging
from typing import List, Optional, Tuple, Any

from book_rate.models import Work, Edition, SourceRating
from book_rate.registry import SourceRegistry

logger = logging.getLogger(__name__)


class WorkPreparer:
    """
    Handles resolving target Work metadata, mapping to Open Library,
    and preparing editions and fallback structures.
    """

    DEFAULT_EDITION_LIMIT = 2000

    def __init__(self, registry: Optional[SourceRegistry] = None, source_instances: Optional[dict] = None):
        self.registry = registry or SourceRegistry()
        self.source_instances = source_instances or {}

    def get_source(self, key: str, google_key: Optional[str] = None):
        if key == "google_books" and google_key:
            return self.registry.create_source("google_books", api_key=google_key)
        if key in self.source_instances:
            return self.source_instances[key]
        return self.registry.create_source(key)

    def _find_ol_work(self, isbn: Optional[str], title: Optional[str], author: Optional[str], active_title_sources: list) -> Optional[Work]:
        if "open_library" not in active_title_sources:
            return None
        ol_source = self.get_source("open_library")
        if isbn:
            ol_works = ol_source.search_works(f"isbn:{isbn}", limit=1)
            if ol_works:
                return ol_works[0]
        clean_author = ""
        if author and author not in ["Unknown Author", "Unknown"]:
            clean_author = author.split(",")[0].strip()
        if title:
            q = f"{title} {clean_author}".strip()
            ol_works = ol_source.search_works(q, limit=1)
            if ol_works:
                return ol_works[0]
            ol_works_title = ol_source.search_works(title, limit=1)
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

    def _apply_ol_mapping(self, isbn: Optional[str], title: str, author: str, active_title_sources: list) -> Tuple[SourceRating, list]:
        ol_work_mapped = self._find_ol_work(isbn, title, author, active_title_sources)
        if ol_work_mapped:
            ol_source = self.get_source("open_library")
            ol_rating = ol_source.fetch_ratings(ol_work_mapped)
            return ol_rating, ol_source.fetch_editions(ol_work_mapped.work_id, limit=self.DEFAULT_EDITION_LIMIT)
        return SourceRating("Open Library"), []

    def resolve_work_editions_and_ol_rating(
        self,
        work_id: str,
        title: str,
        author: str,
        active_title_sources: list,
        gb_source: Optional[Any] = None,
        google_key: Optional[str] = None
    ) -> Tuple[SourceRating, List[Edition], Work, dict]:
        if google_key and not gb_source:
            gb_source = self.get_source("google_books", google_key=google_key)

        ol_rating = SourceRating("Open Library")
        editions = []
        resolved_title = title or ""
        resolved_author = author or ""
        resolved_isbn = None
        crawler_status = {}

        if work_id.startswith("gb:"):
            volume_id = work_id[3:]
            source = gb_source or self.get_source("google_books")
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
            douban_source = self.get_source("douban")
            details = douban_source.fetch_subject_details(sub_id)
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

            goodreads_source = self.get_source("goodreads")
            if is_work:
                gr_editions = goodreads_source.fetch_editions(numeric_id, limit=self.DEFAULT_EDITION_LIMIT)
                crawler_status["goodreads"] = "Normal" if gr_editions else "No editions found"
                if gr_editions:
                    first_isbn_ed = next((ed for ed in gr_editions if ed.isbn_13 or ed.isbn_10), gr_editions[0])
                    resolved_isbn = first_isbn_ed.isbn_13 or first_isbn_ed.isbn_10
                    pub_year = first_isbn_ed.publish_year
                    if not resolved_title:
                        resolved_title = first_isbn_ed.title
            else:
                details = goodreads_source.fetch_book_details(numeric_id)
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
                        editions = goodreads_source.fetch_editions(gr_work_id, limit=self.DEFAULT_EDITION_LIMIT)

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
            storygraph_source = self.get_source("storygraph")
            details = storygraph_source.fetch_book_details(book_id)
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
        ol_source = self.get_source("open_library")
        if "open_library" in active_title_sources:
            ol_rating = ol_source.fetch_ratings(Work(work_id=full_work_id, title="", author=""))
        else:
            ol_rating = SourceRating(source_name="Open Library")
        editions = ol_source.fetch_editions(full_work_id, limit=self.DEFAULT_EDITION_LIMIT)
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
