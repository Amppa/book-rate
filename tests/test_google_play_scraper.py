import unittest
from unittest.mock import MagicMock, patch

from book_rate.models import Work, SourceRating
from book_rate.sources.google_play import GooglePlaySource


class TestGooglePlayScraper(unittest.TestCase):

    def test_extract_volume_id_from_url(self):
        source = GooglePlaySource()

        
        # Test query parameter
        url1 = "https://books.google.com.tw/books?id=z2z_6hLoPmgC&dq=isbn:978957&hl=&source=gbs_api"
        self.assertEqual(source._extract_volume_id_from_url(url1), "z2z_6hLoPmgC")
        
        url2 = "https://play.google.com/store/books/details?id=ZuKTvERuPG8C&source=gbs_api"
        self.assertEqual(source._extract_volume_id_from_url(url2), "ZuKTvERuPG8C")
        
        # Test path parameter
        url3 = "https://play.google.com/store/books/details/z2z_6hLoPmgC"
        self.assertEqual(source._extract_volume_id_from_url(url3), "z2z_6hLoPmgC")
        
        # None cases
        self.assertIsNone(source._extract_volume_id_from_url(None))
        self.assertIsNone(source._extract_volume_id_from_url(""))

    @patch("book_rate.sources.google_play.GooglePlaySource._fetch_html")
    def test_fetch_google_play_rating_json_ld(self, mock_fetch_html):
        source = GooglePlaySource()
        
        # Mock HTML containing valid JSON-LD
        mock_fetch_html.return_value = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@context": "http://schema.org",
              "@type": "Book",
              "name": "Test Book",
              "aggregateRating": {
                "@type": "AggregateRating",
                "ratingValue": "4.7528",
                "ratingCount": "975"
              }
            }
            </script>
          </head>
        </html>
        """
        
        rate, count = source._parse_play_rating("test_id")
        self.assertEqual(rate, 4.7528)
        self.assertEqual(count, 975)

    @patch("book_rate.sources.google_play.GooglePlaySource._fetch_html")
    def test_fetch_google_play_rating_regex_fallback(self, mock_fetch_html):
        source = GooglePlaySource()
        
        # Mock HTML with malformed JSON-LD but matching regex tags
        mock_fetch_html.return_value = """
        <html>
          <body>
            <div>Some random text</div>
            "ratingValue" : "4.487"
            "ratingCount" : "630"
          </body>
        </html>
        """
        
        rate, count = source._parse_play_rating("test_id")
        self.assertEqual(rate, 4.487)
        self.assertEqual(count, 630)

    @patch("book_rate.sources.google_play.GooglePlaySource._fetch_html")
    def test_fetch_google_play_rating_failed(self, mock_fetch_html):
        source = GooglePlaySource()
        
        # Mock HTML containing no matching content
        mock_fetch_html.return_value = "<html><body>No ratings here</body></html>"
        
        rate, count = source._parse_play_rating("test_id")
        self.assertIsNone(rate)
        self.assertIsNone(count)

    @patch("book_rate.sources.google_play.GooglePlaySource._parse_play_rating")
    def test_fetch_ratings_direct(self, mock_parse_play):
        source = GooglePlaySource()
        
        # Setup mock for Play rating
        mock_parse_play.return_value = (4.487, 630)
        
        dummy_work = Work(work_id="gb:ZuKTvERuPG8C", title="Test Title", author="Test Author")
        
        # Execute
        result_rating = source.fetch_ratings(dummy_work)
        
        # Asserts
        self.assertEqual(result_rating.rate, 4.487)
        self.assertEqual(result_rating.rating_count, 630)
        self.assertEqual(result_rating.url, "https://play.google.com/store/books/details?id=ZuKTvERuPG8C")
        self.assertEqual(result_rating.status, "MATCH")
        mock_parse_play.assert_called_once_with("ZuKTvERuPG8C")


if __name__ == "__main__":
    unittest.main()

