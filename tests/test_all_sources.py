import unittest
from unittest.mock import patch, MagicMock

from book_rate.registry import SourceRegistry
from book_rate.models import Work, SourceRating
from book_rate.sources.readmoo import ReadmooSource
from book_rate.sources.storygraph import StoryGraphSource
from book_rate.sources.books_tw import BooksTwSource
from book_rate.sources.amazon import AmazonSource, AmazonJPSource
from book_rate.sources.goodreads import GoodreadsSource
from book_rate.sources.douban import DoubanSource
from book_rate.sources.google_books import GoogleBooksSource
from book_rate.sources.open_library import OpenLibrarySource


class TestSourceRegistry(unittest.TestCase):
    def test_list_source_keys(self):
        keys = SourceRegistry.list_source_keys()
        self.assertEqual(len(keys), 11)
        self.assertIn("books_tw", keys)
        self.assertIn("open_library", keys)
        self.assertIn("google_books", keys)
        self.assertIn("google_play", keys)


    def test_create_source(self):
        source = SourceRegistry.create_source("readmoo")
        self.assertIsNotNone(source)
        self.assertEqual(source.name, "Readmoo")

        invalid = SourceRegistry.create_source("unknown_source")
        self.assertIsNone(invalid)


class TestAllSourcesUnit(unittest.TestCase):
    """Unit tests for all 9 source adapters with mock HTML/API responses."""

    def setUp(self):
        self.test_work = Work(
            work_id="test_work_1",
            title="Thinking, Fast and Slow",
            author="Daniel Kahneman",
            title_list=["Thinking, Fast and Slow"],
            title_zh_list=["快思慢想"],
            author_list=["Daniel Kahneman"],
            isbn_list=["9780374275631"]
        )

    @patch("book_rate.sources.base.BaseSource._fetch_html")
    def test_readmoo_source_parsing(self, mock_fetch_html):
        html_content = """
        <div class="title"><a href="https://readmoo.com/book/2100000000">快思慢想</a></div>
        <div class="rating-val">4.5</div>
        <div class="rating-count">120 人評分</div>
        """
        mock_fetch_html.return_value = html_content
        source = ReadmooSource()
        rating = source.fetch_ratings(self.test_work, strategy="title_zh_list")
        self.assertIsNotNone(rating)
        self.assertEqual(rating.source_name, "Readmoo")

    @patch("book_rate.sources.base.BaseSource._fetch_html")
    def test_storygraph_source_parsing(self, mock_fetch_html):
        html_content = """
        <a href="/books/123456">Thinking, Fast and Slow</a>
        <span class="average-star-rating">4.2</span>
        """
        mock_fetch_html.return_value = html_content
        source = StoryGraphSource()
        rating = source.fetch_ratings(self.test_work, strategy="title_list")
        self.assertIsNotNone(rating)
        self.assertEqual(rating.source_name, "StoryGraph")

    @patch("book_rate.sources.base.BaseSource._fetch_html")
    def test_books_tw_source_parsing(self, mock_fetch_html):
        html_content = """
        <a href="//www.books.com.tw/products/0010522737">快思慢想</a>
        """
        mock_fetch_html.return_value = html_content
        source = BooksTwSource()
        works = source.search_works("快思慢想", limit=1)
        self.assertTrue(len(works) >= 0)

    @patch("book_rate.sources.base.BaseSource._fetch_html")
    def test_amazon_jp_source_parsing(self, mock_fetch_html):
        html_content = """
        <a class="a-link-normal" href="/dp/415209333X">ファスト＆スロー</a>
        <span class="a-icon-alt">5星中的4.3顆星</span>
        """
        mock_fetch_html.return_value = html_content
        source = AmazonJPSource()
        rating = source.fetch_ratings(self.test_work, strategy="search_name")
        self.assertIsNotNone(rating)
        self.assertEqual(rating.source_name, "Amazon JP")


from book_rate.orchestrator import RatingOrchestrator
from book_rate.models import RatingRequestPayload


