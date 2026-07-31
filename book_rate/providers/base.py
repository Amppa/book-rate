import logging
import re
from typing import List, Optional, Callable
from book_rate.models import Work, PlatformRating
from book_rate.utils.isbn import clean_isbn, extract_isbns_from_work

logger = logging.getLogger(__name__)


class SearchStrategy:
    ISBN_PRIMARY = "isbn_primary"
    ISBN_ALL = "isbn_all"
    TITLE = "title"
    TITLE_AUTHOR = "title_author"
    TITLE_AUTHOR_YEAR = "title_author_year"
    PROVIDER_ID = "provider_id"


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

    @property
    def default_strategy(self) -> str:
        """Default search strategy for this provider."""
        return SearchStrategy.TITLE_AUTHOR

    def search_works(self, query: str, limit: int = 5, page: int = 1) -> List[Work]:
        """Search for works matching query string."""
        raise NotImplementedError

    def fetch_ratings(self, work: Work, strategy: Optional[str] = None) -> PlatformRating:
        """Fetch rating metrics for a given Work object with explicit strategy."""
        return self._fetch_ratings(work, strategy=strategy)

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

    def _fetch_ratings(
        self,
        work: Work,
        strategy: Optional[str] = None,
        custom_search: Optional[Callable[[str], List[Work]]] = None
    ) -> PlatformRating:
        """
        Execute explicit SearchStrategy for the given Work object.
        No silent fallback.
        """
        strat = strategy or self.default_strategy
        search = custom_search or (lambda q: self.search_works(q, limit=5))
        target_title = work.original_title or work.title

        candidate_works: List[Work] = []
        query_used = ""

        primary_isbn = getattr(work, "isbn", None)
        if not primary_isbn and work.editions:
            for ed in work.editions:
                if ed.isbn_13 or ed.isbn_10:
                    primary_isbn = ed.isbn_13 or ed.isbn_10
                    break
        cleaned = clean_isbn(primary_isbn) if primary_isbn else None

        if strat == SearchStrategy.ISBN_PRIMARY and not cleaned and strategy is None:
            strat = SearchStrategy.TITLE_AUTHOR

        if strat == SearchStrategy.ISBN_PRIMARY:
            if cleaned:
                query_used = cleaned
                try:
                    candidate_works.extend(search(cleaned))
                except Exception as e:
                    logger.debug(f"[{self.name}] Query failed for primary ISBN {cleaned}: {e}")

        elif strat == SearchStrategy.ISBN_ALL:
            isbns = extract_isbns_from_work(work)
            if isbns:
                query_used = ", ".join(isbns[:5])
                for isbn in isbns[:5]:
                    try:
                        candidate_works.extend(search(isbn))
                    except Exception as e:
                        logger.debug(f"[{self.name}] Query failed for edition ISBN {isbn}: {e}")

        elif strat == SearchStrategy.TITLE:
            query_used = target_title or ""
            if query_used:
                try:
                    candidate_works.extend(search(query_used))
                except Exception as e:
                    logger.debug(f"[{self.name}] Query failed for title '{query_used}': {e}")

        elif strat == SearchStrategy.TITLE_AUTHOR:
            clean_author = ""
            if work.author and work.author not in ["Unknown Author", "Unknown"]:
                clean_author = work.author.split(",")[0].strip()
            query_used = f"{target_title} {clean_author}".strip()
            if query_used:
                try:
                    candidate_works.extend(search(query_used))
                except Exception as e:
                    logger.debug(f"[{self.name}] Query failed for query '{query_used}': {e}")

        elif strat == SearchStrategy.TITLE_AUTHOR_YEAR:
            clean_author = ""
            if work.author and work.author not in ["Unknown Author", "Unknown"]:
                clean_author = work.author.split(",")[0].strip()
            pub_year = work.first_publish_year
            if not pub_year and work.editions:
                for ed in work.editions:
                    if ed.publish_year:
                        year_match = re.search(r'\b\d{4}\b', str(ed.publish_year))
                        if year_match:
                            pub_year = year_match.group(0)
                            break
            year_str = str(pub_year) if pub_year else ""
            query_used = f"{target_title} {clean_author} {year_str}".strip()
            if query_used:
                try:
                    candidate_works.extend(search(query_used))
                except Exception as e:
                    logger.debug(f"[{self.name}] Query failed for query '{query_used}': {e}")

        elif strat == SearchStrategy.PROVIDER_ID:
            query_used = work.work_id
            if self.name in work.ratings and work.ratings[self.name].rate is not None:
                r = work.ratings[self.name]
                r.strategy = strat
                r.query = query_used
                r.status = "MATCH"
                return r

            # Handle provider ID search if prefix matches
            prefix_map = {
                "Goodreads": "gr:",
                "Google Books": "gb:",
                "豆瓣": "db:",
                "Amazon JP": "amjp:",
                "Amazon": "am:",
                "StoryGraph": "sg:",
                "Open Library": "/works/"
            }
            p_prefix = prefix_map.get(self.name, "")
            if p_prefix and (work.work_id.startswith(p_prefix) or (p_prefix == "/works/" and "OL" in work.work_id)):
                try:
                    candidate_works.extend(search(work.work_id))
                except Exception as e:
                    logger.debug(f"[{self.name}] Query failed for provider ID '{work.work_id}': {e}")

        best_rating = self._select_best_rating(candidate_works, target_title=target_title)
        if best_rating and (best_rating.rate is not None or best_rating.rating_count is not None or best_rating.url):
            best_rating.strategy = strat
            best_rating.query = query_used
            best_rating.status = "MATCH" if (best_rating.rate is not None or best_rating.rating_count is not None) else "NO_MATCH"
            return best_rating

        return PlatformRating(
            platform_name=self.name,
            url=None,
            strategy=strat,
            query=query_used,
            status="NO_MATCH"
        )

