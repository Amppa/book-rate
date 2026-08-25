import unittest
from unittest.mock import patch, MagicMock

from book_rate.models import Work, SourceRating
from book_rate.sources.storygraph import StoryGraphSource


class TestStoryGraphSource(unittest.TestCase):
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



if __name__ == "__main__":
    unittest.main()
