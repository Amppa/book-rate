import unittest
from unittest.mock import MagicMock, patch

from book_rate.models import Work, SourceRating
from book_rate.sources.amazon import AmazonSource
from book_rate.sources.douban import DoubanSource
from book_rate.sources.goodreads import GoodreadsSource
from book_rate.sources.google_books import GoogleBooksSource


class TestNonExistentBookCase(unittest.TestCase):
    """Test Case 1: Non-existent book across sources (url=None, rate=None)."""

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

        source = AmazonSource()
        rating = source.fetch_ratings(self.dummy_work)

        self.assertEqual(rating.source_name, "Amazon")
        self.assertIsNone(rating.url)
        self.assertIsNone(rating.rate)
        self.assertIsNone(rating.rating_count)

    @patch("book_rate.sources.base.BaseSource._fetch_html")
    @patch("requests.Session.get")
    def test_douban_non_existent_book(self, mock_get, mock_fetch_html):
        mock_fetch_html.return_value = ""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_get.return_value = mock_resp

        source = DoubanSource()
        rating = source.fetch_ratings(self.dummy_work)

        self.assertEqual(rating.source_name, "Douban")
        self.assertIsNone(rating.url)
        self.assertIsNone(rating.rate)
        self.assertIsNone(rating.rating_count)

    @patch("requests.Session.get")
    def test_goodreads_non_existent_book(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_get.return_value = mock_resp

        source = GoodreadsSource()
        rating = source.fetch_ratings(self.dummy_work)

        self.assertEqual(rating.source_name, "Goodreads")
        self.assertIsNone(rating.url)
        self.assertIsNone(rating.rate)
        self.assertIsNone(rating.rating_count)

    @patch("requests.Session.get")
    def test_google_books_non_existent_book(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"totalItems": 0, "items": []}
        mock_get.return_value = mock_resp

        source = GoogleBooksSource()
        rating = source.fetch_ratings(self.dummy_work)

        self.assertEqual(rating.source_name, "Google Books")
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

        source = AmazonSource()
        rating = source.fetch_ratings(self.unrated_work)

        self.assertEqual(rating.source_name, "Amazon")
        self.assertIsNotNone(rating.url)
        self.assertIn("B000000111", rating.url)
        self.assertIsNone(rating.rate)
        self.assertIsNone(rating.rating_count)

    @patch("book_rate.sources.base.BaseSource._fetch_html")
    @patch("requests.Session.get")
    def test_douban_unrated_book_with_url(self, mock_get, mock_fetch_html):
        mock_fetch_html.return_value = ""
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

        source = DoubanSource()
        rating = source.fetch_ratings(self.unrated_work)

        self.assertEqual(rating.source_name, "Douban")
        self.assertIsNotNone(rating.url)
        self.assertEqual(rating.url, "https://book.douban.com/subject/999888777/")
        self.assertIsNone(rating.rate)
        self.assertIsNone(rating.rating_count)


    @patch("requests.Session.get")
    def test_books_tw_search_parsing(self, mock_get):
        from book_rate.sources.books_tw import BooksTwSource
        source = BooksTwSource()
        sample_html = '''
        <table class="table-search">
          <tr>
            <td>
              <h4><a target="_blank" rel="mid_name" href="//search.books.com.tw/redirect/move/item/0011032772/" title="牧羊少年奇幻之旅">牧羊少年奇幻之旅</a></h4>
              <ul class="list-date clearfix">
                <li><span>中文書</span> , <a rel='go_author' href='//search.books.com.tw/adv_author/1' title='保羅．科爾賀'>保羅．科爾賀</a>, 出版日期: 2025-10-07</li>
              </ul>
            </td>
          </tr>
        </table>
        '''
        items = source._parse_search_items(sample_html)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["book_id"], "0011032772")
        self.assertEqual(items[0]["author"], "保羅．科爾賀")
        self.assertEqual(items[0]["first_publish_year"], 2025)


if __name__ == "__main__":
    unittest.main()

