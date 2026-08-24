import logging
from typing import List, Optional, Tuple, Any

from book_rate.models import Work, Edition, SourceRating
from book_rate.registry import SourceRegistry

logger = logging.getLogger(__name__)


class WorkPreparer:
    """
    Handles resolving target Work metadata without synchronous network requests.
    Zero-I/O memory construction supporting both Quick Mode and Wizard Mode.
    """

    def __init__(self, registry: Optional[SourceRegistry] = None, source_instances: Optional[dict] = None):
        self.registry = registry or SourceRegistry()
        self.source_instances = source_instances or {}

    def get_source(self, key: str, google_key: Optional[str] = None):
        if key == "google_books" and google_key:
            return self.registry.create_source("google_books", api_key=google_key)
        if key in self.source_instances:
            return self.source_instances[key]
        return self.registry.create_source(key)

    @staticmethod
    def _finalize(ol_rating: SourceRating, editions: List[Edition], work_id: str, title: str, author: str,
                  crawler_status: dict, isbn: Optional[str] = None, first_publish_year: Optional[int] = None,
                  edition_count: Optional[int] = None) -> Tuple[SourceRating, List[Edition], Work, dict]:
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

    def resolve_work_editions_and_ol_rating(
        self,
        work_id: str,
        title: str,
        author: str,
        active_title_sources: list,
        gb_source: Optional[Any] = None,
        google_key: Optional[str] = None
    ) -> Tuple[SourceRating, List[Edition], Work, dict]:
        """
        Fast zero-I/O memory preparation of target Work.
        Dispatches platform prefix to assign clean crawler_status and normalized work_id.
        """
        prefix, s_key = SourceRegistry.match_id_prefix(work_id)

        if s_key:
            crawler_status = {s_key: "Normal"}
            full_work_id = work_id
        elif work_id.startswith("custom:"):
            crawler_status = {"custom": "Normal"}
            full_work_id = work_id
        else:
            crawler_status = {"open_library": "Normal"}
            full_work_id = work_id if work_id.startswith("/works/") else f"/works/{work_id}"

        ol_rating = SourceRating(source_name="Open Library")
        return self._finalize(
            ol_rating, [], full_work_id, title or "", author or "", crawler_status
        )
