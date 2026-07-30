import unittest
from unittest.mock import MagicMock, patch

from book_rate.models import Work, PlatformRating
from book_rate.providers.amazon import AmazonProvider
from book_rate.providers.douban import DoubanProvider
from book_rate.providers.goodreads import GoodreadsProvider
from book_rate.providers.google_books import GoogleBooksProvider


class TestNonExistentBookCase(unittest.TestCase):
    """Test Case 1: Non-existent book across providers (url=None, rate=None)."""

    def setUp(self):
        self.dummy_work = Work(
            work_id="non_existent_123",
            title="NonExistentBook_XYZ999",
            author="UnknownAuthor_XYZ999"
        )

    @patch("requests.Session.get")
    def test_amazon_non_existent_book(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body><div>No results found for your search</div></body></html>"
        mock_get.return_value = mock_resp

        provider = AmazonProvider()
        rating = provider.fetch_ratings(self.dummy_work)

        self.assertEqual(rating.platform_name, "Amazon")
        self.assertIsNone(rating.url)
        self.assertIsNone(rating.rate)
        self.assertIsNone(rating.rating_count)

    @patch("requests.Session.get")
    def test_douban_non_existent_book(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_get.return_value = mock_resp

        provider = DoubanProvider()
        rating = provider.fetch_ratings(self.dummy_work)

        self.assertEqual(rating.platform_name, "Douban")
        self.assertIsNone(rating.url)
        self.assertIsNone(rating.rate)
        self.assertIsNone(rating.rating_count)

    @patch("requests.Session.get")
    def test_goodreads_non_existent_book(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_get.return_value = mock_resp

        provider = GoodreadsProvider()
        rating = provider.fetch_ratings(self.dummy_work)

        self.assertEqual(rating.platform_name, "Goodreads")
        self.assertIsNone(rating.url)
        self.assertIsNone(rating.rate)
        self.assertIsNone(rating.rating_count)

    @patch("requests.Session.get")
    def test_google_books_non_existent_book(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"totalItems": 0, "items": []}
        mock_get.return_value = mock_resp

        provider = GoogleBooksProvider()
        rating = provider.fetch_ratings(self.dummy_work)

        self.assertEqual(rating.platform_name, "Google Books")
        self.assertIsNone(rating.url)
        self.assertIsNone(rating.rate)
        self.assertIsNone(rating.rating_count)


class TestUnratedBookWithUrlCase(unittest.TestCase):
    """Test Case 2: Book exists (url is present), but has no rating score (rate=None)."""

    def setUp(self):
        self.unrated_work = Work(
            work_id="unrated_book_123",
            title="Unrated Modern Novel",
            author="New Author"
        )

    @patch("requests.Session.get")
    def test_amazon_unrated_book_with_url(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # HTML containing search result card and ASIN link, but NO star ratings
        mock_resp.text = '''
        <div data-component-type="s-search-result">
          <h2><a href="/Unrated-Novel/dp/B000000111"><span>Unrated Modern Novel</span></a></h2>
          by New Author
        </div>
        '''
        mock_get.return_value = mock_resp

        provider = AmazonProvider()
        rating = provider.fetch_ratings(self.unrated_work)

        self.assertEqual(rating.platform_name, "Amazon")
        self.assertIsNotNone(rating.url)
        self.assertIn("B000000111", rating.url)
        self.assertIsNone(rating.rate)
        self.assertIsNone(rating.rating_count)

    @patch("requests.Session.get")
    def test_douban_unrated_book_with_url(self, mock_get):
        def side_effect(url, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            if "subject_suggest" in url:
                mock_resp.json.return_value = [
                    {
                        "id": "999888777",
                        "title": "Unrated Modern Novel",
                        "author_name": "New Author",
                        "url": "https://book.douban.com/subject/999888777/"
                    }
                ]
            else:
                # Subject detail HTML without rating average or votes
                mock_resp.text = "<html><body><h1>Unrated Modern Novel</h1><div>目前無評價數據</div></body></html>"
            return mock_resp

        mock_get.side_effect = side_effect

        provider = DoubanProvider()
        rating = provider.fetch_ratings(self.unrated_work)

        self.assertEqual(rating.platform_name, "Douban")
        self.assertIsNotNone(rating.url)
        self.assertEqual(rating.url, "https://book.douban.com/subject/999888777/")
        self.assertIsNone(rating.rate)
        self.assertIsNone(rating.rating_count)


if __name__ == "__main__":
    unittest.main()
