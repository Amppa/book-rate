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

    def fetch_ratings(self, work: Work) -> PlatformRating:
        """Fetch Goodreads rating for a given Work by ISBN or title/author."""
        if self.name in work.ratings:
            return work.ratings[self.name]

        # 1. Search by ISBN if available
        for ed in work.editions:
            isbn = ed.isbn_13 or ed.isbn_10
            if isbn:
                try:
                    gr_works = self.search_works(isbn, limit=1)
                    if gr_works and self.name in gr_works[0].ratings:
                        return gr_works[0].ratings[self.name]
                except Exception as e:
                    logger.debug(f"Goodreads rating query failed for ISBN {isbn}: {e}")

        # 2. Try original_title or main title
        search_query = work.original_title or work.title
        if search_query:
            if work.author and work.author not in ["Unknown Author", "資料未提供"]:
                search_query += f" {work.author}"
            try:
                gr_works = self.search_works(search_query, limit=1)
                if gr_works and self.name in gr_works[0].ratings:
                    return gr_works[0].ratings[self.name]
            except Exception as e:
                logger.debug(f"Goodreads rating query failed for title '{search_query}': {e}")

        return PlatformRating(platform_name=self.name)
