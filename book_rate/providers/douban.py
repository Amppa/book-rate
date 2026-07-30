import logging
import re
from typing import List, Optional
import requests

from book_rate.models import Work, Edition, PlatformRating
from book_rate.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class DoubanProvider(BaseProvider):
    """Provider for querying Douban (豆瓣) ratings and book subjects."""

    SUGGEST_URL = "https://book.douban.com/j/subject_suggest"

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
        return "Douban"

    def _fetch_subject_rating(self, subject_url: str) -> tuple[Optional[float], Optional[int]]:
        """Fetch subject detail HTML page from Douban and extract rating and votes count."""
        try:
            resp = self.session.get(subject_url, timeout=self.timeout)
            resp.raise_for_status()
            html = resp.text

            rate_match = re.search(r'property="v:average">\s*([\d\.]+)\s*</', html)
            votes_match = re.search(r'property="v:votes">\s*(\d+)\s*</', html)

            rate: Optional[float] = None
            if rate_match:
                try:
                    r_val = float(rate_match.group(1))
                    if r_val > 0:
                        rate = r_val
                except ValueError:
                    pass

            votes: Optional[int] = None
            if votes_match:
                try:
                    v_val = int(votes_match.group(1))
                    if v_val > 0:
                        votes = v_val
                except ValueError:
                    pass

            return rate, votes
        except Exception as e:
            logger.warning(f"Failed to fetch Douban subject details from '{subject_url}': {e}")
            return None, None

    def search_works(self, query: str, limit: int = 5, page: int = 1) -> List[Work]:
        """Search Douban subject suggest endpoint for query."""
        clean_query = query.strip()
        if not clean_query:
            return []

        try:
            resp = self.session.get(
                self.SUGGEST_URL,
                params={"q": clean_query},
                timeout=self.timeout
            )
            resp.raise_for_status()
            items = resp.json()
        except Exception as e:
            logger.warning(f"Douban search failed for '{query}': {e}")
            return []

        if not isinstance(items, list):
            return []

        works: List[Work] = []
        for item in items[:limit]:
            if not isinstance(item, dict):
                continue

            sub_id = str(item.get("id", ""))
            title = item.get("title", "Unknown Title")
            author_name = item.get("author_name", "Unknown Author")
            pub_year_str = item.get("year", "")
            pub_year: Optional[int] = None
            if pub_year_str and pub_year_str.isdigit():
                pub_year = int(pub_year_str)

            subject_url = item.get("url") or f"https://book.douban.com/subject/{sub_id}/"

            avg_rating, ratings_count = self._fetch_subject_rating(subject_url)

            work = Work(
                work_id=f"db:{sub_id}" if sub_id else f"db:{title}",
                title=title,
                author=author_name,
                first_publish_year=pub_year,
                edition_count=1
            )

            if avg_rating is not None or ratings_count is not None:
                work.ratings[self.name] = PlatformRating(
                    platform_name=self.name,
                    rate=avg_rating,
                    rating_count=ratings_count,
                    url=subject_url,
                    title=title
                )

            edition = Edition(
                edition_id=sub_id or "1",
                title=title,
                publish_year=pub_year_str
            )
            work.editions.append(edition)
            works.append(work)

        return works

    def fetch_ratings(self, work: Work) -> PlatformRating:
        """Fetch Douban rating for a given Work by ISBN or title/author."""
        if self.name in work.ratings:
            return work.ratings[self.name]

        # 1. Search by ISBN if available
        for ed in work.editions:
            isbn = ed.isbn_13 or ed.isbn_10
            if isbn:
                try:
                    db_works = self.search_works(isbn, limit=1)
                    if db_works and self.name in db_works[0].ratings:
                        return db_works[0].ratings[self.name]
                except Exception as e:
                    logger.debug(f"Douban rating query failed for ISBN {isbn}: {e}")

        # 2. Search by title (and author)
        if work.title:
            query = work.title
            if work.author and work.author not in ["Unknown Author", "Unknown"]:
                query += f" {work.author}"
            try:
                db_works = self.search_works(query, limit=1)
                if db_works and self.name in db_works[0].ratings:
                    return db_works[0].ratings[self.name]
            except Exception as e:
                logger.debug(f"Douban rating query failed for title '{query}': {e}")

        return PlatformRating(platform_name=self.name)
