import unittest
from unittest.mock import patch, MagicMock

from book_rate.models import Work, SourceRating
from book_rate.sources.google_books import GoogleBooksSource


class TestGoogleBooksQuotaFlag(unittest.TestCase):
    @patch("requests.Session.get")
    def test_search_works_sets_quota_flag_on_429_and_resets_on_success(self, mock_get):
        from book_rate.sources.google_books import GoogleBooksSource
        gb = GoogleBooksSource()

        resp_429 = MagicMock()
        resp_429.status_code = 429
        mock_get.return_value = resp_429
        self.assertEqual(gb.search_works("Any Query"), [])
        self.assertTrue(gb.quota_exceeded)

        resp_ok = MagicMock()
        resp_ok.status_code = 200
        resp_ok.json.return_value = {
            "items": [{"id": "v1", "volumeInfo": {"title": "Some Book", "authors": ["Author"]}}]
        }
        mock_get.return_value = resp_ok
        works = gb.search_works("Another Query")
        self.assertFalse(gb.quota_exceeded)
        self.assertEqual(len(works), 1)

    @patch("requests.Session.get")
    def test_fetch_volume_by_id_sets_quota_flag_on_429(self, mock_get):
        from book_rate.sources.google_books import GoogleBooksSource
        gb = GoogleBooksSource()
        resp_429 = MagicMock()
        resp_429.status_code = 429
        mock_get.return_value = resp_429
        self.assertIsNone(gb.fetch_volume_by_id("vol123"))
        self.assertTrue(gb.quota_exceeded)

    @patch("requests.Session.get")
    def test_invalid_api_key_raises_actionable_network_error(self, mock_get):
        import requests
        from book_rate.sources.base import SourceNetworkError
        from book_rate.sources.google_books import GoogleBooksSource
        gb = GoogleBooksSource()

        resp = MagicMock()
        resp.status_code = 400
        resp.text = '{"error": {"code": 400, "message": "API key not valid. Please pass a valid API key."}}'
        he = requests.exceptions.HTTPError("400 Client Error: Bad Request", response=resp)
        mock_get.return_value = resp
        resp.raise_for_status.side_effect = he

        with self.assertRaises(SourceNetworkError) as ctx:
            gb.search_works("Any Query")
        self.assertIn("Invalid API Key", str(ctx.exception))
        self.assertFalse(gb.quota_exceeded)

    @patch("requests.Session.get")
    def test_other_http_errors_return_empty_without_raising(self, mock_get):
        import requests
        from book_rate.sources.google_books import GoogleBooksSource
        gb = GoogleBooksSource()

        resp = MagicMock()
        resp.status_code = 500
        resp.text = "{}"
        he = requests.exceptions.HTTPError("500 Server Error", response=resp)
        mock_get.return_value = resp
        resp.raise_for_status.side_effect = he

        self.assertEqual(gb.search_works("Any Query"), [])
        self.assertFalse(gb.quota_exceeded)



class TestGoogleBooksTitleCleaner(unittest.TestCase):
    def test_clean_title_normal_title(self):
        source = GoogleBooksSource()
        title = "Thinking, Fast and Slow"
        cleaned = source._clean_title(title, "vol_123")
        self.assertEqual(cleaned, title)

    @patch("book_rate.sources.base.BaseSource._fetch_html")
    def test_clean_title_garbled_title(self, mock_fetch_html):
        mock_fetch_html.return_value = (
            '<html><head>'
            '<meta name="title" content="哈利·波特与魔法石 ((Harry Potter and the Philosopher&#39;s Stone)"/>'
            '</head></html>',
            False
        )
        source = GoogleBooksSource()
        garbled = "哈利+!JY'T2!ar!G*!N( (Harry Potter and the Philosopher's Stone)"
        cleaned = source._clean_title(garbled, "Ztg2zgEACAAJ")
        self.assertEqual(cleaned, "哈利·波特与魔法石 ((Harry Potter and the Philosopher's Stone)")
        mock_fetch_html.assert_called_once_with("https://books.google.com/books?id=Ztg2zgEACAAJ")

    @patch("book_rate.sources.base.BaseSource._fetch_html")
    @patch("requests.Session.get")
    def test_search_works_cleans_garbled_title(self, mock_get, mock_fetch_html):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {
                    "id": "Ztg2zgEACAAJ",
                    "volumeInfo": {
                        "title": "哈利+!JY'T2!ar!G*!N( (Harry Potter and the Philosopher's Stone)",
                        "authors": ["J.K. Rowling"]
                    }
                }
            ]
        }
        mock_get.return_value = mock_resp
        mock_fetch_html.return_value = (
            '<html><head>'
            '<meta name="title" content="哈利·波特与魔法石 ((Harry Potter and the Philosopher&#39;s Stone)"/>'
            '</head></html>',
            False
        )
        source = GoogleBooksSource()
        works = source.search_works("哈利·波特与魔法石", limit=1)
        self.assertEqual(len(works), 1)
        self.assertEqual(works[0].title, "哈利·波特与魔法石 ((Harry Potter and the Philosopher's Stone)")
        self.assertEqual(works[0].editions[0].title, "哈利·波特与魔法石 ((Harry Potter and the Philosopher's Stone)")



class TestGoogleBooksAdditional(unittest.TestCase):
    def setUp(self):
        self.dummy_work = Work(
            work_id="non_existent_123",
            title="NonExistentBook_XYZ999",
            author="UnknownAuthor_XYZ999"
        )


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


    @patch("requests.Session.get")
    def test_google_books_book_info_extraction(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {
                    "id": "gb123",
                    "volumeInfo": {
                        "title": "Clean Code",
                        "authors": ["Robert C. Martin"],
                        "publisher": "Prentice Hall",
                        "publishedDate": "2008-08-01",
                        "language": "en",
                        "industryIdentifiers": [{"type": "ISBN_13", "identifier": "9780132350884"}],
                        "averageRating": 4.5,
                        "ratingsCount": 2500
                    }
                }
            ]
        }
        mock_get.return_value = mock_resp
        source = GoogleBooksSource()
        works = source.search_works("Clean Code", limit=1)
        self.assertEqual(len(works), 1)
        r = works[0].ratings["Google Books"]
        self.assertEqual(r.author, "Robert C. Martin")
        self.assertEqual(r.publisher, "Prentice Hall")
        self.assertEqual(r.publish_date, "2008-08-01")
        self.assertEqual(r.language, "en")
        self.assertEqual(r.isbn, "9780132350884")
        self.assertEqual(r.work_id, "gb:gb123")



if __name__ == "__main__":
    unittest.main()
