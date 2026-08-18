import html
import json
import logging
import os
import re
import requests
from typing import List, Optional


from book_rate.models import Work, Edition, SourceRating, SourceStatus
from book_rate.sources.base import BaseSource
from book_rate.utils.isbn import clean_isbn, extract_isbns_from_work

logger = logging.getLogger(__name__)


class GoogleBooksSource(BaseSource):
    """Source for querying Google Books API volumes and ratings."""

    BASE_URL = "https://www.googleapis.com/books/v1/volumes"

    def __init__(self, api_key: Optional[str] = None, timeout: int = 10):
        super().__init__(timeout=timeout)
        self.api_key = api_key or os.environ.get("GOOGLE_BOOKS_API_KEY")
        self.session.headers.update({
            "User-Agent": "BookScoreAggregator/1.0 (https://github.com/books-score)"
        })

    def _clean_title(self, title: str, volume_id: str) -> str:
        """Detect and fix garbled titles caused by EACC/MARC-8 decoding errors in Google Books API."""
        if not title:
            return title

        if re.search(r'\+![\x21-\x7e]{3,}', title):
            url = f"https://books.google.com/books?id={volume_id}"
            try:
                html_content, _ = self._fetch_html(url)
                if html_content:
                    patterns = [
                        r'<meta\s+name=["\']title["\']\s+content=["\'](.*?)["\']',
                        r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']',
                        r'<title>(.*?)</title>'
                    ]
                    for pat in patterns:
                        m = re.search(pat, html_content, re.IGNORECASE)
                        if m:
                            scraped_title = html.unescape(m.group(1).strip())
                            scraped_title = re.sub(r'\s+-\s+Google\s+.*$', '', scraped_title, flags=re.IGNORECASE)
                            if scraped_title:
                                return scraped_title
            except Exception as e:
                logger.warning(f"Failed to scrape correct title for volume {volume_id}: {e}")

        return title

    @property
    def name(self) -> str:
        return "Google Books"

    @property
    def default_strategy(self) -> str:
        return "isbn_primary"

    def fetch_ratings(self, work: Work, strategy: Optional[str] = None) -> SourceRating:
        """Fetch Google Books rating for a Work via Google Books API."""
        rating = self._fetch_ratings(work, strategy=strategy)
        return rating if rating else SourceRating(source_name=self.name, strategy=strategy, status=SourceStatus.NOT_FOUND.value)

    def _extract_volume_id_from_url(self, url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        m = re.search(r'[?&]id=([^&]+)', url)
        if m:
            return m.group(1)
        m2 = re.search(r'books/details/([^?&/]+)', url)
        if m2:
            return m2.group(1)
        return None

    def _extract_volume_id(self, rating: SourceRating) -> Optional[str]:
        """Extract Google Books/Play volume ID from rating object."""
        if not rating:
            return None
        if rating.query and rating.query.startswith("gb:"):
            return rating.query[3:]
        return self._extract_volume_id_from_url(rating.url)

    def _fetch_google_play_rating(self, volume_id: str) -> tuple[Optional[float], Optional[int]]:
        """Fetch rating and vote count from Google Play Books detail page."""
        url = f"https://play.google.com/store/books/details?id={volume_id}"
        fetch_res = self._fetch_html(url)
        html_content = fetch_res[0] if isinstance(fetch_res, tuple) else fetch_res
        if not html_content:
            return None, None

        # 1. Try parsing application/ld+json
        ld_json_blocks = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html_content, re.DOTALL)
        for block in ld_json_blocks:
            try:
                data = json.loads(block.strip())
                if isinstance(data, dict):
                    items = [data]
                    if "@graph" in data and isinstance(data["@graph"], list):
                        items.extend(data["@graph"])

                    for item in items:
                        if "aggregateRating" in item and isinstance(item["aggregateRating"], dict):
                            ar = item["aggregateRating"]
                            r_val = ar.get("ratingValue")
                            r_count = ar.get("ratingCount")
                            if r_val is not None and r_count is not None:
                                return float(r_val), int(r_count)
            except Exception as e:
                logger.debug(f"Failed to parse JSON-LD block: {e}")

        # 2. Fallback to direct regex searches
        try:
            rv = re.search(r'"ratingValue"\s*:\s*"([^"]+)"', html_content)
            rc = re.search(r'"ratingCount"\s*:\s*"([^"]+)"', html_content)
            if rv and rc:
                return float(rv.group(1)), int(rc.group(1))
        except Exception as e:
            logger.debug(f"Fallback regex parsing failed: {e}")

        return None, None

    def search_works(self, query: str, limit: int = 5, include_details: bool = True, page: int = 1) -> List[Work]:
        """Search Google Books volumes for query."""
        clean_query = query.strip()
        if not clean_query:
            return []

        if clean_query.startswith("gb:"):
            vol_id = clean_query[3:]
            w = self.fetch_volume_by_id(vol_id)
            return [w] if w else []

        max_results = min(limit, 10)
        params = {
            "q": clean_query,
            "maxResults": max_results,
            "startIndex": (page - 1) * max_results
        }
        if self.api_key:
            params["key"] = self.api_key

        try:
            resp = self.session.get(self.BASE_URL, params=params, timeout=self.timeout)
            if resp.status_code == 429:
                logger.warning(
                    "Google Books API rate limit / quota exceeded (HTTP 429). "
                    "Consider setting GOOGLE_BOOKS_API_KEY environment variable."
                )
                print(f"  [Google Books API] ⚠️ QUOTA EXCEEDED (HTTP 429) for query '{query}'")
                return []
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.Timeout:
            logger.warning(f"Google Books API search timed out for '{query}'")
            print(f"  [Google Books API] ⏱️ TIMEOUT for query '{query}'")
            return []
        except Exception as e:
            logger.warning(f"Google Books API search failed for '{query}': {e}")
            print(f"  [Google Books API] ❌ ERROR ({e}) for query '{query}'")
        items = data.get("items", [])
        if not items:
            print(f"  [Google Books API] 🔍 0 RESULTS (No matching books) for query '{query}'")

        return [self._parse_volume_item(item) for item in items]

    def _parse_volume_item(self, item: dict) -> Work:
        """Parse raw Google Books volume API item into a Work object."""
        volume_id = item.get("id", "")
        vol_info = item.get("volumeInfo", {})
        title = vol_info.get("title", "Unknown Title")
        title = self._clean_title(title, volume_id)
        authors = vol_info.get("authors", [])
        author_str = ", ".join(authors) if authors else "Unknown Author"

        avg_rating = vol_info.get("averageRating")
        ratings_count = vol_info.get("ratingsCount")

        # ISBN extraction
        isbn_10 = None
        isbn_13 = None
        for identifier in vol_info.get("industryIdentifiers", []):
            id_type = identifier.get("type")
            cleaned = clean_isbn(identifier.get("identifier"))
            if id_type == "ISBN_10":
                isbn_10 = cleaned
            elif id_type == "ISBN_13":
                isbn_13 = cleaned

        pub_date = vol_info.get("publishedDate")
        pub_year: Optional[int] = None
        if pub_date:
            year_match = re.search(r'\b\d{4}\b', pub_date)
            if year_match:
                pub_year = int(year_match.group(0))

        orig_title = None
        desc = vol_info.get("description", "")
        if desc:
            orig_match = re.search(r'《[^》]+》（([A-Za-z0-9\s:,]+)）', desc) or re.search(r'\((?:英文版|原文書名|Original Title)?\s*([A-Z][a-zA-Z0-9\s:]+)\)', desc)
            if orig_match:
                orig_title = orig_match.group(1).strip()

        work = Work(
            work_id=f"gb:{volume_id}",
            title=title,
            author=author_str,
            first_publish_year=pub_year,
            isbn=isbn_13 or isbn_10,
            original_title=orig_title
        )

        if avg_rating is not None or ratings_count is not None:
            work.ratings[self.name] = SourceRating(
                source_name=self.name,
                rate=float(avg_rating) if avg_rating is not None else None,
                rating_count=int(ratings_count) if ratings_count is not None else 0,
                url=vol_info.get("infoLink"),
                title=title
            )

        edition = Edition(
            edition_id=volume_id,
            title=title,
            publish_year=pub_date,
            language=vol_info.get("language"),
            isbn_10=isbn_10,
            isbn_13=isbn_13,
            publisher=vol_info.get("publisher")
        )
        work.editions.append(edition)
        return work

    def fetch_volume_by_id(self, volume_id: str) -> Optional[Work]:
        """Fetch a specific volume by Google Books volume ID."""
        url = f"{self.BASE_URL}/{volume_id}"
        params = {}
        if self.api_key:
            params["key"] = self.api_key

        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            return self._parse_volume_item(resp.json())
        except Exception as e:
            logger.warning(f"Failed to fetch Google Books volume ID {volume_id}: {e}")
            return None
