import logging
import re
from typing import List, Optional, Callable
from book_rate.models import Work, PlatformRating
from book_rate.utils.isbn import clean_isbn, extract_isbns_from_work

logger = logging.getLogger(__name__)


class BaseProvider:
    """Base abstract class for all book rating providers."""

    DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        import requests
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.DEFAULT_USER_AGENT
        })

    @property
    def name(self) -> str:
        """Name of the platform provider (e.g. 'Open Library')."""
        raise NotImplementedError

    def search_works(self, query: str, limit: int = 5, page: int = 1) -> List[Work]:
        """Search for works matching query string."""
        raise NotImplementedError

    def fetch_ratings(self, work: Work) -> PlatformRating:
        """Fetch rating metrics for a given Work object."""
        raise NotImplementedError

    def _select_best_rating(self, works: List[Work], target_title: Optional[str] = None) -> Optional[PlatformRating]:
        """Helper to select the work rating with highest rating count that is relevant to target_title."""
        if not works:
            return None

        target_words = set()
        if target_title:
            target_words = set(w.lower() for w in re.findall(r'\b[a-zA-Z0-9\u4e00-\u9fa5]{3,}\b', target_title))

        valid_works = []
        for w in works:
            t_lower = w.title.lower()
            if any(k in t_lower for k in ["summary of", "workbook for", "study guide for", "collection set"]):
                continue

            # Check title relevance if target_title is provided
            if target_words:
                cand_words = set(cw.lower() for cw in re.findall(r'\b[a-zA-Z0-9\u4e00-\u9fa5]{3,}\b', t_lower))
                if not (target_words & cand_words):
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
          Phase 2: Primary ISBN & Title/Author search
          Phase 3: Fallback Edition ISBNs if no candidates found
        """
        # Phase 1: Existing rating check
        if self.name in work.ratings and work.ratings[self.name].rate is not None:
            return work.ratings[self.name]

        search = custom_search or (lambda q: self.search_works(q, limit=5))

        target_title = work.original_title or work.title
        candidate_works: List[Work] = []

        # 1. Primary work ISBN search (if work has a direct primary ISBN)
        if hasattr(work, "isbn") and work.isbn:
            clean_primary = clean_isbn(work.isbn)
            if clean_primary:
                try:
                    candidate_works.extend(search(clean_primary))
                except Exception as e:
                    logger.debug(f"[{self.name}] Rating query failed for primary ISBN {clean_primary}: {e}")

        # 2. Title search (original_title / title)
        titles_to_try = [t for t in [work.original_title, work.title] if t]
        for title in titles_to_try:
            try:
                candidate_works.extend(search(title))
            except Exception as e:
                logger.debug(f"[{self.name}] Rating query failed for title '{title}': {e}")

        # 3. Title + Author search
        if work.author and work.author not in ["Unknown Author", "Unknown"]:
            clean_author = work.author.split(",")[0].strip()
            for title in titles_to_try:
                query = f"{title} {clean_author}".strip()
                try:
                    candidate_works.extend(search(query))
                except Exception as e:
                    logger.debug(f"[{self.name}] Rating query failed for query '{query}': {e}")

        # 4. Fallback to edition ISBNs if no candidates were found
        if not candidate_works:
            isbns = extract_isbns_from_work(work)
            for isbn in isbns[:5]:
                try:
                    candidate_works.extend(search(isbn))
                except Exception as e:
                    logger.debug(f"[{self.name}] Rating query failed for edition ISBN {isbn}: {e}")

        best_rating = self._select_best_rating(candidate_works, target_title=target_title)
        if best_rating and (best_rating.rate is not None or best_rating.rating_count is not None):
            return best_rating

        return PlatformRating(platform_name=self.name, url=None)
