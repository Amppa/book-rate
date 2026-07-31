import logging
from abc import ABC, abstractmethod
from typing import List, Optional, Callable
import requests

from book_rate.models import Work, PlatformRating
from book_rate.utils.isbn import extract_isbns_from_work

logger = logging.getLogger(__name__)


class BaseProvider(ABC):
    """Base interface and common implementation for book score providers."""

    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.DEFAULT_USER_AGENT})

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name identifier."""
        pass

    @abstractmethod
    def search_works(self, query: str, limit: int = 5, page: int = 1) -> List[Work]:
        """Search for works matching the given query."""
        pass

    @abstractmethod
    def fetch_ratings(self, work: Work) -> PlatformRating:
        """Fetch rating data for a specific work."""
        pass

    def _select_best_rating(self, works: List[Work]) -> Optional[PlatformRating]:
        """Helper to select the work rating with highest rating count."""
        if not works:
            return None

        # Filter out obvious summaries/brochures
        valid_works = []
        for w in works:
            t_lower = w.title.lower()
            if any(k in t_lower for k in ["summary of", "workbook for", "study guide for", "collection set"]):
                continue
            valid_works.append(w)

        target_list = valid_works if valid_works else works
        best_work = max(
            target_list,
            key=lambda w: (
                w.ratings.get(self.name).rating_count or 0
                if (self.name in w.ratings and w.ratings[self.name].rating_count)
                else 0
            )
        )
        return best_work.ratings.get(self.name)

    def _fetch_ratings_with_fallback(
        self,
        work: Work,
        custom_search: Optional[Callable[[str], List[Work]]] = None
    ) -> PlatformRating:
        """
        Unified 4-phase rating resolution fallback strategy:
          Phase 1: Existing platform rating in work.ratings
          Phase 2: Search by ISBN(s)
          Phase 3: Search by Title (original_title / title)
          Phase 4: Search by Title + Author
        """
        # Phase 1: Existing rating check
        if self.name in work.ratings and work.ratings[self.name].rate is not None:
            return work.ratings[self.name]

        search = custom_search or (lambda q: self.search_works(q, limit=5))

        # Phase 2: ISBN lookup
        isbns = extract_isbns_from_work(work)
        for isbn in isbns:
            try:
                works = search(isbn)
                rating = self._select_best_rating(works)
                if rating and (rating.rate is not None or rating.rating_count is not None):
                    return rating
            except Exception as e:
                logger.debug(f"[{self.name}] Rating query failed for ISBN {isbn}: {e}")

        # Phase 3: Title search
        titles_to_try = [t for t in [work.original_title, work.title] if t]
        for title in titles_to_try:
            try:
                works = search(title)
                rating = self._select_best_rating(works)
                if rating and (rating.rate is not None or rating.rating_count is not None):
                    return rating
            except Exception as e:
                logger.debug(f"[{self.name}] Rating query failed for title '{title}': {e}")

        # Phase 4: Title + Author search
        if work.author and work.author not in ["Unknown Author", "Unknown"]:
            clean_author = work.author.split(",")[0].strip()
            for title in titles_to_try:
                query = f"{title} {clean_author}".strip()
                try:
                    works = search(query)
                    rating = self._select_best_rating(works)
                    if rating and (rating.rate is not None or rating.rating_count is not None):
                        return rating
                except Exception as e:
                    logger.debug(f"[{self.name}] Rating query failed for query '{query}': {e}")

        return PlatformRating(platform_name=self.name, url=None)
