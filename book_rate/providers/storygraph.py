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

        works: List[Work] = []
        for href, b_id, title, author_name in unique_books[:limit]:
            subject_url = f"{self.BASE_URL}{href}"
            avg_rating, ratings_count = self._fetch_book_rating(b_id)

            work = Work(
                work_id=f"sg:{b_id}",
                title=title,
                author=author_name,
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

            edition = Edition(edition_id=b_id, title=title)
            work.editions.append(edition)
            works.append(work)

        return works

    def fetch_ratings(self, work: Work) -> PlatformRating:
        """Fetch StoryGraph rating for a Work."""
        if work.work_id and work.work_id.startswith("sg:"):
            b_id = work.work_id[3:]
            rate, votes = self._fetch_book_rating(b_id)
            subject_url = f"{self.BASE_URL}/books/{b_id}"
            return PlatformRating(
                platform_name=self.name,
                rate=rate,
                rating_count=votes,
                url=subject_url,
                title=work.title
            )

        return self._fetch_ratings_with_fallback(work)
