import html
import json
import logging
import re
from datetime import datetime
from typing import List, Optional

from book_rate.models import Work, Edition, SourceRating, SourceStatus
from book_rate.sources.base import BaseSource
from book_rate.utils.isbn import clean_isbn

logger = logging.getLogger(__name__)


def _parse_goodreads_search_html(html_str: str, used_curl: bool, limit: int = 5) -> List[Work]:
    """Parse Goodreads search results page HTML."""
    if not html_str:
        return []

    works: List[Work] = []
    # Match each book table row
    row_pattern = re.compile(r'<tr[^>]*itemtype="http://schema\.org/Book"[^>]*>(.*?)</tr>', re.DOTALL | re.IGNORECASE)
    
    for row_match in row_pattern.finditer(html_str):
        if len(works) >= limit:
            break
        row_html = row_match.group(1)

        # 1. Book title, URL, and book_id
        title_m = re.search(r'<a[^>]*class="bookTitle"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', row_html, re.DOTALL)
        if not title_m:
            continue
        book_href = title_m.group(1)
        raw_title_inner = title_m.group(2)
        title = html.unescape(re.sub(r'<[^>]+>', '', raw_title_inner).strip())

        id_m = re.search(r'/book/show/(\d+)', book_href)
        book_id = id_m.group(1) if id_m else ""
        book_slug = book_href.split("/book/show/")[-1].split("?")[0] if "/book/show/" in book_href else (book_id or "")
        book_url = f"https://www.goodreads.com/book/show/{book_slug}" if book_slug else None

        # 2. Author
        author_m = re.search(r'<a[^>]*class="authorName"[^>]*>(.*?)</a>', row_html, re.DOTALL)
        author_name = "Unknown Author"
        if author_m:
            author_name = html.unescape(re.sub(r'<[^>]+>', '', author_m.group(1)).strip())

        # 3. Rating and rating count
        rate: Optional[float] = None
        rating_count: Optional[int] = None
        rating_text: Optional[str] = None
        rating_m = re.search(r'class="minirating".*?([\d.]+)\s+avg\s+rating\s*(?:&mdash;|—|-)\s*([\d,]+)\s+ratings?', row_html, re.DOTALL | re.IGNORECASE)
        if rating_m:
            try:
                rate = float(rating_m.group(1))
            except ValueError:
                pass
            try:
                rating_count = int(rating_m.group(2).replace(",", ""))
            except ValueError:
                pass

        if rate is not None and rate > 0:
            count_str = f"{rating_count:,} ratings" if rating_count else ""
            rating_text = f"{rate:.2f} ({count_str})" if count_str else f"{rate:.2f}"

        # 4. Publish year
        pub_year: Optional[int] = None
        pub_m = re.search(r'published\s*(\d{4})', row_html, re.IGNORECASE)
        if pub_m:
            try:
                pub_year = int(pub_m.group(1))
            except ValueError:
                pass

        # 5. Work ID and Editions count
        work_id_str = None
        editions_count: Optional[int] = None
        ed_m = re.search(r'href="[^"]*?/work/editions/(\d+)[^"]*"[^>]*>([\d,]+)\s+editions?</a>', row_html, re.IGNORECASE)
        if ed_m:
            work_id_str = ed_m.group(1)
            try:
                editions_count = int(ed_m.group(2).replace(",", ""))
            except ValueError:
                pass

        if work_id_str:
            work_key = f"gr:work/{work_id_str}/book/{book_slug}"
        elif book_slug:
            work_key = f"gr:book/{book_slug}"
        else:
            work_key = f"gr:{title}"

        is_match = (rate is not None or bool(title))
        status_val = (SourceStatus.CURL_MATCH.value if used_curl else SourceStatus.MATCH.value) if is_match else SourceStatus.NO_MATCH.value

        work = Work(
            work_id=work_key,
            title=title,
            author=author_name,
            edition_count=editions_count,
            first_publish_year=pub_year,
            isbn=None
        )
        work.ratings["Goodreads"] = SourceRating(
            source_name="Goodreads",
            rate=rate,
            rating_count=rating_count,
            rating_text=rating_text,
            url=book_url,
            title=title,
            status=status_val,
            author=author_name if author_name != "Unknown Author" else None,
            publish_date=str(pub_year) if pub_year else None,
            work_id=f"gr:{book_id}" if book_id else work_key,
            edition_count=editions_count
        )
        work.editions.append(Edition(
            edition_id=book_id or "1",
            title=title,
            publish_year=str(pub_year) if pub_year else None
        ))
        works.append(work)

    return works


