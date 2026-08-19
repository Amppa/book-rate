import time
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from book_rate.models import Work, SourceRating, SourceStatus, RatingRequestPayload
from book_rate.utils.rate_limiter import DomainRateLimiter
from book_rate.sources.base import BaseSource, SearchStrategy
from book_rate.sources.douban import DoubanSource
from book_rate.sources.books_tw import BooksTwSource
from book_rate.sources.amazon import AmazonSource, AmazonJPSource
from server import app


class DummyTestEngine(BaseSource):
    @property
    def name(self) -> str:
        return "DummyEngine"

    def search_works(self, query: str, limit: int = 5, page: int = 1):
        return []


class TestRateLimiterAndAntiBlocking(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_domain_rate_limiter_cooldown(self):
        """Verify DomainRateLimiter properly sleeps when requests are too close."""
        limiter = DomainRateLimiter(default_cooldown=0.2, jitter_range=(0.0, 0.05))
        key = "test_domain"

        t0 = time.time()
        limiter.wait_if_needed(key, custom_cooldown=0.2)
        # Second call immediately after
        limiter.wait_if_needed(key, custom_cooldown=0.2)
        elapsed = time.time() - t0

        self.assertGreaterEqual(elapsed, 0.2)

    def test_query_deduplication(self):
        """Verify BaseSource._deduplicate_queries removes spaces and punctuation duplicates."""
        raw_titles = [
            "  The Lord of the Rings  ",
            "The Lord of the Rings",
            "魔戒：王者再臨",
            "魔戒: 王者再臨",
            "",
            "   ",
            "魔戒：王者再臨"
        ]
        unique = BaseSource._deduplicate_queries(raw_titles)
        self.assertEqual(len(unique), 2)
        self.assertEqual(unique[0], "The Lord of the Rings")
        self.assertEqual(unique[1], "魔戒：王者再臨")

    def test_single_query_evaluation_statuses(self):
        """Verify _evaluate_single_query returns exact status for MATCH, UNRATED, and NOT_FOUND."""
        engine = DummyTestEngine()

        # 1. Match with score
        work_match = Work(work_id="d:1", title="Book Match", author="Author")
        work_match.ratings["DummyEngine"] = SourceRating(
            source_name="DummyEngine",
            rate=4.5,
            rating_count=100,
            url="https://dummy.com/1",
            title="Book Match"
        )
        r_match = engine._evaluate_single_query("Book Match", SearchStrategy.TITLE_LIST, lambda q: [work_match])
        self.assertEqual(r_match.status, SourceStatus.MATCH.value)
        self.assertEqual(r_match.rate, 4.5)

        # 2. Unrated with URL
        work_unrated = Work(work_id="d:2", title="Book Unrated", author="Author")
        work_unrated.ratings["DummyEngine"] = SourceRating(
            source_name="DummyEngine",
            rate=None,
            rating_count=None,
            url="https://dummy.com/2",
            title="Book Unrated"
        )
        r_unrated = engine._evaluate_single_query("Book Unrated", SearchStrategy.TITLE_LIST, lambda q: [work_unrated])
        self.assertEqual(r_unrated.status, SourceStatus.UNRATED.value)

        # 3. Not found
        r_none = engine._evaluate_single_query("Nonexistent", SearchStrategy.TITLE_LIST, lambda q: [])
        self.assertEqual(r_none.status, SourceStatus.NO_MATCH.value)

    def test_sources_default_cooldown(self):
        """Verify Douban, Books.com.tw, Amazon, and Amazon JP have default cooldown set to 1.0s."""
        db = DoubanSource()
        bk = BooksTwSource()
        am = AmazonSource()
        am_jp = AmazonJPSource()
        self.assertEqual(db.cooldown, 1.0)
        self.assertEqual(bk.cooldown, 1.0)
        self.assertEqual(am.cooldown, 1.0)
        self.assertEqual(am_jp.cooldown, 1.0)
        self.assertIn("Referer", db.session.headers)
        self.assertIn("Referer", bk.session.headers)

    @patch.object(AmazonSource, "_fetch_html")
    def test_amazon_search_works_with_fetch_html(self, mock_fetch):
        """Verify AmazonSource.search_works uses _fetch_html and parses item block correctly."""
        sample_html = '''
        <div data-component-type="s-search-result">
            <h2><span class="a-size-medium">Dune: Deluxe Edition</span></h2>
            <a href="/dp/0441013597">Link</a>
            <span>by <a href="/author">Frank Herbert</a></span>
            <span>4.8 out of 5 stars</span>
            <a href="#customerReviews"><span>12,345</span></a>
        </div>
        '''
        mock_fetch.return_value = (sample_html, True)
        am = AmazonSource()
        works = am.search_works("Dune")
        self.assertEqual(len(works), 1)
        self.assertEqual(works[0].title, "Dune: Deluxe Edition")
        self.assertEqual(works[0].author, "Frank Herbert")
        self.assertEqual(works[0].work_id, "am:0441013597")
        self.assertEqual(works[0].ratings["Amazon"].rate, 4.8)
        self.assertEqual(works[0].ratings["Amazon"].rating_count, 12345)

    @patch("server.aggregator.search_works")
    def test_api_search_cooldown_param(self, mock_search):
        """Verify /api/search accepts cooldown parameter and updates source instance cooldown."""
        mock_search.return_value = []
        response = self.client.get("/api/search?q=test&engines=douban,books_tw&cooldown=0.5")
        self.assertEqual(response.status_code, 200)
        from server import aggregator
        self.assertEqual(aggregator.douban.cooldown, 0.5)
        self.assertEqual(aggregator.books_tw.cooldown, 0.5)

    def test_full_list_ratings_collection(self):
        """Verify _fetch_full_list_ratings collects individual query results with distinct statuses."""
        engine = DummyTestEngine()
        work1 = Work(work_id="d:1", title="Title 1", author="A")
        work1.ratings["DummyEngine"] = SourceRating(source_name="DummyEngine", rate=4.2, rating_count=10, url="http://1", title="Title 1")

        def mock_search(q):
            if q == "Title 1":
                return [work1]
            return []

        res = engine._fetch_full_list_ratings(["Title 1", "Title 2"], SearchStrategy.TITLE_LIST_FULL, mock_search)
        self.assertEqual(len(res.results), 2)
        self.assertEqual(res.results[0]["status"], SourceStatus.MATCH.value)
        self.assertEqual(res.results[1]["status"], SourceStatus.NO_MATCH.value)


if __name__ == "__main__":
    unittest.main()
