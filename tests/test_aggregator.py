import unittest
from book_rate.models import Work, PlatformRating, Edition
from book_rate.formatters import format_markdown_table, format_csv, format_json


class TestModelsAndFormatters(unittest.TestCase):

    def setUp(self):
        self.sample_work = Work(
            work_id="/works/OL17362624W",
            title="三體",
            author="劉慈欣",
            editions=[
                Edition(
                    edition_id="/books/OL26331908M",
                    title="三體",
                    publish_year="2008",
                    language="chi",
                    isbn_13="9787536692930"
                )
            ],
            ratings={
                "Open Library": PlatformRating(
                    platform_name="Open Library",
                    rate=4.25,
                    rating_count=150,
                    url="https://openlibrary.org/works/OL17362624W"
                ),
                "Google Books": PlatformRating(
                    platform_name="Google Books",
                    rate=4.40,
                    rating_count=3200,
                    url="https://books.google.com"
                )
            }
        )

    def test_platform_rating_format(self):
        rating = PlatformRating(platform_name="Open Library", rate=4.5, rating_count=100)
        self.assertEqual(rating.format_rate_count(), "4.50 / 100 reviews")

        empty_rating = PlatformRating(platform_name="Google Books")
        self.assertEqual(empty_rating.format_rate_count(), "N/A")

    def test_markdown_formatter(self):
        md = format_markdown_table([self.sample_work])
        self.assertIn("書名", md)
        self.assertIn("原作者", md)
        self.assertIn("work", md)
        self.assertIn("Open Library 分數／人數", md)
        self.assertIn("Google Books 分數／人數", md)
        self.assertIn("三體", md)
        self.assertIn("劉慈欣", md)
        self.assertIn("/works/OL17362624W", md)
        self.assertIn("4.25 / 150 reviews", md)
        self.assertIn("4.40 / 3200 reviews", md)

    def test_csv_formatter(self):
        csv_out = format_csv([self.sample_work])
        self.assertIn("三體", csv_out)
        self.assertIn("劉慈欣", csv_out)
        self.assertIn("4.25 / 150 reviews", csv_out)

    def test_json_formatter(self):
        json_out = format_json([self.sample_work])
        self.assertIn("/works/OL17362624W", json_out)
        self.assertIn("三體", json_out)


from unittest.mock import MagicMock, patch
from book_rate.providers.google_books import GoogleBooksProvider

class TestGoogleBooksProvider(unittest.TestCase):
    @patch('requests.Session.get')
    def test_fetch_volume_by_id(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "test_vol_123",
            "volumeInfo": {
                "title": "原子習慣",
                "authors": ["詹姆斯‧克利爾"],
                "publisher": "方智",
                "publishedDate": "2019-06-01",
                "averageRating": 4.8,
                "ratingsCount": 250,
                "industryIdentifiers": [
                    {"type": "ISBN_13", "identifier": "9789861755267"}
                ],
                "language": "zh-TW",
                "infoLink": "https://books.google.com/test"
            }
        }
        mock_get.return_value = mock_response

        provider = GoogleBooksProvider(api_key="fake_key")
        work = provider.fetch_volume_by_id("test_vol_123")

        self.assertIsNotNone(work)
        self.assertEqual(work.work_id, "gb:test_vol_123")
        self.assertEqual(work.title, "原子習慣")
        self.assertEqual(work.author, "詹姆斯‧克利爾")
        self.assertEqual(work.first_publish_year, 2019)
        self.assertEqual(len(work.editions), 1)
        self.assertEqual(work.editions[0].publisher, "方智")
        self.assertEqual(work.editions[0].isbn_13, "9789861755267")

        gb_rating = work.ratings.get("Google Books")
        self.assertIsNotNone(gb_rating)
        self.assertEqual(gb_rating.rate, 4.8)
        self.assertEqual(gb_rating.rating_count, 250)


    @patch('requests.Session.get')
    def test_original_title_extraction(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "test_vol_456",
            "volumeInfo": {
                "title": "原子習慣：細微改變帶來巨大成就的實證法則",
                "authors": ["詹姆斯‧克利爾 (James Clear)"],
                "description": "「每天進步1%，一年後，你會進步37倍。」 這是暢銷書《原子習慣》（Atomic Habits）的核心觀點。",
                "publishedDate": "2019"
            }
        }
        mock_get.return_value = mock_response

        provider = GoogleBooksProvider(api_key="fake_key")
        work = provider.fetch_volume_by_id("test_vol_456")

        self.assertIsNotNone(work)
        self.assertEqual(work.original_title, "Atomic Habits")


if __name__ == "__main__":
    unittest.main()
