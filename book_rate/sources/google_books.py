import logging
import os
import re
from typing import List, Optional

from book_rate.models import Work, Edition, SourceRating
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
        self.quota_exceeded = False

    @property
    def name(self) -> str:
        return "Google Books"

    @property
    def default_strategy(self) -> str:
        return "isbn_primary"

    def fetch_ratings(self, work: Work, strategy: Optional[str] = None) -> SourceRating:
        """Fetch Google Books rating for a Work using explicit SearchStrategy and enrich with Google Play ratings."""
        if self.quota_exceeded:
            return SourceRating(
                source_name=self.name,
                strategy=strategy or self.default_strategy,
                status="QUOTA_EXCEEDED"
            )

        rating = self._fetch_ratings(work, strategy=strategy)

        # Enhance Google Books rating with Google Play details if a match was found
        if rating and rating.status in ("MATCH", "CURL_MATCH"):
            volume_id = None
            if work.work_id and work.work_id.startswith("gb:"):
                volume_id = work.work_id[3:]
            else:
                volume_id = self._extract_volume_id(rating)

            if volume_id:
                logger.info(f"Enriching Google Books rating from Google Play Books for volume {volume_id}")
                play_rate, play_count = self._fetch_google_play_rating(volume_id)
                if play_rate is not None:
                    rating.rate = play_rate
                    rating.rating_count = play_count
                    rating.url = f"https://play.google.com/store/books/details?id={volume_id}"
                    if getattr(self, "last_request_used_curl", False):
                        rating.status = "CURL_MATCH"
                    else:
                        rating.status = "MATCH"

                # Update matching result in results list if present
                if rating.results:
                    for res in rating.results:
                        res_vol_id = self._extract_volume_id_from_url(res.get("url"))
                        if res_vol_id == volume_id and play_rate is not None:
                            res["average"] = play_rate
                            res["count"] = play_count
                            res["url"] = f"https://play.google.com/store/books/details?id={volume_id}"
                            res["status"] = "MATCH"

        return rating

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
        html_content = self._fetch_html(url)
        if not html_content:
            return None, None

        # 1. Try parsing application/ld+json
        ld_json_blocks = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html_content, re.DOTALL)
        import json
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
                if not self.quota_exceeded:
                    self.quota_exceeded = True
                    logger.warning(
                        "Google Books API rate limit / quota exceeded (HTTP 429). "
                        "Consider setting GOOGLE_BOOKS_API_KEY environment variable."
                    )
                return []
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"Google Books API search failed for '{query}': {e}")
            return []

        items = data.get("items", [])
        works: List[Work] = []

        for item in items:
            volume_id = item.get("id", "")
            vol_info = item.get("volumeInfo", {})
            title = vol_info.get("title", "Unknown Title")
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
                publish_year=vol_info.get("publishedDate"),
                language=vol_info.get("language"),
                isbn_10=isbn_10,
                isbn_13=isbn_13,
                publisher=vol_info.get("publisher")
            )
            work.editions.append(edition)
            works.append(work)

        return works

    def fetch_volume_by_id(self, volume_id: str) -> Optional[Work]:
        """Fetch a specific volume by Google Books volume ID."""
        url = f"{self.BASE_URL}/{volume_id}"
        params = {}
        if self.api_key:
            params["key"] = self.api_key

        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            item = resp.json()
            vol_info = item.get("volumeInfo", {})
            title = vol_info.get("title", "Unknown Title")
            authors = vol_info.get("authors", [])
            author_str = ", ".join(authors) if authors else "Unknown Author"

            avg_rating = vol_info.get("averageRating")
            ratings_count = vol_info.get("ratingsCount")

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
        except Exception as e:
            logger.warning(f"Failed to fetch Google Books volume ID {volume_id}: {e}")
            return None
