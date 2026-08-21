import html
import logging
import re
import subprocess
import urllib.parse
from typing import List, Optional

from book_rate.models import Work, Edition, SourceRating, SourceStatus
from book_rate.sources.base import BaseSource, SourceNetworkError

logger = logging.getLogger(__name__)


def _parse_compact_number(val_str: str) -> Optional[int]:
    """Parse number strings like '1.5k', '2.3M', '1,500', '304' into integers."""
    if not val_str:
        return None
    cleaned = val_str.strip().replace(",", "").replace("+", "").lower()
    try:
        if cleaned.endswith("k"):
            return int(float(cleaned[:-1]) * 1000)
        elif cleaned.endswith("m"):
            return int(float(cleaned[:-1]) * 1000000)
        return int(float(cleaned))
    except (ValueError, TypeError):
        return None


class StoryGraphSource(BaseSource):
    """Source for querying The StoryGraph (app.thestorygraph.com) ratings and books."""

    BASE_URL = "https://app.thestorygraph.com"
    BROWSE_URL = "https://app.thestorygraph.com/browse"

    @property
    def name(self) -> str:
        return "StoryGraph"


    def _fetch_book_rating(self, book_id: str) -> tuple[Optional[float], Optional[int], bool]:
        """Fetch rating and review count for a book from community_reviews Turbo Frame."""
        reviews_url = f"{self.BASE_URL}/books/{book_id}/community_reviews"
        res = self._fetch_html(reviews_url)
        if isinstance(res, tuple):
            r_html, used_curl = res
        else:
            r_html, used_curl = str(res), False

        if not r_html:
            return None, None, used_curl

        # Parse aria-label="Book rating: 4.16 out of 5 stars based on 89,069 reviews"
        aria_m = re.search(
            r'aria-label="Book rating:\s*([\d\.]+)\s*out of 5 stars based on ([\d,]+)\s*reviews"',
            r_html,
            re.IGNORECASE
        )
        if aria_m:
            try:
                rate = float(aria_m.group(1))
                votes = int(aria_m.group(2).replace(",", ""))
                return rate, votes, used_curl
            except ValueError:
                pass

        rate_m = re.search(r'average-star-rating[^>]*>\s*([\d\.]+)', r_html)
        votes_m = re.search(r'([\d,]+)\s*reviews', r_html)
        rate = float(rate_m.group(1)) if rate_m else None
        votes = int(votes_m.group(1).replace(",", "")) if votes_m else None
        return rate, votes, used_curl

    def fetch_book_details(self, book_id: str) -> dict:
        """Fetch book details page from StoryGraph and extract ISBN, pub_year, and editions_count."""
        url = f"https://app.thestorygraph.com/books/{book_id}"
        res = {
            "isbn": None,
            "pub_year": None,
            "editions_count": None,
            "work_id": book_id,
            "title": None,
            "author": None,
            "crawler_status": "Normal",
            "url": url,
            "used_curl": False,
        }

        try:
            fetch_res = self._fetch_html(url)
            if isinstance(fetch_res, tuple):
                html_str, used_curl = fetch_res
            else:
                html_str, used_curl = str(fetch_res), False

            res["used_curl"] = used_curl
            if not html_str:
                res["crawler_status"] = "Empty HTML response"
                return res

            # 1. Extract editions count (e.g. "1.5k editions", "304 editions", "Other editions (1.5k)")
            editions_match = (
                re.search(r'class="browse-editions-link[^"]*">\s*([0-9\.,\s\+kKmM]+)\s*editions', html_str, re.IGNORECASE) or
                re.search(r'href="[^"]*/books/[^"]+/editions"[^>]*>.*?([0-9\.,\s\+kKmM]+)\s*editions', html_str, re.IGNORECASE | re.DOTALL) or
                re.search(r'href="[^"]*/books/[^"]+/editions"[^>]*>.*?\(([0-9\.,\s\+kKmM]+)\)', html_str, re.IGNORECASE | re.DOTALL) or
                re.search(r'href="[^"]*/books/[^"]+/editions"[^>]*>([^<]+)</a>', html_str, re.IGNORECASE) or
                re.search(r'\b([0-9\.,\s\+kKmM]+)\s+editions\b', html_str, re.IGNORECASE) or
                re.search(r'editions\s*\(([0-9\.,\s\+kKmM]+)\)', html_str, re.IGNORECASE)
            )
            if editions_match:
                m_text = editions_match.group(1) if editions_match.lastindex else editions_match.group(0)
                num_match = re.search(r'([0-9\.]+\s*[kKmM]?)\+?', m_text)
                if num_match:
                    res["editions_count"] = _parse_compact_number(num_match.group(1))

            # 2. Extract ISBN/UID (e.g. <span class="font-semibold">ISBN/UID:</span> 9781846558238)
            isbn_match = re.search(r'ISBN/UID:</span>\s*([a-zA-Z0-9]+)', html_str, re.IGNORECASE)
            if isbn_match:
                res["isbn"] = isbn_match.group(1).strip()

            # 3. Extract publication year
            # Looking for: <span class="text-darkerGrey dark:text-lightGrey"> • </span>2011
            # Or Edition Pub Date: 25 Feb 2015
            pub_date_match = re.search(r'Edition Pub Date:</span>\s*([^<]+)', html_str, re.IGNORECASE)
            if pub_date_match:
                date_str = pub_date_match.group(1).strip()
                year_match = re.search(r'\b\d{4}\b', date_str)
                if year_match:
                    res["pub_year"] = year_match.group(0)
            else:
                # Try simple year match on lines with bullet points
                year_match = re.search(r'•\s*</span>\s*(\d{4})\b', html_str)
                if year_match:
                    res["pub_year"] = year_match.group(1)

            # 4. Extract title and author if not found
            title_match = re.search(r'<h3 class="[^"]*text-2xl[^"]*">\s*(.*?)\s*</h3>', html_str, re.DOTALL)
            if title_match:
                res["title"] = html.unescape(re.sub(r'<[^>]+>', '', title_match.group(1)).strip())

            author_match = re.search(r'href="/authors/[^"]+">\s*(.*?)\s*</a>', html_str, re.DOTALL)
            if author_match:
                res["author"] = html.unescape(re.sub(r'<[^>]+>', '', author_match.group(1)).strip())

        except Exception as e:
            logger.warning(f"Failed to fetch StoryGraph book details for '{book_id}': {e}")
            res["crawler_status"] = f"Error: {e}"

        return res

    def search_works(self, query: str, limit: int = 5, page: int = 1) -> List[Work]:
        """Search The StoryGraph browse endpoint for query string or ISBN."""
        clean_query = query.strip()
        if not clean_query:
            return []

        # Check if direct ID
        direct_id = None
        if clean_query.startswith("sg:"):
            direct_id = clean_query[3:]
        elif len(clean_query) == 36 and re.match(r'^[a-f0-9\-]{36}$', clean_query):
            direct_id = clean_query

        search_used_curl = False
        if direct_id:
            unique_books = [(f"/books/{direct_id}", direct_id, "Unknown Title", "Unknown Author")]
        else:
            search_url = f"{self.BROWSE_URL}?search_term={urllib.parse.quote(clean_query)}"
            fetch_res = self._fetch_html(search_url)
            if isinstance(fetch_res, tuple):
                search_html, search_used_curl = fetch_res
            else:
                search_html, search_used_curl = str(fetch_res), False

            if not search_html:
                if self.last_network_error:
                    raise SourceNetworkError(self.last_network_error, status_code=403)
                return []

            book_matches = re.findall(r'href="(/books/([a-f0-9\-]{36}))">([^<]+)</a>', search_html)
            author_matches = re.findall(r'href="/authors/[^"]+">([^<]+)</a>', search_html)

            unique_books = []
            seen_ids = set()

            for idx, (href, b_id, raw_title) in enumerate(book_matches):
                if b_id in seen_ids:
                    continue
                seen_ids.add(b_id)
                title = html.unescape(raw_title.strip())
                author = html.unescape(author_matches[len(unique_books)].strip()) if len(unique_books) < len(author_matches) else "Unknown Author"
                unique_books.append((href, b_id, title, author))

        def process_single_item(item):
            href, b_id, title, author_name = item
            subject_url = f"{self.BASE_URL}{href}"

            details = {"isbn": None, "pub_year": None, "editions_count": None, "crawler_status": "Normal", "used_curl": False}
            try:
                details = self.fetch_book_details(b_id)
            except Exception:
                pass

            # Fetch rating & rating count
            rate, votes = None, None
            rating_used_curl = False
            try:
                rate, votes, rating_used_curl = self._fetch_book_rating(b_id)
            except Exception as e:
                logger.warning(f"Failed to fetch StoryGraph rating for '{b_id}': {e}")
                if details.get("crawler_status") == "Normal":
                    details["crawler_status"] = f"Rating error: {e}"

            work = Work(
                work_id=f"sg:{b_id}",
                title=details.get("title") or title,
                author=details.get("author") or author_name,
                edition_count=details.get("editions_count"),
                first_publish_year=int(details.get("pub_year")) if details.get("pub_year") and str(details.get("pub_year")).isdigit() else None,
                isbn=details.get("isbn")
            )

            is_match = (rate is not None or votes is not None)
            has_used_curl = search_used_curl or details.get("used_curl", False) or rating_used_curl
            status_val = (SourceStatus.CURL_MATCH.value if has_used_curl else SourceStatus.MATCH.value) if is_match else (details.get("crawler_status") or SourceStatus.NO_MATCH.value)

            work.ratings[self.name] = SourceRating(
                source_name=self.name,
                rate=rate,
                rating_count=votes,
                url=subject_url,
                title=details.get("title") or title,
                status=status_val
            )

            edition = Edition(edition_id=b_id, title=details.get("title") or title)
            work.editions.append(edition)
            return work

        from concurrent.futures import ThreadPoolExecutor
        works: List[Work] = []
        with ThreadPoolExecutor(max_workers=limit) as executor:
            resolved_works = list(executor.map(process_single_item, unique_books[:limit]))
            works = [w for w in resolved_works if w is not None]

        return works

    @property
    def enable_extend_editions(self) -> bool:
        return True

    def fetch_editions(self, work_id: str, limit: int = 10) -> List[Edition]:
        """Fetch editions associated with a specific StoryGraph book/work ID."""
        if not work_id:
            return []

        if ":" in work_id:
            work_id = work_id.split(":", 1)[1]

        id_match = re.search(r'([a-f0-9\-]{36})', work_id)
        if not id_match:
            return []
        book_id = id_match.group(1)

        editions_url = f"{self.BASE_URL}/books/{book_id}/editions"
        fetch_res = self._fetch_html(editions_url)
        html_str = fetch_res[0] if isinstance(fetch_res, tuple) else fetch_res

        editions: List[Edition] = []

        if html_str:
            blocks = re.split(r'(?=<div[^>]*class="[^"]*book-pane[^"]*")', html_str)
            if len(blocks) <= 1:
                blocks = re.split(r'(?=<div[^>]*class="[^"]*edition[^"]*")', html_str)
            if len(blocks) <= 1:
                blocks = html_str.split('<div class="')

            for block in blocks:
                if len(editions) >= limit:
                    break

                b_id_match = re.search(r'href="/books/([a-f0-9\-]{36})"', block)
                if not b_id_match:
                    continue
                ed_id = b_id_match.group(1)

                title_match = re.search(r'<h3[^>]*>\s*(?:<a[^>]*>)?\s*(.*?)\s*(?:</a>)?\s*</h3>', block, re.DOTALL) or \
                              re.search(r'href="/books/[a-f0-9\-]{36}"[^>]*>\s*([^<]+)\s*</a>', block)
                if not title_match:
                    continue

                title = html.unescape(re.sub(r'<[^>]+>', '', title_match.group(1)).strip())
                if not title:
                    continue

                if any(e.edition_id == ed_id for e in editions):
                    continue

                # Extract ISBN
                isbn_match = re.search(r'ISBN(?:/UID)?:\s*</span>\s*([a-zA-Z0-9]+)', block, re.IGNORECASE) or \
                             re.search(r'ISBN(?:/UID)?:?\s*([0-9Xx]{10,13})', block, re.IGNORECASE)
                isbn = isbn_match.group(1).strip() if isbn_match else None
                isbn_10 = isbn if isbn and len(isbn) == 10 else None
                isbn_13 = isbn if isbn and len(isbn) == 13 else None

                # Extract publish year / date
                pub_year = None
                pub_date_match = re.search(r'Edition Pub Date:\s*</span>\s*([^<]+)', block, re.IGNORECASE) or \
                                 re.search(r'Published:\s*</span>\s*([^<]+)', block, re.IGNORECASE) or \
                                 re.search(r'•\s*</span>\s*(\d{4})\b', block)
                if pub_date_match:
                    d_str = pub_date_match.group(1).strip()
                    y_m = re.search(r'\b\d{4}\b', d_str)
                    pub_year = y_m.group(0) if y_m else d_str

                # Extract publisher
                pub_match = re.search(r'Publisher:\s*</span>\s*([^<]+)', block, re.IGNORECASE) or \
                            re.search(r'class="publisher"[^>]*>\s*([^<]+)\s*<', block, re.IGNORECASE)
                publisher = html.unescape(pub_match.group(1).strip()) if pub_match else None

                # Extract language
                lang_match = re.search(r'Language:\s*</span>\s*([^<]+)', block, re.IGNORECASE)
                language = lang_match.group(1).strip() if lang_match else None

                editions.append(Edition(
                    edition_id=ed_id,
                    title=title,
                    publish_year=pub_year,
                    publisher=publisher,
                    language=language,
                    isbn_10=isbn_10,
                    isbn_13=isbn_13
                ))

        if not editions:
            details = self.fetch_book_details(book_id)
            if details.get("title"):
                isbn = details.get("isbn")
                editions.append(Edition(
                    edition_id=book_id,
                    title=details["title"],
                    publish_year=details.get("pub_year"),
                    isbn_10=isbn if isbn and len(isbn) == 10 else None,
                    isbn_13=isbn if isbn and len(isbn) == 13 else None,
                ))

        return editions

    @property
    def default_strategy(self) -> str:
        return "title_author"

    def fetch_ratings(self, work: Work, strategy: Optional[str] = None) -> SourceRating:
        """Fetch StoryGraph rating for a Work using explicit SearchStrategy."""
        return self._fetch_ratings(work, strategy=strategy)
