import json
import logging
import re
import urllib.parse
from typing import List, Optional

from book_rate.models import Work, Edition, SourceRating, SourceStatus
from book_rate.sources.base import BaseSource
from book_rate.utils.isbn import clean_isbn
from book_rate.utils.text_parser import clean_text

logger = logging.getLogger(__name__)


def _build_subject_url(sub_id: str) -> str:
    return f"https://book.douban.com/subject/{sub_id}/"


def _extract_douban_info_field(html_str: str, label_pattern: str) -> Optional[str]:
    """Extract a metadata field value from Douban #info block by label."""
    m = re.search(r'(?:<span class="pl">\s*)?' + label_pattern + r'\s*[:：]?\s*(?:</span>)?\s*[:：]?\s*(.*?)(?=<span class="pl">|<br\s*/?>|</div>|$)', html_str, re.DOTALL | re.IGNORECASE)
    if m:
        raw_val = m.group(1)
        clean_val = re.sub(r'<[^>]+>', ' ', raw_val)
        val = clean_text(clean_val)
        return val if val else None
    return None


def _parse_subject_html(html_str: str, url: str) -> dict:
    """Parse Douban subject HTML page and extract rating, votes count, ISBN, pub_year, title, and editions_count."""
    res = {
        "rate": None,
        "votes": None,
        "isbn": None,
        "pub_year": None,
        "title": None,
        "author": None,
        "translator": None,
        "publisher": None,
        "original_title": None,
        "url": url,
        "editions_count": None
    }
    if not html_str:
        return res

    rate_match = re.search(r'property="v:average">\s*([\d\.]+)\s*</', html_str)
    votes_match = re.search(r'property="v:votes">\s*(\d+)\s*</', html_str)
    title_match = re.search(r'<span property="v:itemreviewed">(.*?)</span>', html_str)

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
        res["title"] = clean_text(title_match.group(1))

    # Extract info block fields
    author_val = _extract_douban_info_field(html_str, r'(?:作者|著者|编者|编|著)')
    if author_val:
        res["author"] = author_val

    translator_val = _extract_douban_info_field(html_str, r'(?:译者|譯者)')
    if translator_val:
        res["translator"] = translator_val

    publisher_val = _extract_douban_info_field(html_str, r'出版社')
    if publisher_val:
        res["publisher"] = publisher_val

    orig_val = _extract_douban_info_field(html_str, r'(?:原作名|原名|英文名)')
    if orig_val:
        res["original_title"] = orig_val

    pub_val = _extract_douban_info_field(html_str, r'(?:出版年|出版日期)')
    if pub_val:
        res["pub_year"] = pub_val

    isbn_val = _extract_douban_info_field(html_str, r'ISBN')
    if isbn_val:
        res["isbn"] = clean_isbn(isbn_val) or isbn_val

    editions_match = re.search(r'这本书的其他版本.*?全部(\d+)', html_str, re.DOTALL)
    if editions_match:
        res["editions_count"] = int(editions_match.group(1))

    return res


