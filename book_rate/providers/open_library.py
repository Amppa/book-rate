import logging
import urllib.parse
from typing import List, Optional
import requests

from book_rate.models import Work, Edition, PlatformRating
from book_rate.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class OpenLibraryProvider(BaseProvider):
    """Provider for fetching Works, Editions, and Ratings from Open Library."""

    BASE_URL = "https://openlibrary.org"

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "BookScoreAggregator/1.0 (https://github.com/books-score)"
        })

    @property
    def name(self) -> str:
        return "Open Library"

    def search_works(self, query: str, limit: int = 5, page: int = 1, include_details: bool = True) -> List[Work]:
        """Search Open Library for works matching query."""
        clean_query = query.strip()
        if not clean_query:
            return []

        fields = "key,title,author_name,ratings_average,ratings_count,edition_count,language,isbn,first_publish_year"
        docs = []

        # Try search strategies
        search_queries = []
        if len(clean_query) < 3:
            search_queries.append({"q": f"{clean_query}*"})
            search_queries.append({"title": clean_query})
        else:
            search_queries.append({"q": clean_query})
            search_queries.append({"q": f"{clean_query}*"})

        for q_params in search_queries:
            params = {"limit": limit, "page": page, "fields": fields, **q_params}
            try:
                url = f"{self.BASE_URL}/search.json"
                resp = self.session.get(url, params=params, timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    res_docs = data.get("docs", [])
                    if res_docs:
                        docs = res_docs
                        break
            except Exception as e:
                logger.warning(f"Open Library search failed for '{q_params}': {e}")

        works: List[Work] = []

        for doc in docs:
            work_key = doc.get("key", "")
            if not work_key.startswith("/works/"):
                work_key = f"/works/{work_key}" if work_key else ""

            title = doc.get("title", "Unknown Title")
            authors = doc.get("author_name", [])
            author_str = ", ".join(authors) if authors else "Unknown Author"

            isbns = doc.get("isbn", [])
            primary_isbn = isbns[0] if isinstance(isbns, list) and isbns else None

            work = Work(
                work_id=work_key,
                title=title,
                author=author_str,
                first_publish_year=doc.get("first_publish_year"),
                edition_count=doc.get("edition_count"),
                isbn=primary_isbn
            )

            # Rating from search document if available
            avg_rating = doc.get("ratings_average")
            rating_count = doc.get("ratings_count")

            if avg_rating is not None or rating_count is not None:
                work.ratings[self.name] = PlatformRating(
                    platform_name=self.name,
                    rate=float(avg_rating) if avg_rating is not None else None,
                    rating_count=int(rating_count) if rating_count is not None else 0,
                    url=f"{self.BASE_URL}{work_key}" if work_key else None
                )
            elif include_details:
                # Fetch rating explicitly via ratings endpoint
                rating = self.fetch_ratings(work)
                if rating:
                    work.ratings[self.name] = rating

            # Fetch editions for this work
            if include_details:
                work.editions = self.fetch_editions(work_key, limit=10)

            works.append(work)

        return works

    def fetch_ratings(self, work: Work) -> PlatformRating:
        """Fetch dedicated rating object from Open Library ratings endpoint."""
        work_id = work.work_id
        if not work_id:
            return PlatformRating(platform_name=self.name)

        try:
            url = f"{self.BASE_URL}{work_id}/ratings.json"
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                summary = data.get("summary", {})
                avg = summary.get("average")
                count = summary.get("count")
                return PlatformRating(
                    platform_name=self.name,
                    rate=float(avg) if avg is not None and avg > 0 else None,
                    rating_count=int(count) if count is not None else 0,
                    url=f"{self.BASE_URL}{work_id}"
                )
        except Exception as e:
            logger.debug(f"Failed to fetch ratings for {work_id}: {e}")

        return PlatformRating(platform_name=self.name)

    def fetch_editions(self, work_id: str, limit: int = 10) -> List[Edition]:
        """Fetch editions associated with a specific Work ID."""
        if not work_id:
            return []

        editions: List[Edition] = []
        try:
            url = f"{self.BASE_URL}{work_id}/editions.json"
            params = {"limit": limit}
            resp = self.session.get(url, params=params, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                entries = data.get("entries", [])
                for entry in entries:
                    edition_key = entry.get("key", "")
                    title = entry.get("title", "Untitled Edition")
                    publish_date = entry.get("publish_date")
                    
                    languages = entry.get("languages", [])
                    lang_str = None
                    if languages and isinstance(languages, list):
                        lang_keys = [l.get("key", "").split("/")[-1] for l in languages if isinstance(l, dict)]
                        lang_str = ", ".join(lang_keys)

                    isbns_13 = entry.get("isbn_13", [])
                    isbns_10 = entry.get("isbn_10", [])

                    edition = Edition(
                        edition_id=edition_key,
                        title=title,
                        publish_year=str(publish_date) if publish_date else None,
                        language=lang_str,
                        isbn_13=isbns_13[0] if isbns_13 else None,
                        isbn_10=isbns_10[0] if isbns_10 else None,
                        publisher=", ".join(entry.get("publishers", [])) if entry.get("publishers") else None
                    )
                    editions.append(edition)
        except Exception as e:
            logger.debug(f"Failed to fetch editions for {work_id}: {e}")

        return editions