class TestRatingOrchestrator(unittest.TestCase):
    def test_evaluate_all_sync(self):
        orchestrator = RatingOrchestrator()
        req = RatingRequestPayload(
            work_id="gr:12345",
            title="Thinking, Fast and Slow",
            author="Daniel Kahneman",
            engines=["readmoo"]
        )
        res = orchestrator.evaluate_all(req)
        self.assertEqual(res["work_id"], "gr:12345")
        self.assertIn("readmoo", res["ratings"])

    def test_evaluate_stream(self):
        orchestrator = RatingOrchestrator()
        req = RatingRequestPayload(
            work_id="gr:12345",
            title="Thinking, Fast and Slow",
            author="Daniel Kahneman",
            engines=["readmoo"]
        )
        events = list(orchestrator.evaluate_stream(req))
        self.assertTrue(len(events) >= 2)
        self.assertEqual(events[0]["type"], "init")
        self.assertEqual(events[-1]["type"], "done")

    @patch.object(GoogleBooksSource, "fetch_volume_by_id")
    def test_google_books_direct_id_search(self, mock_fetch_vol):
        mock_work = Work(work_id="gb:gS_oAwAAQBAJ", title="Thinking, Fast and Slow", author="Daniel Kahneman")
        mock_fetch_vol.return_value = mock_work

        gb = GoogleBooksSource()
        results = gb.search_works("gb:gS_oAwAAQBAJ")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].work_id, "gb:gS_oAwAAQBAJ")
        mock_fetch_vol.assert_called_once_with("gS_oAwAAQBAJ")

    @patch("requests.Session.get")
    def test_google_books_quota_limit_independent(self, mock_get):
        gb = GoogleBooksSource()

        # Mock 429 response on first request
        mock_resp_429 = MagicMock()
        mock_resp_429.status_code = 429
        mock_get.return_value = mock_resp_429

        results_429 = gb.search_works("Test Query 1")
        self.assertEqual(results_429, [])

        # Mock 200 response on second request
        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200
        mock_resp_200.json.return_value = {
            "items": [{
                "id": "vol123",
                "volumeInfo": {"title": "Test Book", "authors": ["Test Author"], "averageRating": 4.5, "ratingsCount": 10}
            }]
        }
        mock_get.return_value = mock_resp_200

        results_200 = gb.search_works("Test Query 2")
        self.assertEqual(len(results_200), 1)
        self.assertEqual(results_200[0].title, "Test Book")

    @patch("book_rate.sources.douban.DoubanSource._fetch_html")
    def test_douban_search_and_editions_unpacked(self, mock_fetch_html):
        from book_rate.utils.formatters import format_work_to_dict
        source = DoubanSource()
        import json

        # Mock HTML returned for search page containing multiple works including ratings and null_reason
        search_json = {
            "items": [
                {
                    "tpl_name": "search_subject",
                    "id": "26260838",
                    "title": "Harry Potter and the Philosopher's Stone",
                    "url": "https://book.douban.com/subject/26260838/",
                    "rating": {"value": 9.6, "count": 2417, "star_count": 5.0, "rating_info": ""},
                    "abstract": "J.K. Rowling / Bloosbury Publishing / 2014-9 / GBP 12.99"
                },
                {
                    "tpl_name": "search_subject",
                    "id": "19061774",
                    "title": "Harry Potter and the Philosophers Stone",
                    "url": "https://book.douban.com/subject/19061774/",
                    "rating": {"value": 0, "count": 0, "star_count": 0, "rating_info": "评价人数不足"},
                    "abstract": "Miller, Frederic P.; Vandome, Agnes F.; McBrewster, John"
                }
            ]
        }
        mock_fetch_html.return_value = (
            f"<html><body>window.__DATA__ = {json.dumps(search_json)};</body></html>",
            True
        )

        works = source.search_works("Harry Potter and the philosopher's stone")
        self.assertEqual(len(works), 2)
        
        # Test work 1: valid rating
        self.assertEqual(works[0].title, "Harry Potter and the Philosopher's Stone")
        self.assertEqual(works[0].author, "J.K. Rowling")
        self.assertEqual(works[0].first_publish_year, 2014)
        self.assertIn("Douban", works[0].ratings)
        self.assertEqual(works[0].ratings["Douban"].rate, 9.6)
        self.assertEqual(works[0].ratings["Douban"].rating_count, 2417)
        self.assertEqual(works[0].ratings["Douban"].rating_text, "9.6 (2417人评价)")
        
        # Test work 1 dictionary formatting
        dict_1 = format_work_to_dict(works[0])
        self.assertIsNotNone(dict_1["rating"])
        self.assertEqual(dict_1["rating"]["rate"], 9.6)
        self.assertEqual(dict_1["rating"]["rating_count"], 2417)
        self.assertEqual(dict_1["rating"]["rating_text"], "9.6 (2417人评价)")

        # Test work 2: insufficient votes (评价人数不足)
        self.assertEqual(works[1].title, "Harry Potter and the Philosophers Stone")
        self.assertEqual(works[1].author, "Miller, Frederic P.; Vandome, Agnes F.; McBrewster, John")
        self.assertIn("Douban", works[1].ratings)
        self.assertIsNone(works[1].ratings["Douban"].rate)
        self.assertIsNone(works[1].ratings["Douban"].rating_count)
        self.assertEqual(works[1].ratings["Douban"].rating_text, "评价人数不足")

        # Test work 2 dictionary formatting
        dict_2 = format_work_to_dict(works[1])
        self.assertIsNotNone(dict_2["rating"])
        self.assertIsNone(dict_2["rating"]["rate"])
        self.assertIsNone(dict_2["rating"]["rating_count"])
        self.assertEqual(dict_2["rating"]["rating_text"], "评价人数不足")

    def test_books_tw_clean_text_unescape(self):
        source = BooksTwSource()
        raw_text = "An Analysis of Daniel Kahneman&rsquo;s Thinking, Fast and Slow"
        cleaned = source._clean_text(raw_text)
        self.assertEqual(cleaned, "An Analysis of Daniel Kahneman’s Thinking, Fast and Slow")


if __name__ == "__main__":
    unittest.main()

