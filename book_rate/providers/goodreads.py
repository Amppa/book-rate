import logging
import re
from typing import List, Optional
import requests

from book_rate.models import Work, Edition, PlatformRating
from book_rate.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class GoodreadsProvider(BaseProvider):
    """Provider for querying Goodreads ratings and books."""

    AUTOCOMPLETE_URL = "https://www.goodreads.com/book/auto_complete"

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        })

    @property
    def name(self) -> str:
        return "Goodreads"

    def search_works(self, query: str, limit: int = 5, page: int = 1) -> List[Work]:
        """Search Goodreads auto_complete endpoint for query."""
        clean_query = query.strip()
        if not clean_query:
            return []

        try:
            resp = self.session.get(
                self.AUTOCOMPLETE_URL,
                params={"q": clean_query},
                timeout=self.timeout
            )
            resp.raise_for_status()
            items = resp.json()
        except Exception as e:
            logger.warning(f"Goodreads search failed for '{query}': {e}")
            return []

        if not isinstance(items, list):
            return []

        works: List[Work] = []
        for item in items[:limit]:
            if not isinstance(item, dict):
                continue

            book_id = str(item.get("bookId", ""))
            title = item.get("title", item.get("bookTitleBare", "Unknown Title"))
            author_info = item.get("author", {})
            author_name = author_info.get("name", "Unknown Author") if isinstance(author_info, dict) else "Unknown Author"

            raw_rating = item.get("avgRating")
            avg_rating: Optional[float] = None
            if raw_rating is not None:
                try:
                    r_val = float(raw_rating)
                    if r_val > 0:
                        avg_rating = r_val
                except (ValueError, TypeError):
                    pass

            raw_count = item.get("ratingsCount")
            ratings_count: Optional[int] = None
            if raw_count is not None:
                try:
                    c_val = int(raw_count)
                    if c_val > 0:
                        ratings_count = c_val
                except (ValueError, TypeError):
                    pass

            book_url_rel = item.get("bookUrl", "")
            book_url = f"https://www.goodreads.com{book_url_rel}" if book_url_rel else None

            work = Work(
                work_id=f"gr:{book_id}" if book_id else f"gr:{title}",
                title=title,
                author=author_name,
                edition_count=1
            )

            if avg_rating is not None or ratings_count is not None:
                work.ratings[self.name] = PlatformRating(
                    platform_name=self.name,
                    rate=avg_rating,
                    rating_count=ratings_count,
                    url=book_url,
                    title=title
                )

            edition = Edition(
                edition_id=book_id or "1",
                title=title
            )
            work.editions.append(edition)
            works.append(work)

        return works

    def _select_best_rating(self, gr_works: List[Work]) -> Optional[PlatformRating]:
        """Select the best non-summary Goodreads rating with highest review count."""
        if not gr_works:
            return None

        # Filter out summary/workbook brochures
        valid_works = []
        for w in gr_works:
            t_lower = w.title.lower()
            if any(k in t_lower for k in ["summary", "workbook", "30 minute", "study guide", "collection set"]):
                continue
            valid_works.append(w)

        target_list = valid_works if valid_works else gr_works
        best_work = max(
            target_list,
            key=lambda w: (w.ratings.get(self.name).rating_count or 0) if (self.name in w.ratings and w.ratings[self.name].rating_count) else 0
        )
        return best_work.ratings.get(self.name)

    def fetch_ratings(self, work: Work) -> PlatformRating:
        """Fetch Goodreads rating for a given Work by ISBN or title/author."""
        if self.name in work.ratings and work.ratings[self.name].rate is not None:
            return work.ratings[self.name]

        # 1. Check if ISBN is present in work.editions or work_id
        isbns_to_check = []
        if work.work_id:
            raw_id = work.work_id.replace("gb:", "").replace("gr:", "").replace("db:", "").replace("/works/", "")
            if re.match(r'^\d{10,13}$', raw_id):
                isbns_to_check.append(raw_id)
            
        for ed in work.editions:
            isbn = ed.isbn_13 or ed.isbn_10
            if isbn and isbn not in isbns_to_check:
                isbns_to_check.append(isbn)

        for isbn in isbns_to_check:
            try:
                gr_works = self.search_works(isbn, limit=5)
                best_rating = self._select_best_rating(gr_works)
                if best_rating and (best_rating.rate is not None or best_rating.rating_count is not None):
                    return best_rating
            except Exception as e:
                logger.debug(f"Goodreads rating query failed for ISBN {isbn}: {e}")

        # 2. Try title search (first without author, as appending author to title can pollute search ranking)
        titles_to_try = [t for t in [work.original_title, work.title] if t]
        for title in titles_to_try:
            try:
                gr_works = self.search_works(title, limit=5)
                best_rating = self._select_best_rating(gr_works)
                if best_rating and (best_rating.rate is not None or best_rating.rating_count is not None):
                    return best_rating
            except Exception as e:
                logger.debug(f"Goodreads rating query failed for title '{title}': {e}")

        # 3. Fallback: Try title + author
        for title in titles_to_try:
            if work.author and work.author not in ["Unknown Author", "資料未提供"]:
                query = f"{title} {work.author}"
                try:
                    gr_works = self.search_works(query, limit=5)
                    best_rating = self._select_best_rating(gr_works)
                    if best_rating and (best_rating.rate is not None or best_rating.rating_count is not None):
                        return best_rating
                except Exception as e:
                    logger.debug(f"Goodreads rating query failed for query '{query}': {e}")

        return PlatformRating(platform_name=self.name)
