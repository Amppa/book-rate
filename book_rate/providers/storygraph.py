import html
import logging
import re
import subprocess
import urllib.parse
from typing import List, Optional

from book_rate.models import Work, Edition, PlatformRating
from book_rate.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class StoryGraphProvider(BaseProvider):
    """Provider for querying The StoryGraph (app.thestorygraph.com) ratings and books."""

    BASE_URL = "https://app.thestorygraph.com"
    BROWSE_URL = "https://app.thestorygraph.com/browse"

    @property
    def name(self) -> str:
        return "StoryGraph"

    def _fetch_html(self, url: str) -> str:
        """Fetch URL using curl.exe to pass Cloudflare TLS fingerprinting checks on Windows."""
        try:
            cmd = [
                "curl.exe", "-s", "-L",
                "-A", self.DEFAULT_USER_AGENT,
                url
            ]
            output = subprocess.check_output(cmd, timeout=self.timeout)
            return output.decode("utf-8", errors="ignore")
        except Exception as e:
            logger.warning(f"Failed to fetch HTML via curl for URL '{url}': {e}")
            try:
                resp = self.session.get(url, timeout=self.timeout)
                resp.raise_for_status()
                return resp.text
            except Exception as ex:
                logger.warning(f"Fallback requests.get also failed for '{url}': {ex}")
                return ""

    def _fetch_book_rating(self, book_id: str) -> tuple[Optional[float], Optional[int]]:
        """Fetch rating and review count for a book from community_reviews Turbo Frame."""
        reviews_url = f"{self.BASE_URL}/books/{book_id}/community_reviews"
        r_html = self._fetch_html(reviews_url)
        if not r_html:
            return None, None

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
                return rate, votes
            except ValueError:
                pass

        rate_m = re.search(r'average-star-rating[^>]*>\s*([\d\.]+)', r_html)
        votes_m = re.search(r'([\d,]+)\s*reviews', r_html)
        rate = float(rate_m.group(1)) if rate_m else None
        votes = int(votes_m.group(1).replace(",", "")) if votes_m else None
        return rate, votes

    def fetch_book_details(self, book_id: str) -> dict:
        """Fetch book details page from StoryGraph and extract ISBN, pub_year, and editions_count."""
        url = f"https://app.thestorygraph.com/books/{book_id}"
        res = {
            "isbn": None,
            "pub_year": None,
            "editions_count": 1,
            "work_id": book_id,
            "title": None,
            "author": None,
            "crawler_status": "Normal",
            "url": url
        }

        try:
            html_str = self._fetch_html(url)
            if not html_str:
                res["crawler_status"] = "Empty HTML response"
                return res

            # 1. Extract editions count (e.g. "304 editions" inside browse-editions-link)
            editions_match = re.search(r'class="browse-editions-link[^"]*">\s*([\d,]+)\s+editions', html_str, re.IGNORECASE)
            if not editions_match:
                # Alternate search pattern
                editions_match = re.search(r'([\d,]+)\s+editions', html_str, re.IGNORECASE)
            if editions_match:
                res["editions_count"] = int(editions_match.group(1).replace(",", ""))

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

        search_url = f"{self.BROWSE_URL}?search_term={urllib.parse.quote(clean_query)}"
        search_html = self._fetch_html(search_url)
        if not search_html:
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

            details = {"isbn": None, "pub_year": None, "editions_count": 1, "crawler_status": "Normal"}
            try:
                details = self.fetch_book_details(b_id)
            except Exception:
                pass

            work = Work(
                work_id=f"sg:{b_id}",
                title=details.get("title") or title,
                author=details.get("author") or author_name,
                edition_count=details.get("editions_count") or 1,
                first_publish_year=int(details.get("pub_year")) if details.get("pub_year") and str(details.get("pub_year")).isdigit() else None,
                isbn=details.get("isbn")
            )

            work.ratings[self.name] = PlatformRating(
                platform_name=self.name,
                rate=None,
                rating_count=None,
                url=subject_url,
                title=details.get("title") or title,
                status=details.get("crawler_status") or "Normal"
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
    def default_strategy(self) -> str:
        return "title_author"

    def fetch_ratings(self, work: Work, strategy: Optional[str] = None) -> PlatformRating:
        """Fetch StoryGraph rating for a Work using explicit SearchStrategy."""
        return self._fetch_ratings(work, strategy=strategy)
