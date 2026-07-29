import logging
import os
from typing import List, Optional
import requests

from book_rate.models import Work, Edition, PlatformRating
from book_rate.providers.base import BaseProvider

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
                if id_type == "ISBN_10":
                    isbn_10 = identifier.get("identifier")
                elif id_type == "ISBN_13":
                    isbn_13 = identifier.get("identifier")

            pub_date = vol_info.get("publishedDate")
            pub_year = None
            if pub_date:
                import re
                year_match = re.search(r'\b\d{4}\b', pub_date)
                if year_match:
                    pub_year = int(year_match.group(0))

            work = Work(
                work_id=f"gb:{volume_id}",
                title=title,
                author=author_str,
                first_publish_year=pub_year,
                edition_count=1
            )

            # Store platform rating
            if avg_rating is not None or ratings_count is not None:
                work.ratings[self.name] = PlatformRating(
                    platform_name=self.name,
                    rate=float(avg_rating) if avg_rating is not None else None,
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

    def fetch_volume_by_id(self, volume_id: str) -> Optional[Work]:
        """Fetch details of a single Google Books volume by ID."""
        if self.quota_exceeded or not volume_id:
            return None

        url = f"{self.BASE_URL}/{volume_id}"
        params = {}
        if self.api_key:
            params["key"] = self.api_key

        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            if resp.status_code == 429:
                self.quota_exceeded = True
                logger.warning("Google Books API rate limit / quota exceeded (HTTP 429).")
                return None
            resp.raise_for_status()
            item = resp.json()
        except Exception as e:
            logger.warning(f"Google Books API fetch volume failed for '{volume_id}': {e}")
            return None

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

        pub_date = vol_info.get("publishedDate")
        pub_year = None
        if pub_date:
            import re
            year_match = re.search(r'\b\d{4}\b', pub_date)
            if year_match:
                pub_year = int(year_match.group(0))

        description = vol_info.get("description", "")
        import re
        original_title = None
        # 1. Search for parentheses in title (e.g. "原子習慣 (Atomic Habits)")
        title_matches = re.findall(r'[（\(]([a-zA-Z0-9\s\-,:\'!]+)[）\)]', title)
        for m in title_matches:
            m_clean = m.strip()
            if len(m_clean.split()) >= 1:
                original_title = m_clean
                break

        # 2. Search description for English text inside parentheses or quotes
        if not original_title and description:
            matches = re.findall(r'[（\(《]([a-zA-Z\s\-,:\'!]{3,})[）\)裝》]', description)
            for m in matches:
                m_clean = m.strip()
                words = m_clean.split()
                if len(words) >= 1:
                    if any(w.lower() in ["isbn", "pdf", "epub", "api"] for w in words):
                        continue
                    if len(words) >= 2 or (len(words) == 1 and words[0].istitle()):
                        original_title = m_clean
                        break

        # 3. Fallback: Find the longest English sequence starting with a capital letter in the first 300 chars of description
        if not original_title and description:
            first_part = description[:300]
            eng_sequences = re.findall(r'\b[A-Z][a-zA-Z\s\-,:\'!]{4,}\b', first_part)
            if eng_sequences:
                longest = max(eng_sequences, key=len)
                longest_clean = longest.strip()
                if len(longest_clean.split()) >= 1:
                    original_title = longest_clean

        work = Work(
            work_id=f"gb:{volume_id}",
            title=title,
            author=author_str,
            first_publish_year=pub_year,
            edition_count=1,
            original_title=original_title
        )

        # Store platform rating
        if avg_rating is not None or ratings_count is not None:
            work.ratings[self.name] = PlatformRating(
                platform_name=self.name,
                rate=float(avg_rating) if avg_rating is not None else None,
                rating_count=int(ratings_count) if ratings_count is not None else 0,
                url=vol_info.get("infoLink"),
                title=title
            )

        # Create primary edition for this volume
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