def _parse_search_item(item: dict, used_curl: bool, source_name: str = "Douban") -> Optional[Work]:
    """Parse a single search_subject item from Douban search window.__DATA__."""
    if not isinstance(item, dict) or item.get("tpl_name") != "search_subject":
        return None

    sub_id = str(item.get("id", "")).strip()
    if not sub_id:
        return None

    title = item.get("title", "Unknown Title")
    subject_url = item.get("url") or _build_subject_url(sub_id)

    # 1. Parse rating info
    rating_data = item.get("rating") or {}
    rate_val = rating_data.get("value")
    votes_val = rating_data.get("count")
    null_reason = (rating_data.get("rating_info") or rating_data.get("null_reason") or "").strip()

    rate = None
    votes = None
    if rate_val is not None:
        try:
            r_float = float(rate_val)
            if r_float > 0:
                rate = r_float
        except ValueError:
            pass

    if votes_val is not None:
        try:
            v_int = int(votes_val)
            if v_int > 0:
                votes = v_int
        except ValueError:
            pass

    if rate is not None:
        votes_str = f"{votes}人评价" if votes is not None else ""
        rating_text = f"{rate:.1f} ({votes_str})" if votes_str else f"{rate:.1f}"
    elif null_reason:
        rating_text = null_reason
    else:
        rating_text = "暂无评分"

    # 2. Parse abstract for author, translator, publisher, and pub_year
    abstract_str = item.get("abstract", "")
    author_name = "Unknown Author"
    translator_str = None
    publisher_str = None
    pub_year_str = ""
    pub_year = None

    if abstract_str:
        raw_parts = [p.strip() for p in abstract_str.split("/") if p.strip()]
        # Strip trailing price if present (e.g. 49.00元, $10, etc.)
        parts = []
        for p in raw_parts:
            if re.search(r'[\d\.]+\s*(?:元|USD|NT\$|\$|円)', p):
                continue
            parts.append(p)

        if parts:
            # Find date part (e.g. 2007-7, 2007-07, 2007)
            date_idx = None
            for idx, p in enumerate(parts):
                if re.search(r'^\d{4}(?:-\d{1,2})?(?:-\d{1,2})?$', p) or re.search(r'^\d{4}年(?:\d{1,2}月)?', p):
                    date_idx = idx
                    pub_year_str = p
                    y_m = re.search(r'\b(\d{4})\b', p)
                    if y_m:
                        pub_year = int(y_m.group(1))
                    break

            if date_idx is not None:
                # Part immediately before date is usually publisher
                if date_idx > 0:
                    publisher_str = parts[date_idx - 1]
                # Part(s) before publisher are author / translator
                author_parts = parts[:max(0, date_idx - 1)]
                if len(author_parts) == 1:
                    author_name = author_parts[0]
                elif len(author_parts) >= 2:
                    author_name = author_parts[0]
                    translator_str = author_parts[1]
            else:
                author_name = parts[0]
                if len(parts) >= 2:
                    publisher_str = parts[1]

    is_match = (rate is not None or bool(null_reason))
    status_val = (SourceStatus.CURL_MATCH.value if used_curl else SourceStatus.MATCH.value) if is_match else SourceStatus.NO_MATCH.value

    work = Work(
        work_id=f"db:{sub_id}",
        title=title,
        author=author_name,
        first_publish_year=pub_year,
        edition_count=None
    )
    work.ratings[source_name] = SourceRating(
        source_name=source_name,
        rate=rate,
        rating_count=votes,
        rating_text=rating_text,
        url=subject_url,
        title=title,
        status=status_val,
        author=author_name if author_name != "Unknown Author" else None,
        translator=translator_str,
        publisher=publisher_str,
        publish_date=pub_year_str or None,
        work_id=f"db:{sub_id}"
    )
    work.editions.append(Edition(
        edition_id=sub_id,
        title=title,
        publish_year=pub_year_str,
        publisher=publisher_str
    ))
    return work


