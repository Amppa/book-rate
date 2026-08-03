import logging
from typing import List, Optional, Dict
from book_rate.models import Work, PlatformRating
from book_rate.providers.open_library import OpenLibraryProvider
from book_rate.providers.google_books import GoogleBooksProvider
from book_rate.providers.goodreads import GoodreadsProvider
from book_rate.providers.douban import DoubanProvider
from book_rate.providers.amazon import AmazonProvider
from book_rate.providers.amazon_jp import AmazonJPProvider
from book_rate.providers.storygraph import StoryGraphProvider
from book_rate.providers.readmoo import ReadmooProvider

logger = logging.getLogger(__name__)


class BookAggregator:
    """Aggregates book works, editions, and ratings across multiple providers."""

    def __init__(self, google_api_key: Optional[str] = None):
        self.open_library = OpenLibraryProvider()
        self.google_books = GoogleBooksProvider(api_key=google_api_key)
        self.goodreads = GoodreadsProvider()
        self.douban = DoubanProvider()
        self.amazon = AmazonProvider()
        self.amazon_jp = AmazonJPProvider()
        self.storygraph = StoryGraphProvider()
        self.readmoo = ReadmooProvider()

    def aggregate_by_title(self, title_query: str, limit: int = 5) -> List[Work]:
        """
        Search for a book by title, resolve corresponding Works and Editions,
        and fetch rating metrics across all providers.
        """
        clean_query = title_query.strip()
        if not clean_query:
            return []

        # 1. Primary search via Open Library for Work entities
        ol_works = self.open_library.search_works(clean_query, limit=limit)
        
        # 2. Search Google Books for additional works / volume ratings
        gb_works = self.google_books.search_works(clean_query, limit=limit)

        aggregated_works: List[Work] = []

        target_works = ol_works or gb_works

        for work in target_works:
            # Enrich with Google Books rating
            if self.google_books.name not in work.ratings:
                gb_rating = self.google_books.fetch_ratings(work)
                work.ratings[self.google_books.name] = gb_rating or PlatformRating(platform_name=self.google_books.name)

            # Enrich with Open Library rating
            if self.open_library.name not in work.ratings:
                ol_rating = self.open_library.fetch_ratings(work)
                work.ratings[self.open_library.name] = ol_rating or PlatformRating(platform_name=self.open_library.name)

            # Enrich with Goodreads rating
            if self.goodreads.name not in work.ratings:
                gr_rating = self.goodreads.fetch_ratings(work)
                work.ratings[self.goodreads.name] = gr_rating or PlatformRating(platform_name=self.goodreads.name)

            # Enrich with Douban rating
            if self.douban.name not in work.ratings:
                db_rating = self.douban.fetch_ratings(work)
                work.ratings[self.douban.name] = db_rating or PlatformRating(platform_name=self.douban.name)

            # Enrich with Amazon rating
            if self.amazon.name not in work.ratings:
                am_rating = self.amazon.fetch_ratings(work)
                work.ratings[self.amazon.name] = am_rating or PlatformRating(platform_name=self.amazon.name)

            # Enrich with Amazon JP rating
            if self.amazon_jp.name not in work.ratings:
                amjp_rating = self.amazon_jp.fetch_ratings(work)
                work.ratings[self.amazon_jp.name] = amjp_rating or PlatformRating(platform_name=self.amazon_jp.name)

            # Enrich with StoryGraph rating
            if self.storygraph.name not in work.ratings:
                sg_rating = self.storygraph.fetch_ratings(work)
                work.ratings[self.storygraph.name] = sg_rating or PlatformRating(platform_name=self.storygraph.name)

            # Enrich with Readmoo rating
            if self.readmoo.name not in work.ratings:
                rm_rating = self.readmoo.fetch_ratings(work)
                work.ratings[self.readmoo.name] = rm_rating or PlatformRating(platform_name=self.readmoo.name)

            aggregated_works.append(work)

        return aggregated_works
