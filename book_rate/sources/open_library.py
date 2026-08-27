import logging
from typing import List, Optional

from book_rate.models import Work, Edition, SourceRating
from book_rate.sources.base import BaseSource
from book_rate.utils.isbn import clean_isbn

logger = logging.getLogger(__name__)


class OpenLibrarySource(BaseSource):
    """Source for querying Open Library works, editions, and ratings."""

    BASE_URL = "https://openlibrary.org"
    SEARCH_URL = "https://openlibrary.org/search.json"

    @property
    def name(self) -> str:
        return "Open Library"

    @property
    def enable_extend_editions(self) -> bool:
        return True

    def search_works(self, query: str, limit: int = 5, page: int = 1, include_details: bool = False) -> List[Work]:
        """Search Open Library for works matching query."""
        clean_query = query.strip()
        if not clean_query:
            return []

        params = {
            "q": clean_query,
            "limit": limit,
            "page": page,
            "fields": "key,title,author_name,first_publish_year,edition_count,isbn,ratings_average,ratings_count,publisher,publish_date,language"
        }

        try:
            resp = self._get(self.SEARCH_URL, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"Open Library search failed for '{query}': {e}")
            return []

        docs = data.get("docs", [])
        works: List[Work] = []

        for doc in docs:
            raw_key = doc.get("key", "")
            clean_key = raw_key.replace("/works/", "").strip()
            work_key = f"ol:{clean_key}" if clean_key else ""
            title = doc.get("title", "Unknown Title")
            authors = doc.get("author_name", [])
            author_str = ", ".join(authors) if authors else "Unknown Author"

            avg_rating = doc.get("ratings_average")
            rating_count = doc.get("ratings_count")

            isbns = doc.get("isbn", [])
            cleaned_isbn = clean_isbn(isbns[0]) if isbns else None

            publishers = doc.get("publisher", [])
            publisher_str = publishers[0] if publishers else None

            pub_dates = doc.get("publish_date", [])
            pub_date_str = pub_dates[0] if pub_dates else (str(doc.get("first_publish_year")) if doc.get("first_publish_year") else None)

            languages = doc.get("language", [])
            lang_str = languages[0] if languages else None
            ed_count = doc.get("edition_count", 0)

            work = Work(
                work_id=work_key,
                title=title,
                author=author_str,
                first_publish_year=doc.get("first_publish_year"),
                edition_count=ed_count,
                isbn=cleaned_isbn
            )

            work.ratings[self.name] = SourceRating(
                source_name=self.name,
                rate=float(avg_rating) if avg_rating is not None else None,
                rating_count=int(rating_count) if rating_count is not None else 0,
                url=f"{self.BASE_URL}/works/{clean_key}" if clean_key else None,
                title=title,
                author=author_str if author_str != "Unknown Author" else None,
                publisher=publisher_str,
                publish_date=pub_date_str,
                isbn=cleaned_isbn,
                language=lang_str,
                work_id=work_key if work_key else None,
                edition_count=ed_count
            )

            if include_details:
                work.editions = self.fetch_editions(work_key, limit=10)

            works.append(work)

        return works

    @property
    def default_strategy(self) -> str:
        return "search_name"

    def fetch_ratings(self, work: Work, strategy: Optional[str] = None) -> SourceRating:
        """Fetch dedicated rating object from Open Library ratings endpoint or via strategy."""
        work_id = work.work_id or ""
        strat = strategy or self.default_strategy
        if "OL" in work_id.upper():
            clean_id = work_id.replace("ol:", "").replace("/works/", "").strip()
            full_id = f"/works/{clean_id}"
            try:
                url = f"{self.BASE_URL}{full_id}/ratings.json"
                resp = self._get(url, timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    summary = data.get("summary", {})
                    avg = summary.get("average")
                    count = summary.get("count")
                    return SourceRating(
                        source_name=self.name,
                        rate=float(avg) if avg is not None and avg > 0 else None,
                        rating_count=int(count) if count is not None else 0,
                        url=f"{self.BASE_URL}{full_id}",
                        strategy=strat,
                        query=work_id,
                        status="MATCH" if (avg or count) else "NO_MATCH"
                    )
            except Exception as e:
                logger.debug(f"Failed to fetch ratings for {full_id}: {e}")

        return self._fetch_ratings(work, strategy=strategy)

    def fetch_editions(self, work_id: str, limit: int = 10) -> List[Edition]:
        """Fetch editions associated with a specific Work ID."""
        if not work_id:
            return []

        clean_id = work_id.replace("ol:", "").replace("/works/", "").strip()
        full_id = f"/works/{clean_id}"
        editions: List[Edition] = []
        safe_limit = min(max(1, limit), 1000)

        try:
            url = f"{self.BASE_URL}{full_id}/editions.json"
            resp = self._get(url, params={"limit": safe_limit}, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()

            for entry in data.get("entries", []):
                ed_key = entry.get("key", "")
                title = entry.get("title", "Unknown Title")
                pub_date = entry.get("publish_date")
                publishers = entry.get("publishers", [])
                pub_str = publishers[0] if publishers else None

                languages = entry.get("languages", [])
                lang_str = None
                if languages:
                    lang_str = ",".join(
                        l.get("key", "").replace("/languages/", "")
                        for l in languages if isinstance(l, dict)
                    )

                isbns_13 = entry.get("isbn_13", [])
                isbns_10 = entry.get("isbn_10", [])

                isbn_13 = clean_isbn(isbns_13[0]) if isbns_13 else None
                isbn_10 = clean_isbn(isbns_10[0]) if isbns_10 else None

                edition = Edition(
                    edition_id=ed_key,
                    title=title,
                    publish_year=pub_date,
                    publisher=pub_str,
                    language=lang_str,
                    isbn_13=isbn_13,
                    isbn_10=isbn_10
                )
                editions.append(edition)

        except Exception as e:
            logger.debug(f"Failed to fetch editions for {full_id}: {e}")

        return editions
