import logging
import re
import urllib.parse
from typing import List, Optional, Tuple

from book_rate.models import Work, Edition, SourceRating, SourceStatus
from book_rate.sources.base import BaseSource, SourceNetworkError
from book_rate.utils.isbn import clean_isbn
from book_rate.utils.text_parser import clean_text, extract_year, parse_compact_number

logger = logging.getLogger(__name__)


def _parse_compact_number(val_str: str) -> Optional[int]:
    """Backward compatible wrapper delegating to text_parser.parse_compact_number."""
    return parse_compact_number(val_str)


from book_rate.utils.metadata import empty_book_metadata, merge_book_metadata


def _parse_storygraph_book_html(html_str: str, book_id: str, url: str) -> dict:
    """Pure parsing function for The StoryGraph book detail page HTML."""
    res = {}
    if not html_str:
        return res

    # 1. Extract editions count
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
            res["edition_count"] = parse_compact_number(num_match.group(1))

    # 2. Extract ISBN/UID
    isbn_match = re.search(r'ISBN/UID:</span>\s*([a-zA-Z0-9]+)', html_str, re.IGNORECASE)
    if isbn_match:
        res["isbn"] = clean_isbn(isbn_match.group(1).strip()) or isbn_match.group(1).strip()

    # 3. Extract publication date
    pub_date_match = re.search(r'Edition Pub Date:</span>\s*([^<]+)', html_str, re.IGNORECASE)
    if pub_date_match:
        date_str = clean_text(pub_date_match.group(1))
        res["publish_date"] = date_str
    else:
        year_match = re.search(r'•\s*</span>\s*(\d{4})\b', html_str)
        if year_match:
            res["publish_date"] = year_match.group(1)

    # 4. Extract publisher, language, translator
    pub_match = re.search(r'Publisher:</span>\s*([^<]+)', html_str, re.IGNORECASE)
    if pub_match:
        res["publisher"] = clean_text(pub_match.group(1))

    lang_match = re.search(r'(?:Edition\s+)?Language:</span>\s*([^<]+)', html_str, re.IGNORECASE)
    if lang_match:
        res["language"] = clean_text(lang_match.group(1))

    trans_match = re.search(r'Translator:</span>\s*(?:<a[^>]*>)?([^<\n]+)', html_str, re.IGNORECASE)
    if trans_match:
        res["translator"] = clean_text(trans_match.group(1))

    # 5. Extract title and author
    title_match = re.search(r'<h3 class="[^"]*text-2xl[^"]*">\s*(.*?)\s*</h3>', html_str, re.DOTALL)
    if title_match:
        res["title"] = clean_text(title_match.group(1))

    author_match = re.search(r'href="/authors/[^"]+">\s*(.*?)\s*</a>', html_str, re.DOTALL)
    if author_match:
        res["author"] = clean_text(author_match.group(1))

    res["url"] = url
    res["work_id"] = f"sg:{book_id}"
    return res


def _parse_storygraph_reviews_html(r_html: str) -> Tuple[Optional[float], Optional[int]]:
    """Pure parsing function for The StoryGraph community reviews frame HTML."""
    if not r_html:
        return None, None

    aria_m = re.search(
        r'aria-label="Book rating:\s*([\d\.]+)\s*out of 5 stars based on ([\d,]+)\s*reviews"',
        r_html,
        re.IGNORECASE
    )
    if aria_m:
        try:
            rate = float(aria_m.group(1))
            votes = int(aria_m.group(2).replace(",", ""))
            return rate, votes
        except ValueError:
            pass

    rate_m = re.search(r'average-star-rating[^>]*>\s*([\d\.]+)', r_html)
    votes_m = re.search(r'([\d,]+)\s*reviews', r_html)
    rate = float(rate_m.group(1)) if rate_m else None
    votes = int(votes_m.group(1).replace(",", "")) if votes_m else None
    return rate, votes


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

        rate, votes = _parse_storygraph_reviews_html(r_html)
        return rate, votes, used_curl

    def fetch_book_details(self, book_id: str) -> dict:
        """Fetch book details page from StoryGraph and extract metadata."""
        url = f"https://app.thestorygraph.com/books/{book_id}"
        base = empty_book_metadata(url=url, work_id=f"sg:{book_id}")
        base["used_curl"] = False
        base["crawler_status"] = "Normal"

        try:
            fetch_res = self._fetch_html(url)
            if isinstance(fetch_res, tuple):
                html_str, used_curl = fetch_res
            else:
                html_str, used_curl = str(fetch_res), False

            base["used_curl"] = used_curl
            if not html_str:
                base["crawler_status"] = "Empty HTML response"
                return base

            parsed = _parse_storygraph_book_html(html_str, book_id, url)
            merge_book_metadata(base, parsed)
            # Backward compatible aliases
            base["editions_count"] = base.get("edition_count")
            if base.get("publish_date"):
                base["pub_year"] = extract_year(base["publish_date"])
                base["pub_date"] = base["publish_date"]
            else:
                base["pub_year"] = None
                base["pub_date"] = None
        except Exception as e:
            logger.warning(f"Failed to fetch StoryGraph book details for '{book_id}': {e}")
            base["crawler_status"] = f"Error: {e}"

        return base

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
                title = clean_text(raw_title) or "Unknown Title"
                author = clean_text(author_matches[len(unique_books)]) if len(unique_books) < len(author_matches) else "Unknown Author"
                unique_books.append((href, b_id, title, author or "Unknown Author"))

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

            parsed_author = details.get("author") or author_name
            work = Work(
                work_id=f"sg:{b_id}",
                title=details.get("title") or title,
                author=parsed_author,
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
                status=status_val,
                author=parsed_author if parsed_author != "Unknown Author" else None,
                translator=details.get("translator"),
                publisher=details.get("publisher"),
                publish_date=details.get("pub_date") or (str(details.get("pub_year")) if details.get("pub_year") else None),
                isbn=details.get("isbn"),
                language=details.get("language"),
                work_id=f"sg:{b_id}",
                edition_count=details.get("editions_count")
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

                title = clean_text(title_match.group(1))
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
                                 re.search(r'>\s*Edition Pub Date:\s*([^<]+)<', block, re.IGNORECASE) or \
                                 re.search(r'•\s*</span>\s*(\d{4})\b', block)
                if pub_date_match:
                    d_str = pub_date_match.group(1).strip()
                    y_m = re.search(r'\b\d{4}\b', d_str)
                    pub_year = y_m.group(0) if y_m else d_str

                # Extract publisher
                pub_match = re.search(r'Publisher:\s*</span>\s*([^<]+)', block, re.IGNORECASE) or \
                            re.search(r'<span[^>]*>\s*Publisher:\s*([^<]+?)\s*</span>', block, re.IGNORECASE) or \
                            re.search(r'class="publisher"[^>]*>\s*([^<]+)\s*<', block, re.IGNORECASE)
                publisher = clean_text(pub_match.group(1)) if pub_match else None

                # Extract language
                lang_match = re.search(r'Language:\s*</span>\s*([^<]+)', block, re.IGNORECASE) or \
                re.search(r'>\s*Language:\s*([^<]+)<', block, re.IGNORECASE)
                language = clean_text(lang_match.group(1)) if lang_match else None

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
        return "search_name"

    def fetch_ratings(self, work: Work, strategy: Optional[str] = None) -> SourceRating:
        """Fetch StoryGraph rating for a Work using explicit SearchStrategy."""
        return self._fetch_ratings(work, strategy=strategy)
