import unittest
from unittest.mock import MagicMock, patch
from book_rate.models import Work
from book_rate.sources.amazon import AmazonSource, AmazonJPSource


class TestAmazonSource(unittest.TestCase):

    def test_source_name_us(self):
        source = AmazonSource()
        self.assertEqual(source.name, "Amazon")
        self.assertEqual(source.SEARCH_URL, "https://www.amazon.com/s")

    def test_source_name_jp(self):
        source = AmazonJPSource()
        self.assertEqual(source.name, "Amazon JP")
        self.assertEqual(source.SEARCH_URL, "https://www.amazon.co.jp/s")

    @patch("requests.Session.get")
    def test_search_works_parsing_us(self, mock_get):
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

        source = AmazonSource()
        works = source.search_works("Atomic Habits")
        self.assertTrue(len(works) > 0)
        self.assertEqual(works[0].title, "Atomic Habits")
        self.assertEqual(works[0].author, "James Clear")
        rating = works[0].ratings.get("Amazon")
        self.assertIsNotNone(rating)
        self.assertEqual(rating.rate, 4.8)
        self.assertEqual(rating.rating_count, 125000)

    @patch("requests.Session.get")
    def test_search_works_parsing_jp(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '''
        <div data-component-type="s-search-result" data-asin="4150119876">
          <h2><span>リーダブルコード</span></h2>
          著者 : <a href="/author">Dustin Boswell</a>
          <span>5つ星のうち4.6</span>
          <span class="a-size-base s-underline-text">3,800</span>
        </div>
        '''
        mock_get.return_value = mock_resp

        source = AmazonJPSource()
        works = source.search_works("リーダブルコード")
        self.assertTrue(len(works) > 0)
        self.assertEqual(works[0].title, "リーダブルコード")
        self.assertEqual(works[0].author, "Dustin Boswell")
        rating = works[0].ratings.get("Amazon JP")
        self.assertIsNotNone(rating)
        self.assertEqual(rating.rate, 4.6)
        self.assertEqual(rating.rating_count, 3800)

    @patch("requests.Session.get")
    def test_search_works_waf_challenge(self, mock_get):
        from book_rate.sources.base import SourceNetworkError
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '''
        <!DOCTYPE html><html><head>
        <meta http-equiv="refresh" content="5; URL='/s?k=test&bm-verify=AAQAAAAN'" />
        </head><body><script>function triggerInterstitialChallenge(){}</script></body></html>
        '''
        mock_get.return_value = mock_resp

        source = AmazonJPSource()
        with self.assertRaises(SourceNetworkError) as ctx:
            source.search_works("モリー先生との火曜日")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("WAF Challenge", str(ctx.exception))

    @patch("requests.Session.get")
    def test_fetch_ratings_fallback(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        source = AmazonSource()
        work = Work(work_id="ol1", title="Test Book", author="Test Author")
        rating = source.fetch_ratings(work)
        self.assertEqual(rating.source_name, "Amazon")
        self.assertIsNone(rating.rate)
        self.assertIsNone(rating.rating_count)


if __name__ == "__main__":
    unittest.main()
