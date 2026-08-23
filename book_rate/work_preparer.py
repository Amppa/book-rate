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

    _DISPATCH = {
        "google_books": "_prepare_google_books",
        "douban": "_prepare_douban",
        "douban_api": "_prepare_douban_api",
        "goodreads": "_prepare_goodreads",
        "storygraph": "_prepare_storygraph",
        "amazon": "_prepare_generic_prefixed",
        "amazon_jp": "_prepare_generic_prefixed",
        "readmoo": "_prepare_generic_prefixed",
        "books_tw": "_prepare_generic_prefixed",
    }

    def resolve_work_editions_and_ol_rating(
        self,
        work_id: str,
        title: str,
        author: str,
        active_title_sources: list,
        gb_source: Optional[Any] = None,
        google_key: Optional[str] = None
    ) -> Tuple[SourceRating, List[Edition], Work, dict]:
        """Dispatch to the per-platform handler for this work_id."""
        if google_key and not gb_source:
            gb_source = self.get_source("google_books", google_key=google_key)

        prefix, s_key = SourceRegistry.match_id_prefix(work_id)
        handler_name = self._DISPATCH.get(s_key)
        ctx = {
            "work_id": work_id,
            "prefix": prefix,
            "title": title or "",
            "author": author or "",
            "active_title_sources": active_title_sources,
            "gb_source": gb_source,
        }
        if handler_name is None:
            return self._prepare_open_library(ctx)
        return getattr(self, handler_name)(ctx)

    @staticmethod
    def _finalize(ol_rating, editions, work_id, title, author, crawler_status,
                  isbn=None, first_publish_year=None, edition_count=None):
        """Assemble the standard (rating, editions, work, status) tuple."""
        target_work = Work(
            work_id=work_id,
            title=title,
            author=author,
            first_publish_year=first_publish_year,
            edition_count=edition_count,
            editions=editions,
            isbn=isbn,
        )
        return ol_rating, editions, target_work, crawler_status

    def _prepare_google_books(self, c):
        volume_id = c["work_id"][len(c["prefix"]):]
        source = c["gb_source"] or self.get_source("google_books")
        gb_work = source.fetch_volume_by_id(volume_id)
        crawler_status = {"google_books": "Normal" if gb_work else "Volume not found"}

        resolved_title = c["title"]
        resolved_author = c["author"]
        resolved_isbn = None
        if gb_work:
            resolved_title = gb_work.title or c["title"] or "Unknown"
            resolved_author = gb_work.author or c["author"] or "Unknown"
            if gb_work.editions:
                resolved_isbn = gb_work.editions[0].isbn_13 or gb_work.editions[0].isbn_10

        ol_rating, editions = self._apply_ol_mapping(resolved_isbn, resolved_title, resolved_author, c["active_title_sources"])

        if not editions and gb_work and gb_work.editions:
            editions = gb_work.editions

        if not editions:
            editions = self._fallback_edition_list(
                volume_id,
                resolved_title,
                isbn=resolved_isbn,
                pub_year=str(gb_work.first_publish_year) if gb_work and gb_work.first_publish_year else None,
            )

        ol_rating, editions, target_work, crawler_status = self._finalize(
            ol_rating, editions, c["work_id"], resolved_title, resolved_author, crawler_status,
            isbn=resolved_isbn,
            first_publish_year=gb_work.first_publish_year if gb_work else None,
            edition_count=len(editions),
        )
        if gb_work and "Google Books" in gb_work.ratings:
            target_work.ratings["Google Books"] = gb_work.ratings["Google Books"]
        return ol_rating, editions, target_work, crawler_status

    def _prepare_douban_like(self, c, status_key):
        sub_id = c["work_id"][len(c["prefix"]):]
        details = self.get_source("douban").fetch_subject_details(sub_id)
        crawler_status = {status_key: "Normal" if details.get("isbn") else "Details not found"}
        resolved_isbn = details.get("isbn")
        resolved_title = details.get("title") or c["title"] or "Unknown"

        ol_rating, editions = self._apply_ol_mapping(resolved_isbn, resolved_title, c["author"], c["active_title_sources"])

        if not editions:
            editions = self._fallback_edition_list(
                sub_id, resolved_title, isbn=resolved_isbn, pub_year=details.get("pub_year")
            )

        return self._finalize(
            ol_rating, editions, c["work_id"], resolved_title, c["author"], crawler_status,
            isbn=resolved_isbn,
            edition_count=details.get("editions_count") or (len(editions) if editions else None),
        )

    def _prepare_douban(self, c):
        return self._prepare_douban_like(c, "douban")

    def _prepare_douban_api(self, c):
        """dbapi:<id> shares the numeric subject id space with douban, so
        resolve details through the douban adapter. Previously such ids fell
        into the Open Library branch producing invalid /works/dbapi:x ids."""
        return self._prepare_douban_like(c, "douban_api")

    def _prepare_goodreads(self, c):
        raw_id = c["work_id"][len(c["prefix"]):]
        is_work = raw_id.startswith("work/")
        if is_work:
            parts = raw_id.split("/")
            numeric_id = parts[1] if len(parts) > 1 else raw_id
        else:
            numeric_id = raw_id.split("/")[-1] if "/" in raw_id else raw_id

        resolved_title = c["title"]
        resolved_author = c["author"]
        resolved_isbn = None
        pub_year = None
        gr_editions = []
        details = {}

        goodreads_source = self.get_source("goodreads")
        if is_work:
            gr_editions = goodreads_source.fetch_editions(numeric_id, limit=self.DEFAULT_EDITION_LIMIT)
            crawler_status = {"goodreads": "Normal" if gr_editions else "No editions found"}
            if gr_editions:
                first_isbn_ed = next((ed for ed in gr_editions if ed.isbn_13 or ed.isbn_10), gr_editions[0])
                resolved_isbn = first_isbn_ed.isbn_13 or first_isbn_ed.isbn_10
                pub_year = first_isbn_ed.publish_year
                if not resolved_title:
                    resolved_title = first_isbn_ed.title
        else:
            details = goodreads_source.fetch_book_details(numeric_id)
            crawler_status = {"goodreads": details.get("crawler_status") or "Normal"}
            resolved_isbn = details.get("isbn")
            pub_year = details.get("pub_year")
            if details.get("title") and not resolved_title:
                resolved_title = details.get("title")
            if details.get("author") and not resolved_author:
                resolved_author = details.get("author")

        ol_rating, ol_editions = self._apply_ol_mapping(resolved_isbn, resolved_title, resolved_author, c["active_title_sources"])

        if ol_editions:
            editions = ol_editions
        else:
            if is_work:
                editions = gr_editions
            else:
                gr_work_id = details.get("work_id")
                if gr_work_id:
                    editions = goodreads_source.fetch_editions(gr_work_id, limit=self.DEFAULT_EDITION_LIMIT)
                else:
                    editions = []

        if not editions:
            editions = self._fallback_edition_list(
                numeric_id, resolved_title or "Unknown", isbn=resolved_isbn, pub_year=pub_year
            )

        return self._finalize(
            ol_rating, editions, c["work_id"], resolved_title, resolved_author, crawler_status,
            isbn=resolved_isbn,
            edition_count=details.get("editions_count") or (len(editions) if editions else None),
        )

    def _prepare_storygraph(self, c):
        book_id = c["work_id"][len(c["prefix"]):]
        details = self.get_source("storygraph").fetch_book_details(book_id)
        crawler_status = {"storygraph": details.get("crawler_status") or "Normal"}
        resolved_isbn = details.get("isbn")
        resolved_title = c["title"]
        resolved_author = c["author"]

        if details.get("title") and not resolved_title:
            resolved_title = details.get("title")
        if details.get("author") and not resolved_author:
            resolved_author = details.get("author")

        ol_rating, editions = self._apply_ol_mapping(resolved_isbn, resolved_title, resolved_author, c["active_title_sources"])

        if not editions:
            editions = self._fallback_edition_list(
                book_id, resolved_title or "Unknown", isbn=resolved_isbn, pub_year=details.get("pub_year")
            )

        return self._finalize(
            ol_rating, editions, c["work_id"], resolved_title, resolved_author, crawler_status,
            isbn=resolved_isbn,
            edition_count=details.get("editions_count") or (len(editions) if editions else None),
        )

    def _prepare_generic_prefixed(self, c):
        prefix = c["prefix"]
        book_id = c["work_id"][len(prefix):]
        crawler_status = {prefix[:-1]: "Normal"}
        ol_rating, editions = self._apply_ol_mapping(None, c["title"], c["author"], c["active_title_sources"])

        if not editions:
            editions = self._fallback_edition_list(book_id, c["title"] or "Unknown")

        return self._finalize(ol_rating, editions, c["work_id"], c["title"], c["author"], crawler_status)

    def _prepare_open_library(self, c):
        work_id = c["work_id"]
        full_work_id = work_id if work_id.startswith("/works/") else f"/works/{work_id}"
        crawler_status = {"open_library": "Normal"}
        resolved_isbn = None

        ol_source = self.get_source("open_library")
        if "open_library" in c["active_title_sources"]:
            ol_rating = ol_source.fetch_ratings(Work(work_id=full_work_id, title="", author=""))
        else:
            ol_rating = SourceRating(source_name="Open Library")

        editions = ol_source.fetch_editions(full_work_id, limit=self.DEFAULT_EDITION_LIMIT)
        if editions:
            for ed in editions:
                if ed.isbn_13 or ed.isbn_10:
                    resolved_isbn = ed.isbn_13 or ed.isbn_10
                    break

        return self._finalize(
            ol_rating, editions, full_work_id, c["title"], c["author"], crawler_status,
            isbn=resolved_isbn,
        )