class DoubanSource(BaseSource):
    """Source for querying Douban (豆瓣) ratings and book subjects."""

    SUGGEST_URL = "https://book.douban.com/j/subject_suggest"
    ISBN_LOOKUP_URL = "https://book.douban.com/isbn/{isbn}/"

    def __init__(self, timeout: int = 10, cooldown: float = 1.0, enrich_search_ratings: bool = True):
        super().__init__(timeout=timeout, cooldown=cooldown)
        # Fetch each subject page during suggest-search so results carry ratings.
        self.enrich_search_ratings = enrich_search_ratings
        self.session.headers.update({
            "Referer": "https://book.douban.com/"
        })

    @property
    def name(self) -> str:
        return "Douban"

    @property
    def enable_extend_editions(self) -> bool:
        return True

    def fetch_subject_details(self, subject_url_or_id: str) -> dict:
        """Fetch subject detail HTML page from Douban and parse metadata."""
        url = subject_url_or_id if subject_url_or_id.startswith("http") else _build_subject_url(subject_url_or_id)
        try:
            resp = self._get(url, timeout=self.timeout)
            resp.raise_for_status()
            return _parse_subject_html(resp.text, url)
        except Exception as e:
            logger.warning(f"Failed to fetch Douban subject details from '{url}': {e}")
            return {"rate": None, "votes": None, "isbn": None, "pub_year": None, "title": None, "author": None, "translator": None, "publisher": None, "url": url, "editions_count": None}

    def _enrich_with_book_page(self, rating: SourceRating) -> SourceRating:
        """Enrich a candidate rating with detailed subject page score & votes."""
        if not rating or not rating.url:
            return rating
        details = self.fetch_subject_details(rating.url)
        if details.get("rate") is not None:
            rating.rate = details["rate"]
        if details.get("votes") is not None:
            rating.rating_count = details["votes"]
        if details.get("title"):
            rating.title = details["title"]
        if details.get("author"):
            rating.author = details["author"]
        if details.get("translator"):
            rating.translator = details["translator"]
        if details.get("publisher"):
            rating.publisher = details["publisher"]
        if details.get("original_title"):
            rating.original_title = details["original_title"]
        if details.get("pub_year"):
            rating.publish_date = details["pub_year"]
        if details.get("isbn"):
            rating.isbn = details["isbn"]
        if details.get("editions_count") is not None:
            rating.edition_count = details["editions_count"]
        return rating

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
            resp = self._get(url, timeout=self.timeout, allow_redirects=True)
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
                title=details["title"],
                author=details.get("author"),
                translator=details.get("translator"),
                publisher=details.get("publisher"),
                original_title=details.get("original_title"),
                publish_date=details.get("pub_year"),
                isbn=details.get("isbn") or isbn_str,
                work_id=f"db:{sub_id}",
                edition_count=details.get("editions_count")
            )
            return rating
        except Exception as e:
            logger.debug(f"Douban ISBN lookup failed for '{isbn_str}': {e}")
            return None

    def _search_works_suggest(self, query: str, limit: int = 5, page: int = 1) -> List[Work]:
        """Fallback to original suggest API search."""
        clean_query = query.strip()
        try:
            resp = self._get(
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

            work = Work(
                work_id=f"db:{sub_id}" if sub_id else f"db:{title}",
                title=title,
                author=author_name,
                first_publish_year=pub_year,
                edition_count=None
            )

            if subject_url:
                rating = SourceRating(
                    source_name=self.name,
                    url=subject_url,
                    title=title
                )
                if getattr(self, "enrich_search_ratings", True):
                    details = self.fetch_subject_details(subject_url)
                    if details.get("rate") is not None or details.get("votes") is not None:
                        rating.rate = details.get("rate")
                        rating.rating_count = details.get("votes")
                    if details.get("title"):
                        rating.title = details["title"]
                work.ratings[self.name] = rating

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
            fetch_res = self._fetch_html(search_url, headers={"Referer": "https://book.douban.com/"})
            html_content, used_curl = fetch_res if isinstance(fetch_res, tuple) else (str(fetch_res), False)

            match = re.search(r'window\.__DATA__\s*=\s*(\{.*?\});', html_content)
            if match:
                data = json.loads(match.group(1))
                items = data.get("items", [])
                works: List[Work] = []
                for item in items:
                    work = _parse_search_item(item, used_curl, self.name)
                    if work is not None:
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
            fetch_res = self._fetch_html(subject_url)
            html_str = fetch_res[0] if isinstance(fetch_res, tuple) else fetch_res
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

        fetch_res = self._fetch_html(works_url)
        html_str = fetch_res[0] if isinstance(fetch_res, tuple) else fetch_res
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

    @property
    def enable_extend_editions(self) -> bool:
        return False

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("enrich_search_ratings", False)
        super().__init__(*args, **kwargs)

    def search_works(self, query: str, limit: int = 5, page: int = 1) -> List[Work]:
        return self._search_works_suggest(query, limit=limit, page=page)

