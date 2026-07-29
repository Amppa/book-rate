import logging
import os
from typing import List, Optional
import requests

from models import Work, Edition, PlatformRating
from providers.base import BaseProvider

logger = logging.getLogger(__name__)


class GoogleBooksProvider(BaseProvider):
    """Provider for querying Google Books API volumes and ratings."""

    BASE_URL = "https://www.googleapis.com/books/v1/volumes"

    def __init__(self, api_key: Optional[str] = None, timeout: int = 10):
        self.api_key = api_key or os.environ.get("GOOGLE_BOOKS_API_KEY")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "BookScoreAggregator/1.0 (https://github.com/books-score)"
        })
        self.quota_exceeded = False

    @property
    def name(self) -> str:
        return "Google Books"

    def search_works(self, query: str, limit: int = 5, include_details: bool = True) -> List[Work]:
        """Search Google Books volumes for query."""
        clean_query = query.strip()
        if not clean_query:
            return []

        params = {
            "q": clean_query,
            "maxResults": min(limit, 10),
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
                if id_type == "ISBN_10":
                    isbn_10 = identifier.get("identifier")
                elif id_type == "ISBN_13":
                    isbn_13 = identifier.get("identifier")

            work = Work(
                work_id=f"gb:{volume_id}",
                title=title,
                author=author_str
            )

            # Store platform rating
            if avg_rating is not None or ratings_count is not None:
                work.ratings[self.name] = PlatformRating(
                    platform_name=self.name,
                    score=float(avg_rating) if avg_rating is not None else None,
                    rating_count=int(ratings_count) if ratings_count is not None else 0,
                    url=vol_info.get("infoLink"),
                    title=title
                )

            # Create primary edition for this volume
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

    def fetch_ratings(self, work: Work) -> PlatformRating:
        """Fetch rating info by ISBN or Volume ID if work exists in Google Books."""
        if self.quota_exceeded:
            return PlatformRating(platform_name=self.name)

        # Check if work already has Google Books rating
        if self.name in work.ratings:
            return work.ratings[self.name]

        # If work has ISBN in editions, search Google Books by ISBN
        for ed in work.editions:
            isbn = ed.isbn_13 or ed.isbn_10
            if isbn:
                try:
                    gb_works = self.search_works(f"isbn:{isbn}", limit=1)
                    if gb_works and self.name in gb_works[0].ratings:
                        return gb_works[0].ratings[self.name]
                except Exception as e:
                    logger.debug(f"Failed to query Google Books rating for ISBN {isbn}: {e}")

        # Fallback search by title and author
        if work.title:
            query = f"intitle:{work.title}"
            if work.author and work.author != "Unknown Author":
                query += f" inauthor:{work.author}"
            try:
                gb_works = self.search_works(query, limit=1)
                if gb_works and self.name in gb_works[0].ratings:
                    return gb_works[0].ratings[self.name]
            except Exception as e:
                logger.debug(f"Failed to query Google Books rating by title '{query}': {e}")

        return PlatformRating(platform_name=self.name)
