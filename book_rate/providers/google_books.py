import logging
import os
import re
from typing import List, Optional

from book_rate.models import Work, Edition, PlatformRating
from book_rate.providers.base import BaseProvider
from book_rate.utils.isbn import clean_isbn, extract_isbns_from_work

logger = logging.getLogger(__name__)


class GoogleBooksProvider(BaseProvider):
    """Provider for querying Google Books API volumes and ratings."""

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

            work = Work(
                work_id=f"gb:{volume_id}",
                title=title,
                author=author_str,
                first_publish_year=pub_year,
                edition_count=1,
                isbn=isbn_13 or isbn_10
            )

            if avg_rating is not None or ratings_count is not None:
                work.ratings[self.name] = PlatformRating(
                    platform_name=self.name,
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

            work = Work(
                work_id=f"gb:{volume_id}",
                title=title,
                author=author_str,
                first_publish_year=pub_year,
                edition_count=1,
                isbn=isbn_13 or isbn_10
            )

            if avg_rating is not None or ratings_count is not None:
                work.ratings[self.name] = PlatformRating(
                    platform_name=self.name,
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

    def fetch_ratings(self, work: Work) -> PlatformRating:
        """Fetch rating info by ISBN or title/author."""
        if self.quota_exceeded:
            return PlatformRating(platform_name=self.name)

        if self.name in work.ratings:
            return work.ratings[self.name]

        # Use clean ISBN search
        isbns = extract_isbns_from_work(work)
        for isbn in isbns:
            try:
                gb_works = self.search_works(f"isbn:{isbn}", limit=1)
                if gb_works and self.name in gb_works[0].ratings:
                    return gb_works[0].ratings[self.name]
            except Exception as e:
                logger.debug(f"Failed to query Google Books rating for ISBN {isbn}: {e}")

        # Title fallback
        if work.title:
            query = f"intitle:{work.title}"
            if work.author and work.author not in ["Unknown Author", "Unknown"]:
                query += f" inauthor:{work.author.split(',')[0].strip()}"
            try:
                gb_works = self.search_works(query, limit=1)
                if gb_works and self.name in gb_works[0].ratings:
                    return gb_works[0].ratings[self.name]
            except Exception as e:
                logger.debug(f"Failed to query Google Books rating for title '{work.title}': {e}")

        return PlatformRating(platform_name=self.name)
