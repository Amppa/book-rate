import unittest
from unittest.mock import MagicMock, patch
from book_rate.models import Work, Edition
from book_rate.sources.amazon import AmazonSource


class TestAmazonSource(unittest.TestCase):

    def setUp(self):
        self.source = AmazonSource()

    def test_source_name(self):
        self.assertEqual(self.source.name, "Amazon")

    @patch("requests.Session.get")
    def test_search_works_parsing(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '''
        <div data-component-type="s-search-result" data-asin="B0875.">
          <h2><a href="/dp/B0875"><span>Atomic Habits</span></a></h2>
          by <a href="/James-Clear">James Clear</a>
          <span>4.8 out of 5 stars</span>
          <span class="a-size-base s-underline-text">125,000</span>
        </div>
        '''
        mock_get.return_value = mock_resp

        works = self.source.search_works("Atomic Habits")
        self.assertTrue(len(works) > 0)
        self.assertEqual(works[0].title, "Atomic Habits")
        self.assertEqual(works[0].author, "James Clear")
        rating = works[0].ratings.get("Amazon")
        self.assertIsNotNone(rating)
        self.assertEqual(rating.rate, 4.8)
        self.assertEqual(rating.rating_count, 125000)

    @patch("requests.Session.get")
    def test_fetch_ratings_fallback(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        work = Work(work_id="ol1", title="Test Book", author="Test Author")
        rating = self.source.fetch_ratings(work)
        self.assertEqual(rating.source_name, "Amazon")
        self.assertIsNone(rating.rate)
        self.assertIsNone(rating.rating_count)


if __name__ == "__main__":
    unittest.main()
