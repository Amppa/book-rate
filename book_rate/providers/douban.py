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
    ISBN_LOOKUP_URL = "https://book.douban.com/isbn/{isbn}/"

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

    def fetch_subject_details(self, subject_url_or_id: str) -> dict:
        """Fetch subject detail HTML page from Douban and extract rating, votes count, ISBN, pub_year, and title."""
        url = subject_url_or_id if subject_url_or_id.startswith("http") else f"https://book.douban.com/subject/{subject_url_or_id}/"
        res = {"rate": None, "votes": None, "isbn": None, "pub_year": None, "title": None, "url": url}
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            html = resp.text

            rate_match = re.search(r'property="v:average">\s*([\d\.]+)\s*</', html)
            votes_match = re.search(r'property="v:votes">\s*(\d+)\s*</', html)
            title_match = re.search(r'<span property="v:itemreviewed">(.*?)</span>', html)
            isbn_match = re.search(r'ISBN:</span>\s*([\d-]+)', html)
            pub_match = re.search(r'出版年:</span>\s*([^\n<]+)', html)

            if rate_match:
                try:
                    r_val = float(rate_match.group(1))
                    if r_val > 0:
                        res["rate"] = r_val
                except ValueError:
                    pass

            if votes_match:
                try:
                    v_val = int(votes_match.group(1))
                    if v_val > 0:
                        res["votes"] = v_val
                except ValueError:
                    pass

            if title_match:
                res["title"] = title_match.group(1).strip()

            if isbn_match:
                res["isbn"] = re.sub(r"[-\s]", "", isbn_match.group(1))

            if pub_match:
                py_clean = pub_match.group(1).strip()
                # Extract 4-digit year if present e.g. '2012-7' -> '2012'
                ym = re.search(r'\b(19\d\d|20\d\d)\b', py_clean)
                res["pub_year"] = ym.group(1) if ym else py_clean

            return res
        except Exception as e:
            logger.warning(f"Failed to fetch Douban subject details from '{url}': {e}")
            return res

    def _fetch_subject_rating(self, subject_url: str) -> tuple[Optional[float], Optional[int]]:
        """Fetch subject detail HTML page from Douban and extract rating and votes count."""
        details = self.fetch_subject_details(subject_url)
        return details["rate"], details["votes"]

    def _lookup_by_isbn(self, isbn: str) -> Optional[PlatformRating]:
        """
        Lookup a Douban subject by ISBN using the /isbn/{isbn}/ redirect endpoint.
        Supports all ISBNs including non-Chinese editions.
        Returns a PlatformRating if the subject is found, else None.
        """
        isbn_clean = re.sub(r"[-\s]", "", isbn)
        if not re.match(r"^\d{10}(\d{3})?$", isbn_clean):
            return None

        url = self.ISBN_LOOKUP_URL.format(isbn=isbn_clean)
        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            # Douban returns 404 or stays on /isbn/ if not found
            subject_match = re.search(r"book\.douban\.com/subject/(\d+)/?", resp.url)
            if not subject_match:
                logger.debug(f"Douban ISBN lookup: no subject found for ISBN {isbn_clean} (url={resp.url})")
                return None

            sub_id = subject_match.group(1)
            subject_url = f"https://book.douban.com/subject/{sub_id}/"
            rate, votes = self._fetch_subject_rating(subject_url)

            # Extract title from HTML
            title_match = re.search(r'<span property="v:itemreviewed">(.*?)</span>', resp.text)
            title = title_match.group(1).strip() if title_match else None

            return PlatformRating(
                platform_name=self.name,
                rate=rate,
                rating_count=votes,
                url=subject_url,
                title=title
            )
        except Exception as e:
            logger.debug(f"Douban ISBN lookup failed for '{isbn_clean}': {e}")
            return None

    def search_works(self, query: str, limit: int = 5, page: int = 1) -> List[Work]:
        """Search Douban for books by query string or ISBN."""
        clean_query = query.strip()
        if not clean_query:
            return []

        # Detect ISBN query (10 or 13 digits, optionally with dashes)
        isbn_clean = re.sub(r"[-\s]", "", clean_query)
        if re.match(r"^\d{10}(\d{3})?$", isbn_clean):
            rating = self._lookup_by_isbn(isbn_clean)
            if rating and rating.url:
                sub_match = re.search(r"/subject/(\d+)/", rating.url)
                sub_id = sub_match.group(1) if sub_match else isbn_clean
                work = Work(
                    work_id=f"db:{sub_id}",
                    title=rating.title or clean_query,
                    author="",
                    edition_count=1
                )
                work.ratings[self.name] = rating
                edition = Edition(edition_id=sub_id, title=rating.title or clean_query)
                work.editions.append(edition)
                return [work]
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

            # Only include book results (type="b"); skip authors (type="a") and others
            if item.get("type") != "b":
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

    def _try_search_rating(self, query: str) -> Optional[PlatformRating]:
        """Helper to execute search_works for a query and extract PlatformRating if found."""
        try:
            db_works = self.search_works(query, limit=3)
            if db_works:
                rating = db_works[0].ratings.get(self.name)
                if rating and rating.url:
                    return rating
                sub_id = db_works[0].work_id.replace("db:", "")
                subject_url = f"https://book.douban.com/subject/{sub_id}/" if sub_id else None
                return PlatformRating(
                    platform_name=self.name,
                    url=subject_url,
                    title=db_works[0].title
                )
        except Exception as e:
            logger.debug(f"Douban rating query failed for '{query}': {e}")
        return None

    def fetch_ratings(self, work: Work) -> PlatformRating:
        """
        Fetch Douban rating for a given Work.
        Strategy (in order):
          1. original_title search (finds the most-rated version, usually simplified Chinese)
          2. title search
          3. title + author search
          4. ISBN lookup as last fallback
        """
        if self.name in work.ratings:
            return work.ratings[self.name]

        titles_to_try = [t for t in [work.original_title, work.title] if t]

        # 1. Search by original_title / title
        for title in titles_to_try:
            rating = self._try_search_rating(title)
            if rating:
                return rating

        # 2. Search by title + author
        if work.author and work.author not in ["Unknown Author", "Unknown"]:
            clean_author = work.author.split(",")[0].strip()
            for title in titles_to_try:
                rating = self._try_search_rating(f"{title} {clean_author}")
                if rating:
                    return rating

        # 3. ISBN lookup as last fallback
        for ed in work.editions:
            isbn = ed.isbn_13 or ed.isbn_10
            if isbn:
                try:
                    rating = self._lookup_by_isbn(isbn)
                    if rating:
                        return rating
                except Exception as e:
                    logger.debug(f"Douban ISBN lookup failed for {isbn}: {e}")

        return PlatformRating(platform_name=self.name, url=None)
