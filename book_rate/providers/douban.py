import html
import logging
import re
from typing import List, Optional

from book_rate.models import Work, Edition, PlatformRating
from book_rate.providers.base import BaseProvider
from book_rate.utils.isbn import clean_isbn

logger = logging.getLogger(__name__)


def _build_subject_url(sub_id: str) -> str:
    return f"https://book.douban.com/subject/{sub_id}/"


def _parse_subject_html(html_str: str, url: str) -> dict:
    """Parse Douban subject HTML page and extract rating, votes count, ISBN, pub_year, title, and editions_count."""
    res = {"rate": None, "votes": None, "isbn": None, "pub_year": None, "title": None, "url": url, "editions_count": None}
    if not html_str:
        return res

    rate_match = re.search(r'property="v:average">\s*([\d\.]+)\s*</', html_str)
    votes_match = re.search(r'property="v:votes">\s*(\d+)\s*</', html_str)
    title_match = re.search(r'<span property="v:itemreviewed">(.*?)</span>', html_str)
    isbn_match = re.search(r'ISBN:</span>\s*([\d-]+)', html_str)
    pub_match = re.search(r'出版年:</span>\s*([^\n<]+)', html_str)

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
        res["title"] = html.unescape(title_match.group(1).strip())

    if isbn_match:
        res["isbn"] = clean_isbn(isbn_match.group(1))

    if pub_match:
        py_clean = pub_match.group(1).strip()
        ym = re.search(r'\b(19\d\d|20\d\d)\b', py_clean)
        res["pub_year"] = ym.group(1) if ym else py_clean

    editions_match = re.search(r'这本书的其他版本.*?全部(\d+)', html_str, re.DOTALL)
    if editions_match:
        res["editions_count"] = int(editions_match.group(1))

    return res


class DoubanProvider(BaseProvider):
    """Provider for querying Douban (豆瓣) ratings and book subjects."""

    SUGGEST_URL = "https://book.douban.com/j/subject_suggest"
    ISBN_LOOKUP_URL = "https://book.douban.com/isbn/{isbn}/"

    @property
    def name(self) -> str:
        return "Douban"

    def fetch_subject_details(self, subject_url_or_id: str) -> dict:
        """Fetch subject detail HTML page from Douban and parse metadata."""
        url = subject_url_or_id if subject_url_or_id.startswith("http") else _build_subject_url(subject_url_or_id)
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            return _parse_subject_html(resp.text, url)
        except Exception as e:
            logger.warning(f"Failed to fetch Douban subject details from '{url}': {e}")
            return {"rate": None, "votes": None, "isbn": None, "pub_year": None, "title": None, "url": url, "editions_count": None}

    def _lookup_by_isbn(self, isbn: str) -> Optional[PlatformRating]:
        """
        Lookup a Douban subject by ISBN using /isbn/{isbn}/ redirect.
        Single HTTP GET request to avoid duplicate requests.
        """
        isbn_str = clean_isbn(isbn)
        if not isbn_str:
            return None

        url = self.ISBN_LOOKUP_URL.format(isbn=isbn_str)
        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            subject_match = re.search(r"book\.douban\.com/subject/(\d+)/?", resp.url)
            if not subject_match:
                logger.debug(f"Douban ISBN lookup: no subject found for ISBN {isbn_str}")
                return None

            sub_id = subject_match.group(1)
            subject_url = _build_subject_url(sub_id)
            details = _parse_subject_html(resp.text, subject_url)

            rating = PlatformRating(
                platform_name=self.name,
                rate=details["rate"],
                rating_count=details["votes"],
                url=subject_url,
                title=details["title"]
            )
            rating.editions_count = details.get("editions_count")
            return rating
        except Exception as e:
            logger.debug(f"Douban ISBN lookup failed for '{isbn_str}': {e}")
            return None

    def search_works(self, query: str, limit: int = 5, page: int = 1) -> List[Work]:
        """Search Douban for books by query string or ISBN."""
        clean_query = query.strip()
        if not clean_query:
            return []

        isbn_str = clean_isbn(clean_query)
        if isbn_str:
            rating = self._lookup_by_isbn(isbn_str)
            if rating and rating.url:
                sub_match = re.search(r"/subject/(\d+)/", rating.url)
                sub_id = sub_match.group(1) if sub_match else isbn_str
                work = Work(
                    work_id=f"db:{sub_id}",
                    title=rating.title or clean_query,
                    author="",
                    edition_count=getattr(rating, "editions_count", None)
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
            if not isinstance(item, dict) or (item.get("type") and item.get("type") != "b"):
                continue

            sub_id = str(item.get("id", ""))
            title = item.get("title", "Unknown Title")
            author_name = item.get("author_name", "Unknown Author")
            pub_year_str = item.get("year", "")
            pub_year: Optional[int] = int(pub_year_str) if pub_year_str and pub_year_str.isdigit() else None
            subject_url = item.get("url") or _build_subject_url(sub_id)

            details = self.fetch_subject_details(subject_url)

            work = Work(
                work_id=f"db:{sub_id}" if sub_id else f"db:{title}",
                title=title,
                author=author_name,
                first_publish_year=pub_year,
                edition_count=details.get("editions_count")
            )

            if details["rate"] is not None or details["votes"] is not None or subject_url:
                work.ratings[self.name] = PlatformRating(
                    platform_name=self.name,
                    rate=details["rate"],
                    rating_count=details["votes"],
                    url=subject_url,
                    title=title
                )

            edition = Edition(edition_id=sub_id or "1", title=title, publish_year=pub_year_str)
            work.editions.append(edition)
            works.append(work)

        return works

    @property
    def default_strategy(self) -> str:
        return "isbn_primary"

    def fetch_ratings(self, work: Work, strategy: Optional[str] = None) -> PlatformRating:
        """Fetch Douban rating for a Work using explicit SearchStrategy."""
        return self._fetch_ratings(work, strategy=strategy)
