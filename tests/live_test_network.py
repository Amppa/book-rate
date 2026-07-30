import os
import time
import unittest

from book_rate.models import Work, Edition
from book_rate.providers.open_library import OpenLibraryProvider
from book_rate.providers.google_books import GoogleBooksProvider
from book_rate.providers.goodreads import GoodreadsProvider
from book_rate.providers.douban import DoubanProvider
from book_rate.providers.amazon import AmazonProvider
from book_rate.aggregator import BookAggregator


class TestLiveNetworkIntegration(unittest.TestCase):
    """
    Live Network Integration Tests sending REAL HTTP requests to external book providers.
    Run explicitly via: python -m unittest tests/live_test_network.py
    Guaranteed test book: 'Thinking, Fast and Slow' / '快思慢想' (ISBN: 9780374275631)
    """

    def setUp(self):
        time.sleep(0.5)  # Slight delay to prevent aggressive rate limiting across tests
        self.guaranteed_work = Work(
            work_id="/works/OL27479W",
            title="Thinking, Fast and Slow",
            author="Daniel Kahneman",
            editions=[
                Edition(
                    edition_id="OL24865249M",
                    title="Thinking, Fast and Slow",
                    isbn_13="9780374275631"
                )
            ]
        )
        self.guaranteed_zh_work = Work(
            work_id="db:22366506",
            title="快思慢想",
            author="丹尼爾·卡內曼",
            editions=[
                Edition(
                    edition_id="OL25368367M",
                    title="快思慢想",
                    isbn_13="9789863200611"
                )
            ]
        )

    def test_live_open_library_search_and_ratings(self):
        provider = OpenLibraryProvider(timeout=15)
        works = provider.search_works("Thinking, Fast and Slow", limit=1)
        self.assertTrue(len(works) > 0, "Live Open Library search returned 0 results")
        self.assertIn("Thinking", works[0].title)

        rating = provider.fetch_ratings(self.guaranteed_work)
        self.assertEqual(rating.platform_name, "Open Library")
        self.assertIsNotNone(rating.url)

    def test_live_google_books_search_and_ratings(self):
        api_key = os.getenv("GOOGLE_BOOKS_API_KEY")
        provider = GoogleBooksProvider(api_key=api_key, timeout=15)
        works = provider.search_works("Thinking, Fast and Slow", limit=1)
        
        if provider.quota_exceeded:
            self.skipTest("Google Books API public quota exceeded (HTTP 429)")
        
        self.assertTrue(len(works) > 0, "Live Google Books search returned 0 results")
        rating = provider.fetch_ratings(self.guaranteed_work)
        self.assertEqual(rating.platform_name, "Google Books")

    def test_live_goodreads_search_and_ratings(self):
        provider = GoodreadsProvider(timeout=15)
        works = provider.search_works("Atomic Habits", limit=1)
        self.assertTrue(len(works) > 0, "Live Goodreads search returned 0 results")
        self.assertIn("Goodreads", works[0].ratings)

        rating = provider.fetch_ratings(self.guaranteed_work)
        self.assertEqual(rating.platform_name, "Goodreads")
        self.assertIsNotNone(rating.url)
        self.assertIsNotNone(rating.rate)
        self.assertGreater(rating.rate, 3.5)

    def test_live_douban_search_and_ratings(self):
        provider = DoubanProvider(timeout=15)
        works = provider.search_works("快思慢想", limit=1)
        if not works:
            self.skipTest("Live Douban anti-bot block / timeout triggered")

        self.assertTrue(len(works) > 0, "Live Douban search returned 0 results")
        self.assertIsNotNone(works[0].ratings.get("Douban"))

        rating = provider.fetch_ratings(works[0])
        self.assertEqual(rating.platform_name, "Douban")
        self.assertIsNotNone(rating.url)

    def test_live_amazon_search_and_ratings(self):
        provider = AmazonProvider(timeout=15)
        works = provider.search_works("Thinking, Fast and Slow Daniel Kahneman", limit=1)
        if not works:
            self.skipTest("Live Amazon anti-bot captcha / block triggered")

        self.assertTrue(len(works) > 0)
        rating = provider.fetch_ratings(self.guaranteed_work)
        self.assertEqual(rating.platform_name, "Amazon")
        if rating.url is not None:
            self.assertIn("amazon.com", rating.url)

    def test_live_book_aggregator(self):
        api_key = os.getenv("GOOGLE_BOOKS_API_KEY")
        aggregator = BookAggregator(google_api_key=api_key)
        works = aggregator.aggregate_by_title("Thinking, Fast and Slow", limit=1)
        self.assertTrue(len(works) > 0, "Live BookAggregator returned 0 works")
        w = works[0]
        self.assertIn("Open Library", w.ratings)


if __name__ == "__main__":
    unittest.main()
