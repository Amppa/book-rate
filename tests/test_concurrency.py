import unittest
from unittest.mock import MagicMock, patch
from concurrent.futures import ThreadPoolExecutor

from book_rate.models import Work, SourceStatus
from book_rate.sources.base import BaseSource
from book_rate.sources.readmoo import ReadmooSource
from book_rate.sources.storygraph import StoryGraphSource


class TestFetchHtmlAndConcurrency(unittest.TestCase):
    @patch("subprocess.check_output")
    def test_fetch_html_curl_success(self, mock_check_output):
        """Test _fetch_html returns (html, True) when curl.exe succeeds."""
        mock_check_output.return_value = b"<html>curl html</html>"
        source = BaseSource()

        html, used_curl = source._fetch_html("http://example.com")
        self.assertEqual(html, "<html>curl html</html>")
        self.assertTrue(used_curl)

    @patch("subprocess.check_output", side_effect=Exception("curl missing"))
    def test_fetch_html_requests_fallback(self, mock_check_output):
        """Test _fetch_html returns (html, False) when curl fails and requests fallback succeeds."""
        source = BaseSource()
        mock_resp = MagicMock()
        mock_resp.text = "<html>requests html</html>"
        source.session.get = MagicMock(return_value=mock_resp)

        html, used_curl = source._fetch_html("http://example.com")
        self.assertEqual(html, "<html>requests html</html>")
        self.assertFalse(used_curl)

    def test_sequential_calls_status_isolation(self):
        """Test sequential calls on the same source instance do not bleed curl status."""
        source = ReadmooSource()
        work = Work(work_id="/works/OL1", title="Test Book", author="Test Author")

        search_html = """
        <li class="listItem-box">
          <div data-readmoo-id="12345">
            <h4 itemprop="name"><a class="product-link" title="Test Book">Test Book</a></h4>
            <div class="contributor-info"><a href="/author/1">Test Author</a></div>
            <div class="avg-rating">4.5</div>
          </div>
        </li>
        """
        detail_html = """
        <h1 class="book-detail-title">Test Book</h1>
        <div data-score="4.5"></div>
        <div itemprop="ratingCount">100</div>
        """

        def mock_fetch_html(url: str):
            if "/book/" in url:
                return detail_html, locals_used_curl[0]
            return search_html, locals_used_curl[0]

        # Call 1: used_curl = True
        locals_used_curl = [True]
        with patch.object(source, "_fetch_html", side_effect=lambda u: (detail_html if "/book/" in u else search_html, True)):
            rating1 = source.fetch_ratings(work, strategy="search_name")
            self.assertEqual(rating1.status, SourceStatus.CURL_MATCH.value)

        # Call 2: used_curl = False
        with patch.object(source, "_fetch_html", side_effect=lambda u: (detail_html if "/book/" in u else search_html, False)):
            rating2 = source.fetch_ratings(work, strategy="search_name")
            self.assertEqual(rating2.status, SourceStatus.MATCH.value)

    def test_concurrent_calls_status_isolation(self):
        """Test concurrent multi-threaded requests on the same source instance do not cross-contaminate."""
        source = ReadmooSource()
        work = Work(work_id="/works/OL1", title="Test Book", author="Test Author")

        search_html = """
        <li class="listItem-box">
          <div data-readmoo-id="12345">
            <h4 itemprop="name"><a class="product-link" title="Test Book">Test Book</a></h4>
            <div class="contributor-info"><a href="/author/1">Test Author</a></div>
            <div class="avg-rating">4.2</div>
          </div>
        </li>
        """
        detail_html = """
        <h1 class="book-detail-title">Test Book</h1>
        <div data-score="4.2"></div>
        <div itemprop="ratingCount">50</div>
        """

        def worker(thread_id: int):
            used_curl = (thread_id % 2 == 1)
            with patch.object(source, "_fetch_html", side_effect=lambda u: (detail_html if "/book/" in u else search_html, used_curl)):
                rating = source.fetch_ratings(work, strategy="search_name")
                expected_status = SourceStatus.CURL_MATCH.value if used_curl else SourceStatus.MATCH.value
                return thread_id, rating.status, expected_status

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker, i) for i in range(20)]
            results = [f.result() for f in futures]

        for thread_id, actual_status, expected_status in results:
            self.assertEqual(
                actual_status,
                expected_status,
                f"Thread {thread_id} status mismatch! Got {actual_status}, expected {expected_status}"
            )

    def test_storygraph_curl_status_propagation(self):
        """Test StoryGraphSource correctly propagates used_curl from detail/rating pages into rating status."""
        source = StoryGraphSource()
        work = Work(work_id="/works/OL1", title="Test Book", author="Test Author")

        search_html = """
        <a href="/books/11111111-2222-3333-4444-555555555555">Test Book</a>
        <a href="/authors/author1">Test Author</a>
        """
        detail_html = """
        <h3 class="text-2xl">Test Book</h3>
        <a href="/authors/author1">Test Author</a>
        """
        reviews_html = """
        <div aria-label="Book rating: 4.5 out of 5 stars based on 100 reviews"></div>
        """

        # Scenario 1: search page uses requests (used_curl=False), detail/community_reviews uses curl (used_curl=True)
        def mock_fetch_curl_on_detail(url: str):
            if "/community_reviews" in url:
                return reviews_html, True
            elif "/books/" in url:
                return detail_html, True
            return search_html, False

        with patch.object(source, "_fetch_html", side_effect=mock_fetch_curl_on_detail):
            works = source.search_works("Test Book")
            self.assertEqual(len(works), 1)
            self.assertEqual(works[0].ratings["StoryGraph"].status, SourceStatus.CURL_MATCH.value)

        # Scenario 2: all requests use requests (used_curl=False)
        def mock_fetch_requests_only(url: str):
            if "/community_reviews" in url:
                return reviews_html, False
            elif "/books/" in url:
                return detail_html, False
            return search_html, False

        with patch.object(source, "_fetch_html", side_effect=mock_fetch_requests_only):
            works2 = source.search_works("Test Book")
            self.assertEqual(len(works2), 1)
            self.assertEqual(works2[0].ratings["StoryGraph"].status, SourceStatus.MATCH.value)


if __name__ == "__main__":
    unittest.main()
