import html
import json
import logging
import re
import urllib.parse
from typing import List, Optional

from book_rate.models import Work, Edition, SourceRating
from book_rate.sources.base import BaseSource
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
        res["pub_year"] = pub_match.group(1).strip()


    editions_match = re.search(r'这本书的其他版本.*?全部(\d+)', html_str, re.DOTALL)
    if editions_match:
        res["editions_count"] = int(editions_match.group(1))

    return res


class DoubanSource(BaseSource):
    """Source for querying Douban (豆瓣) ratings and book subjects."""

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

    def _lookup_by_isbn(self, isbn: str) -> Optional[SourceRating]:
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
            subject_match = None
            if resp.url and isinstance(resp.url, str):
                subject_match = re.search(r"book\.douban\.com/subject/(\d+)/?", resp.url)
            if not subject_match:
                logger.debug(f"Douban ISBN lookup: no subject found for ISBN {isbn_str}")
                return None

            sub_id = subject_match.group(1)
            subject_url = _build_subject_url(sub_id)
            details = _parse_subject_html(resp.text, subject_url)

            rating = SourceRating(
                source_name=self.name,
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

    def _search_works_suggest(self, query: str, limit: int = 5, page: int = 1) -> List[Work]:
        """Fallback to original suggest API search."""
        clean_query = query.strip()
        try:
            resp = self.session.get(
                self.SUGGEST_URL,
                params={"q": clean_query},
                timeout=self.timeout
            )
            resp.raise_for_status()
            items = resp.json()
        except Exception as e:
            logger.warning(f"Douban search suggest failed for '{query}': {e}")
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
                work.ratings[self.name] = SourceRating(
                    source_name=self.name,
                    rate=details["rate"],
                    rating_count=details["votes"],
                    url=subject_url,
                    title=title
                )

            edition = Edition(edition_id=sub_id or "1", title=title, publish_year=pub_year_str)
            work.editions.append(edition)
            works.append(work)

        return works

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

        # Try scraping the subject_search page first to get up to 15 results with ratings in a single request.
        start_index = (page - 1) * 15
        search_url = f"https://search.douban.com/book/subject_search?search_text={urllib.parse.quote(clean_query)}&cat=1001&start={start_index}"
        
        try:
            html_content = self._fetch_html(search_url)
            match = re.search(r'window\.__DATA__\s*=\s*(\{.*?\});', html_content)
            if match:
                data = json.loads(match.group(1))
                items = data.get("items", [])
                
                works: List[Work] = []
                for item in items:
                    if not isinstance(item, dict) or item.get("tpl_name") != "search_subject":
                        continue

                    sub_id = str(item.get("id", ""))
                    if not sub_id:
                        continue

                    title = item.get("title", "Unknown Title")
                    subject_url = item.get("url") or _build_subject_url(sub_id)
                    
                    rating_data = item.get("rating", {})
                    rate_val = rating_data.get("value")
                    votes_val = rating_data.get("count")
                    
                    rate = None
                    votes = None
                    if rate_val is not None:
                        try:
                            rate = float(rate_val)
                        except ValueError:
                            pass
                    if votes_val is not None:
                        try:
                            votes = int(votes_val)
                        except ValueError:
                            pass

                    # Parse abstract to extract author and pub_year
                    abstract_str = item.get("abstract", "")
                    author_name = "Unknown Author"
                    pub_year_str = ""
                    pub_year = None
                    if abstract_str:
                        parts = [p.strip() for p in abstract_str.split("/") if p.strip()]
                        if parts:
                            author_name = parts[0]
                            for p in parts[1:]:
                                year_match = re.search(r'\b(\d{4})\b', p)
                                if year_match:
                                    pub_year_str = year_match.group(1)
                                    pub_year = int(pub_year_str)
                                    break

                    work = Work(
                        work_id=f"db:{sub_id}",
                        title=title,
                        author=author_name,
                        first_publish_year=pub_year,
                        edition_count=None
                    )

                    work.ratings[self.name] = SourceRating(
                        source_name=self.name,
                        rate=rate,
                        rating_count=votes,
                        url=subject_url,
                        title=title
                    )

                    edition = Edition(
                        edition_id=sub_id,
                        title=title,
                        publish_year=pub_year_str
                    )
                    work.editions.append(edition)
                    works.append(work)

                if works:
                    return works
        except Exception as e:
            logger.warning(f"Failed to scrape Douban search page for '{query}': {e}")

        # Fallback to suggest API
        return self._search_works_suggest(query, limit=limit, page=page)

    @property
    def default_strategy(self) -> str:
        return "isbn_primary"

    def fetch_ratings(self, work: Work, strategy: Optional[str] = None) -> SourceRating:
        """Fetch Douban rating for a Work using explicit SearchStrategy."""
        return self._fetch_ratings(work, strategy=strategy)

    def fetch_editions(self, work_id: str, limit: int = 10) -> List[Edition]:
        """Fetch editions associated with a specific Douban Work/Subject ID."""
        if not work_id:
            return []

        if ":" in work_id:
            work_id = work_id.split(":", 1)[1]

        is_works_id = "works" in work_id

        id_match = re.search(r'(\d+)', work_id)
        if not id_match:
            return []
        numeric_id = id_match.group(1)

        if not is_works_id:
            subject_url = f"https://book.douban.com/subject/{numeric_id}/"
            html_str = self._fetch_html(subject_url)
            if not html_str:
                return []

            # Try to find the works link
            works_match = re.search(r'href="([^"]*?/works/(\d+))"', html_str)
            if works_match:
                works_path = works_match.group(1)
                if works_path.startswith("/"):
                    works_url = f"https://book.douban.com{works_path}"
                else:
                    works_url = works_path
            else:
                # No works link found, fallback to original subject details
                details = _parse_subject_html(html_str, subject_url)
                return [Edition(
                    edition_id=numeric_id,
                    title=details["title"] or "Unknown",
                    publish_year=details["pub_year"],
                    isbn_13=details["isbn"] if details["isbn"] and len(details["isbn"]) == 13 else None,
                    isbn_10=details["isbn"] if details["isbn"] and len(details["isbn"]) == 10 else None,
                )]
        else:
            works_url = f"https://book.douban.com/works/{numeric_id}"

        html_str = self._fetch_html(works_url)
        if not html_str:
            return []

        blocks = html_str.split('<div class="bkses')
        editions: List[Edition] = []
        for block in blocks[1:]:
            if len(editions) >= limit:
                break

            title_match = re.search(r'<a\s+class="pl2"\s+href="https://book\.douban\.com/subject/(\d+)/?"[^>]*>\s*(.*?)\s*</a>', block, re.DOTALL)
            if not title_match:
                title_match = re.search(r'href="https://book\.douban\.com/subject/(\d+)/?"[^>]*>\s*([^<]+)', block, re.DOTALL)

            if not title_match:
                continue

            sub_id = title_match.group(1).strip()
            title = title_match.group(2).strip()
            title = re.sub(r'\s+', ' ', title)

            pub_match = re.search(r'<span class="pl">\s*出版社:\s*</span>\s*(.*?)\s*<br/>', block, re.DOTALL)
            publisher = pub_match.group(1).strip() if pub_match else None

            year_match = re.search(r'<span class="pl">\s*出版年:\s*</span>\s*(.*?)\s*<br/>', block, re.DOTALL)
            pub_year = year_match.group(1).strip() if year_match else None

            editions.append(Edition(
                edition_id=sub_id,
                title=title,
                publish_year=pub_year,
                publisher=publisher
            ))

        return editions


class DoubanApiSource(DoubanSource):
    """Source for querying Douban (豆瓣) ratings and book subjects via suggest API."""

    @property
    def name(self) -> str:
        return "Douban API"

    def search_works(self, query: str, limit: int = 5, page: int = 1) -> List[Work]:
        return self._search_works_suggest(query, limit=limit, page=page)

