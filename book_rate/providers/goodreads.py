import logging
import re
from typing import List, Optional

from book_rate.models import Work, Edition, PlatformRating
from book_rate.providers.base import BaseProvider
from book_rate.utils.isbn import clean_isbn

logger = logging.getLogger(__name__)


class GoodreadsProvider(BaseProvider):
    """Provider for querying Goodreads ratings and books."""

    AUTOCOMPLETE_URL = "https://www.goodreads.com/book/auto_complete"
    BOOK_SHOW_URL = "https://www.goodreads.com/book/show/{book_id}"

    @property
    def name(self) -> str:
        return "Goodreads"

    def fetch_book_details(self, book_url_or_id: str) -> dict:
        """Fetch book detail HTML page from Goodreads and extract ISBN and pub_year."""
        url = book_url_or_id if book_url_or_id.startswith("http") else self.BOOK_SHOW_URL.format(book_id=book_url_or_id)
        res = {"isbn": None, "pub_year": None, "url": url}
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            html_str = resp.text

            isbn13_m = re.search(r'"isbn13":"(\d+)"', html_str) or re.search(r'ISBN13:\s*(\d+)', html_str) or re.search(r'978\d{10}', html_str)
            pub_m = re.search(r'first published\s+([A-Za-z]+\s+\d{1,2},\s*)?(\d{4})', html_str, re.IGNORECASE) or re.search(r'published\s+([A-Za-z]+\s+\d{1,2},\s*)?(\d{4})', html_str, re.IGNORECASE)

            if isbn13_m:
                raw_isbn = isbn13_m.group(1) if isbn13_m.groups() and isbn13_m.group(1) else isbn13_m.group(0)
                res["isbn"] = clean_isbn(raw_isbn)

            if pub_m:
                res["pub_year"] = pub_m.group(2) if len(pub_m.groups()) >= 2 and pub_m.group(2) else pub_m.group(1)

            return res
        except Exception as e:
            logger.warning(f"Failed to fetch Goodreads book details from '{url}': {e}")
            return res

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
        """Fetch Goodreads rating for a Work using base fallback strategy."""
        return self._fetch_ratings_with_fallback(work)
