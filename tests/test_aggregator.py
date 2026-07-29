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


if __name__ == "__main__":
    unittest.main()