class GoodreadsSource(BaseSource):
    """Source for querying Goodreads ratings and books."""

    AUTOCOMPLETE_URL = "https://www.goodreads.com/book/auto_complete"
    BOOK_SHOW_URL = "https://www.goodreads.com/book/show/{book_id}"

    @property
    def name(self) -> str:
        return "Goodreads"

    @property
    def enable_extend_editions(self) -> bool:
        return True

    def fetch_book_details(self, book_url_or_id: str) -> dict:
        """Fetch book detail HTML page from Goodreads and extract ISBN, pub_year, and editions_count."""
        url = book_url_or_id if book_url_or_id.startswith("http") else self.BOOK_SHOW_URL.format(book_id=book_url_or_id)
        res = {"isbn": None, "pub_year": None, "editions_count": None, "work_id": None, "title": None, "author": None, "crawler_status": "Normal", "url": url}

        book_id_m = re.search(r'/book/show/(\d+)', url) or re.search(r'/book/editions/(\d+)', url)
        book_id = book_id_m.group(1) if book_id_m else None

        if book_id:
            try:
                ed_url = f"https://www.goodreads.com/book/editions/{book_id}"
                ed_resp = self._get(ed_url, timeout=self.timeout)
                if ed_resp.status_code == 200:
                    res["crawler_status"] = "Normal"
                    
                    # 1. Extract work_id from final redirected URL
                    if ed_resp.url and isinstance(ed_resp.url, str):
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

    def _search_works_autocomplete(self, clean_query: str, limit: int = 5) -> List[Work]:
        """Search Goodreads using auto_complete endpoint via _fetch_html."""
        import urllib.parse
        auto_url = f"{self.AUTOCOMPLETE_URL}?q={urllib.parse.quote(clean_query)}"
        try:
            fetch_res = self._fetch_html(auto_url, headers={"Accept": "application/json"})
            content, used_curl = fetch_res if isinstance(fetch_res, tuple) else (str(fetch_res), False)
            if not content:
                return []

            content_lower = content.lower()
            if "awswaf" in content_lower or "gokuprops" in content_lower or "interstitialchallenge" in content_lower:
                logger.warning(f"Goodreads autocomplete blocked by WAF challenge for '{clean_query}'")
                self.last_network_error = "WAF Challenge"
                return []

            items = json.loads(content)
        except Exception as e:
            logger.warning(f"Goodreads autocomplete search failed for '{clean_query}': {e}")
            return []

        if not isinstance(items, list):
            return []

        works: List[Work] = []
        for item in items[:limit]:
            if not isinstance(item, dict):
                continue

            book_id = str(item.get("bookId", ""))
            work_id = str(item.get("workId", ""))
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

            rating_text: Optional[str] = None
            if avg_rating is not None:
                count_str = f"{ratings_count:,} ratings" if ratings_count else ""
                rating_text = f"{avg_rating:.2f} ({count_str})" if count_str else f"{avg_rating:.2f}"

            book_url_rel = item.get("bookUrl", "")
            book_url = f"https://www.goodreads.com{book_url_rel}" if book_url_rel else None
            book_slug = book_url_rel.split("/book/show/")[-1] if "/book/show/" in book_url_rel else (book_id or "")

            if work_id:
                work_key = f"gr:work/{work_id}/book/{book_slug}"
            elif book_slug:
                work_key = f"gr:book/{book_slug}"
            else:
                work_key = f"gr:{title}"

            status_val = SourceStatus.CURL_MATCH.value if used_curl else SourceStatus.MATCH.value

            work = Work(
                work_id=work_key,
                title=title,
                author=author_name,
                edition_count=None,
                first_publish_year=None,
                isbn=None
            )

            work.ratings[self.name] = SourceRating(
                source_name=self.name,
                rate=avg_rating,
                rating_count=ratings_count,
                rating_text=rating_text,
                url=book_url,
                title=title,
                status=status_val,
                author=author_name if author_name != "Unknown Author" else None,
                work_id=work_key
            )

            edition = Edition(
                edition_id=book_id or "1",
                title=title
            )
            work.editions.append(edition)
            works.append(work)

        return works

    def search_works(self, query: str, limit: int = 5, page: int = 1) -> List[Work]:
        """Search Goodreads using auto_complete endpoint with HTML search fallback."""
        clean_query = query.strip()
        if not clean_query:
            return []

        # 1. Primary: auto_complete endpoint via _fetch_html
        works = self._search_works_autocomplete(clean_query, limit=limit)
        if works:
            return works

        # 2. Fallback: search results page HTML
        import urllib.parse
        search_url = f"https://www.goodreads.com/search?q={urllib.parse.quote(clean_query)}&search_type=books&page={page}"
        try:
            fetch_res = self._fetch_html(search_url, headers={"Referer": "https://www.goodreads.com/"})
            html_content, used_curl = fetch_res if isinstance(fetch_res, tuple) else (str(fetch_res), False)
            if html_content:
                html_works = _parse_goodreads_search_html(html_content, used_curl, limit=limit)
                if html_works:
                    return html_works
        except Exception as e:
            logger.warning(f"Goodreads HTML search fallback failed for '{query}': {e}")

        return []

    def fetch_editions(self, work_id: str, limit: int = 10) -> List[Edition]:
        """Fetch editions associated with a specific Goodreads Work ID."""
        if not work_id:
            return []

        if ":" in work_id:
            work_id = work_id.split(":", 1)[1]

        work_id_m = re.search(r'work/(\d+)', work_id)
        if work_id_m:
            work_id = work_id_m.group(1)
        else:
            if "/" in work_id:
                work_id = work_id.split("/")[-1]

        editions: List[Edition] = []
        page = 1
        max_pages = 20
        resolved_work_id = work_id

        while len(editions) < limit and page <= max_pages:
            try:
                url = f"https://www.goodreads.com/work/editions/{resolved_work_id}?per_page=100&page={page}&utf8=%E2%9C%93"
                fetch_res = self._fetch_html(url, headers={"Referer": "https://www.goodreads.com/"})
                html_str, used_curl = fetch_res if isinstance(fetch_res, tuple) else (str(fetch_res), False)

                if page == 1 and (not html_str or "bookTitle" not in html_str):
                    alt_url = f"https://www.goodreads.com/book/editions/{work_id}?per_page=100&page=1&utf8=%E2%9C%93"
                    alt_res = self._fetch_html(alt_url, headers={"Referer": "https://www.goodreads.com/"})
                    alt_html, alt_curl = alt_res if isinstance(alt_res, tuple) else (str(alt_res), False)
                    if alt_html and "bookTitle" in alt_html:
                        html_str = alt_html

                if not html_str:
                    break

                work_id_m = re.search(r'/work/editions/(\d+)', html_str)
                if work_id_m:
                    resolved_work_id = work_id_m.group(1)

                blocks = html_str.split('<div class="elementList clearFix">')
                page_editions_count = 0
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
                    page_editions_count += 1

                if page_editions_count == 0:
                    break
                page += 1
            except Exception as e:
                logger.warning(f"Failed to fetch Goodreads editions page {page} for work '{work_id}': {e}")
                break

        return editions

    @property
    def default_strategy(self) -> str:
        return "title_author"

    def fetch_ratings(self, work: Work, strategy: Optional[str] = None) -> SourceRating:
        """Fetch Goodreads rating for a Work using explicit strategy."""
        return self._fetch_ratings(work, strategy=strategy)
