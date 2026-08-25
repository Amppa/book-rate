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
        Search candidate works across requested active_title_sources.
        """
        clean_q = q.strip()
        if not clean_q or not active_title_sources:
            return []

        works: List[Work] = []
        for s_key in active_title_sources:
            source_inst = self.get_source(s_key, google_key=google_key if s_key == "google_books" else None)
            if source_inst:
                try:
                    if s_key == "open_library":
                        res = source_inst.search_works(clean_q, limit=10, page=page, include_details=False)
                    else:
                        res = source_inst.search_works(clean_q, limit=10, page=page)
                    if res:
                        works.extend(res)
                except Exception as e:
                    logger.warning(f"Failed to search works on '{s_key}': {e}")

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

        prefix, s_key = SourceRegistry.match_id_prefix(work_id)
        if s_key:
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

