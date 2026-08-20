import logging
from typing import List, Optional, Tuple

from book_rate.models import Work, Edition, SourceRating
from book_rate.registry import SourceRegistry

logger = logging.getLogger(__name__)


class WorkResolver:
    """
    Handles candidate Work discovery across title sources without cross-platform fallbacks.
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


    def search_works(
        self,
        q: str,
        page: int = 1,
        active_title_sources: Optional[List[str]] = None,
        google_key: Optional[str] = None
    ) -> List[Work]:
        """
        Search candidate works across active_title_sources in strict priority order.
        No hidden fallbacks to inactive platforms.
        """
        clean_q = q.strip()
        if not clean_q:
            return []

        if active_title_sources is None:
            active_title_sources = []

        works: List[Work] = []

        if "open_library" in active_title_sources:
            ol_source = self.get_source("open_library")
            if ol_source:
                works = ol_source.search_works(clean_q, limit=10, page=page, include_details=False)

        if "google_books" in active_title_sources:
            gb_source = self.get_source("google_books", google_key=google_key)
            if gb_source:
                if "open_library" not in active_title_sources:
                    gb_works = gb_source.search_works(clean_q, limit=10, page=page)
                elif page == 1:
                    gb_works = gb_source.search_works(clean_q, limit=10, page=1)
                else:
                    gb_works = []
                works.extend(gb_works)

        if not works and "open_library" not in active_title_sources and "google_books" not in active_title_sources:
            for s_key in self.registry.get_title_source_keys():
                if s_key in active_title_sources:
                    source_inst = self.get_source(s_key)
                    if source_inst:
                        extra_works = source_inst.search_works(clean_q, limit=10, page=page)
                        if extra_works:
                            works.extend(extra_works)
                            break

        return works


class EditionResolver:
    """
    Handles resolving published Edition records for a target Work.
    """

    def __init__(self, registry: Optional[SourceRegistry] = None, source_instances: Optional[dict] = None):
        self.registry = registry or SourceRegistry()
        self.source_instances = source_instances or {}

    def get_source(self, key: str):
        if key in self.source_instances:
            return self.source_instances[key]
        return self.registry.create_source(key)

    def resolve_source_and_id(self, work_id: str) -> Tuple[Optional[str], str, int]:
        """Resolve platform source key, formatted ID, and default edition limit from work_id."""
        if not work_id:
            return None, "", 0

        prefix_map = {
            "gr:": "goodreads",
            "sg:": "storygraph",
            "db:": "douban",
            "dbapi:": "douban_api",
            "am:": "amazon",
            "amjp:": "amazon_jp",
            "rm:": "readmoo",
            "gb:": "google_books",
            "play:": "google_play",
            "bk:": "books_tw"
        }
        for prefix, s_key in prefix_map.items():
            if work_id.startswith(prefix):
                return s_key, work_id, 100

        if work_id.startswith(("/works/", "OL")) or ":" not in work_id:
            full_id = work_id if work_id.startswith("/works/") else f"/works/{work_id}"
            return "open_library", full_id, 500

        return None, work_id, 0

    def fetch_editions_for_work(self, work_id: str) -> List[Edition]:
        """Fetch published editions list for a work_id."""
        s_key, formatted_id, limit = self.resolve_source_and_id(work_id)
        if not s_key:
            return []

        source_inst = self.get_source(s_key)
        if not source_inst:
            return []

        try:
            return source_inst.fetch_editions(formatted_id, limit=limit)
        except Exception as e:
            logger.warning(f"Failed to fetch editions for '{work_id}' via '{s_key}': {e}")
            return []

