import logging
from typing import List, Optional, Dict
from book_rate.models import Work, PlatformRating
from book_rate.providers.open_library import OpenLibraryProvider
from book_rate.providers.google_books import GoogleBooksProvider

logger = logging.getLogger(__name__)


class BookAggregator:
    """Aggregates book works, editions, and ratings across multiple providers."""

    def __init__(self, google_api_key: Optional[str] = None):
        self.open_library = OpenLibraryProvider()
        self.google_books = GoogleBooksProvider(api_key=google_api_key)

    def aggregate_by_title(self, title_query: str, limit: int = 5) -> List[Work]:
        """
        Search for a book by title, resolve corresponding Works and Editions,
        and fetch rating metrics across all providers (Open Library & Google Books).
        """
        clean_query = title_query.strip()
        if not clean_query:
            return []

        # 1. Primary search via Open Library for Work entities
        ol_works = self.open_library.search_works(clean_query, limit=limit)
        
        # 2. Search Google Books for additional works / volume ratings
        gb_works = self.google_books.search_works(clean_query, limit=limit)

        aggregated_works: List[Work] = []

        if ol_works:
            for ol_work in ol_works:
                # Enrich with Google Books ratings by checking ISBNs or Title/Author
                gb_rating = self.google_books.fetch_ratings(ol_work)
                if gb_rating and (gb_rating.rate is not None or gb_rating.rating_count is not None):
                    ol_work.ratings[self.google_books.name] = gb_rating
                elif not self.google_books.name in ol_work.ratings:
                    ol_work.ratings[self.google_books.name] = PlatformRating(platform_name=self.google_books.name)

                # Ensure Open Library rating is populated
                if not self.open_library.name in ol_work.ratings:
                    ol_work.ratings[self.open_library.name] = PlatformRating(platform_name=self.open_library.name)

                aggregated_works.append(ol_work)

        # If Open Library yielded no works, fallback to Google Books items
        if not aggregated_works and gb_works:
            for gb_work in gb_works:
                if not self.open_library.name in gb_work.ratings:
                    gb_work.ratings[self.open_library.name] = PlatformRating(platform_name=self.open_library.name)
                aggregated_works.append(gb_work)

        return aggregated_works
