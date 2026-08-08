import logging
from typing import List, Optional, Dict
from book_rate.models import Work, SourceRating
from book_rate.sources.open_library import OpenLibrarySource
from book_rate.sources.google_books import GoogleBooksSource
from book_rate.sources.goodreads import GoodreadsSource
from book_rate.sources.douban import DoubanSource
from book_rate.sources.amazon import AmazonSource
from book_rate.sources.amazon_jp import AmazonJPSource
from book_rate.sources.storygraph import StoryGraphSource
from book_rate.sources.readmoo import ReadmooSource

logger = logging.getLogger(__name__)


class BookAggregator:
    """Aggregates book works, editions, and ratings across multiple sources."""

    def __init__(self, google_api_key: Optional[str] = None):
        self.open_library = OpenLibrarySource()
        self.google_books = GoogleBooksSource(api_key=google_api_key)
        self.goodreads = GoodreadsSource()
        self.douban = DoubanSource()
        self.amazon = AmazonSource()
        self.amazon_jp = AmazonJPSource()
        self.storygraph = StoryGraphSource()
        self.readmoo = ReadmooSource()

    def aggregate_by_title(self, title_query: str, limit: int = 5) -> List[Work]:
        """
        Search for a book by title, resolve corresponding Works and Editions,
        and fetch rating metrics across all sources.
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
                work.ratings[self.google_books.name] = gb_rating or SourceRating(source_name=self.google_books.name)

            # Enrich with Open Library rating
            if self.open_library.name not in work.ratings:
                ol_rating = self.open_library.fetch_ratings(work)
                work.ratings[self.open_library.name] = ol_rating or SourceRating(source_name=self.open_library.name)

            # Enrich with Goodreads rating
            if self.goodreads.name not in work.ratings:
                gr_rating = self.goodreads.fetch_ratings(work)
                work.ratings[self.goodreads.name] = gr_rating or SourceRating(source_name=self.goodreads.name)

            # Enrich with Douban rating
            if self.douban.name not in work.ratings:
                db_rating = self.douban.fetch_ratings(work)
                work.ratings[self.douban.name] = db_rating or SourceRating(source_name=self.douban.name)

            # Enrich with Amazon rating
            if self.amazon.name not in work.ratings:
                am_rating = self.amazon.fetch_ratings(work)
                work.ratings[self.amazon.name] = am_rating or SourceRating(source_name=self.amazon.name)

            # Enrich with Amazon JP rating
            if self.amazon_jp.name not in work.ratings:
                amjp_rating = self.amazon_jp.fetch_ratings(work)
                work.ratings[self.amazon_jp.name] = amjp_rating or SourceRating(source_name=self.amazon_jp.name)

            # Enrich with StoryGraph rating
            if self.storygraph.name not in work.ratings:
                sg_rating = self.storygraph.fetch_ratings(work)
                work.ratings[self.storygraph.name] = sg_rating or SourceRating(source_name=self.storygraph.name)

            # Enrich with Readmoo rating
            if self.readmoo.name not in work.ratings:
                rm_rating = self.readmoo.fetch_ratings(work)
                work.ratings[self.readmoo.name] = rm_rating or SourceRating(source_name=self.readmoo.name)

            aggregated_works.append(work)

        return aggregated_works
