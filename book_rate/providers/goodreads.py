import html
import json
import logging
import re
from datetime import datetime
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
        """Fetch book detail HTML page from Goodreads and extract ISBN, pub_year, and editions_count."""
        url = book_url_or_id if book_url_or_id.startswith("http") else self.BOOK_SHOW_URL.format(book_id=book_url_or_id)
        res = {"isbn": None, "pub_year": None, "editions_count": None, "work_id": None, "title": None, "author": None, "crawler_status": "Normal", "url": url}

        book_id_m = re.search(r'/book/show/(\d+)', url) or re.search(r'/book/editions/(\d+)', url)
        book_id = book_id_m.group(1) if book_id_m else None

        if book_id:
            try:
                ed_url = f"https://www.goodreads.com/book/editions/{book_id}"
                ed_resp = self.session.get(ed_url, timeout=self.timeout)
                if ed_resp.status_code == 200:
                    res["crawler_status"] = "Normal"
                    
                    # 1. Extract work_id from final redirected URL
                    work_id_m = re.search(r'/work/editions/(\d+)', ed_resp.url)
                    if work_id_m:
                        res["work_id"] = work_id_m.group(1)

                    # 2. Extract editions count from page HTML
                    count_m = re.search(r'showing\s+\d+.*?of\s+(\d+[,.\d]*)', ed_resp.text, re.IGNORECASE)
                    if count_m:
                        res["editions_count"] = int(count_m.group(1).replace(",", ""))

                    # 3. Extract title and author if missing
                    if not res["title"]:
                        title_m = re.search(r'<h1>\s*<a[^>]*>([^<]+)</a>\s*&gt;\s*Editions\s*</h1>', ed_resp.text, re.IGNORECASE | re.DOTALL)
                        if title_m:
                            res["title"] = html.unescape(title_m.group(1).strip())
                    if not res["author"]:
                        author_m = re.search(r'<h2>\s*by\s*<a[^>]*>([^<]+)</a>', ed_resp.text, re.IGNORECASE | re.DOTALL)
                        if author_m:
                            res["author"] = html.unescape(author_m.group(1).strip())

                    # 4. Extract ISBN and publish year from first edition block if still missing
                    blocks = ed_resp.text.split('<div class="elementList clearFix">')
                    if len(blocks) > 1:
                        first_block = blocks[1]
                        if not res["isbn"]:
                            isbn_match = re.search(r'ISBN:\s*</div>\s*<div class="dataValue">\s*([0-9Xx]+)?(?:\s*<span class="greyText">\s*\(ISBN10:\s*([0-9Xx]+)\)\s*</span>)?', first_block, re.IGNORECASE | re.DOTALL)
                            if isbn_match:
                                isbn13_val = isbn_match.group(1)
                                isbn10_val = isbn_match.group(2)
                                res["isbn"] = clean_isbn((isbn13_val or isbn10_val or "").strip())

                            if not res["isbn"]:
                                asin_match = re.search(r'ASIN:\s*</div>\s*<div class="dataValue">\s*([a-zA-Z0-9]+)\s*</div>', first_block, re.IGNORECASE | re.DOTALL)
                                if asin_match:
                                    res["isbn"] = asin_match.group(1).strip()

                        if not res["pub_year"]:
                            pub_div_match = re.search(r'<div class="dataRow">\s*Published\s+([^<]+?)\s*</div>', first_block, re.DOTALL | re.IGNORECASE)
                            if pub_div_match:
                                pub_text = pub_div_match.group(1).strip()
                                if "by" in pub_text:
                                    pub_text = pub_text.split("by", 1)[0].strip()
                                year_match = re.search(r'\b\d{4}\b', pub_text)
                                if year_match:
                                    res["pub_year"] = year_match.group(0)
                else:
                    res["crawler_status"] = f"HTTP {ed_resp.status_code}"
            except Exception as ed_e:
                logger.debug(f"Failed to fetch editions for book '{book_id}': {ed_e}")
                res["crawler_status"] = f"Error: {ed_e}"

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

        def process_single_item(item):
            if not isinstance(item, dict):
                return None

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

            # Fetch details concurrently to get actual editions count and status
            details = {"isbn": None, "pub_year": None, "editions_count": 1, "crawler_status": "Normal"}
            if book_id:
                try:
                    details = self.fetch_book_details(book_id)
                except Exception:
                    pass

            work = Work(
                work_id=f"gr:{book_id}" if book_id else f"gr:{title}",
                title=title,
                author=author_name,
                edition_count=details.get("editions_count") or 1,
                first_publish_year=int(details.get("pub_year")) if details.get("pub_year") and str(details.get("pub_year")).isdigit() else None,
                isbn=details.get("isbn")
            )

            work.ratings[self.name] = PlatformRating(
                platform_name=self.name,
                rate=avg_rating,
                rating_count=ratings_count,
                url=book_url,
                title=title,
                status=details.get("crawler_status") or "Normal"
            )

            edition = Edition(
                edition_id=book_id or "1",
                title=title,
                isbn_13=details.get("isbn") if details.get("isbn") and len(details.get("isbn")) == 13 else None,
                isbn_10=details.get("isbn") if details.get("isbn") and len(details.get("isbn")) == 10 else None
            )
            work.editions.append(edition)
            return work

        from concurrent.futures import ThreadPoolExecutor
        works: List[Work] = []
        with ThreadPoolExecutor(max_workers=limit) as executor:
            resolved_works = list(executor.map(process_single_item, items[:limit]))
            works = [w for w in resolved_works if w is not None]

        return works

    def fetch_editions(self, work_id: str, limit: int = 10) -> List[Edition]:
        """Fetch editions associated with a specific Goodreads Work ID."""
        if not work_id:
            return []

        if ":" in work_id:
            work_id = work_id.split(":", 1)[1]

        editions: List[Edition] = []
        try:
            url = f"https://www.goodreads.com/work/editions/{work_id}"
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            html_str = resp.text

            blocks = html_str.split('<div class="elementList clearFix">')
            for block in blocks[1:]:
                if len(editions) >= limit:
                    break
                if "bookTitle" not in block:
                    continue

                title_match = re.search(r'<a class="bookTitle" href="/book/show/(\d+)[^"]*">(.*?)</a>', block, re.DOTALL)
                if not title_match:
                    continue

                edition_id = title_match.group(1)
                title = html.unescape(title_match.group(2).strip())

                pub_div_match = re.search(r'<div class="dataRow">\s*Published\s+([^<]+?)\s*</div>', block, re.DOTALL | re.IGNORECASE)
                publish_year = None
                publisher = None
                if pub_div_match:
                    pub_text = pub_div_match.group(1).strip()
                    if "by" in pub_text:
                        parts = pub_text.split("by", 1)
                        pub_date_str = parts[0].strip()
                        publisher = html.unescape(parts[1].strip())
                    else:
                        pub_date_str = pub_text

                    year_match = re.search(r'\b\d{4}\b', pub_date_str)
                    if year_match:
                        publish_year = year_match.group(0)
                    else:
                        publish_year = pub_date_str

                lang_match = re.search(r'Edition language:\s*</div>\s*<div class="dataValue">\s*([^<]+?)\s*</div>', block, re.IGNORECASE | re.DOTALL)
                language = None
                if lang_match:
                    language = lang_match.group(1).strip()

                isbn_match = re.search(r'ISBN:\s*</div>\s*<div class="dataValue">\s*([0-9Xx]+)?(?:\s*<span class="greyText">\s*\(ISBN10:\s*([0-9Xx]+)\)\s*</span>)?', block, re.IGNORECASE | re.DOTALL)
                isbn_13 = None
                isbn_10 = None
                if isbn_match:
                    isbn_13 = isbn_match.group(1)
                    if isbn_13:
                        isbn_13 = clean_isbn(isbn_13.strip())
                    isbn_10 = isbn_match.group(2)
                    if isbn_10:
                        isbn_10 = clean_isbn(isbn_10.strip())

                asin_match = re.search(r'ASIN:\s*</div>\s*<div class="dataValue">\s*([a-zA-Z0-9]+)\s*</div>', block, re.IGNORECASE | re.DOTALL)
                if asin_match and not isbn_10:
                    isbn_10 = asin_match.group(1).strip()

                edition = Edition(
                    edition_id=edition_id,
                    title=title,
                    publish_year=publish_year,
                    publisher=publisher,
                    language=language,
                    isbn_13=isbn_13,
                    isbn_10=isbn_10
                )
                editions.append(edition)
        except Exception as e:
            logger.warning(f"Failed to fetch Goodreads editions for work '{work_id}': {e}")

        return editions

    @property
    def default_strategy(self) -> str:
        return "title_author"

    def fetch_ratings(self, work: Work, strategy: Optional[str] = None) -> PlatformRating:
        """Fetch Goodreads rating for a Work using explicit strategy."""
        return self._fetch_ratings(work, strategy=strategy)
