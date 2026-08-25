import unittest
from unittest.mock import patch, MagicMock
from book_rate.utils.metadata import (
    BOOK_METADATA_FIELDS,
    empty_book_metadata,
    is_meaningful_value,
    merge_book_metadata,
    source_rating_from_metadata,
)
from book_rate.sources.base import BaseSource, FetchCandidate
from book_rate.models import SourceRating, SourceStatus


class TestMetadataContract(unittest.TestCase):
    """Unit tests for standard metadata contract, merging, and SourceRating factory."""

    def test_empty_book_metadata(self):
        meta = empty_book_metadata(url="https://example.com/book/1", work_id="bk:001")
        self.assertIsNone(meta["title"])
        self.assertIsNone(meta["author"])
        self.assertIsNone(meta["rate"])
        self.assertIsNone(meta["rating_count"])
        self.assertEqual(meta["url"], "https://example.com/book/1")
        self.assertEqual(meta["work_id"], "bk:001")
        self.assertEqual(meta["metadata"], {})

    def test_is_meaningful_value(self):
        self.assertFalse(is_meaningful_value(None))
        self.assertFalse(is_meaningful_value(""))
        self.assertFalse(is_meaningful_value("   "))
        self.assertFalse(is_meaningful_value("Unknown"))
        self.assertFalse(is_meaningful_value("unknown"))
        self.assertFalse(is_meaningful_value("none"))
        self.assertFalse(is_meaningful_value("N/A"))
        self.assertFalse(is_meaningful_value("null"))
        self.assertFalse(is_meaningful_value("-"))
        self.assertFalse(is_meaningful_value([]))
        self.assertFalse(is_meaningful_value({}))

        self.assertTrue(is_meaningful_value("Clean Code"))
        self.assertTrue(is_meaningful_value(0))
        self.assertTrue(is_meaningful_value(4.5))
        self.assertTrue(is_meaningful_value(["author1"]))
        self.assertTrue(is_meaningful_value({"key": "val"}))

    def test_merge_book_metadata(self):
        base = empty_book_metadata(url="https://example.com/book/1", work_id="bk:001")
        extra_1 = {
            "title": "原子習慣",
            "author": "James Clear",
            "translator": None,
            "rate": 4.5,
            "rating_count": "Unknown",
        }
        merge_book_metadata(base, extra_1)
        self.assertEqual(base["title"], "原子習慣")
        self.assertEqual(base["author"], "James Clear")
        self.assertIsNone(base["translator"])
        self.assertEqual(base["rate"], 4.5)
        self.assertIsNone(base["rating_count"])

        extra_2 = {
            "translator": "蔡世偉",
            "rating_count": 1200,
            "title": "",  # Empty title should not overwrite existing title
        }
        merge_book_metadata(base, extra_2)
        self.assertEqual(base["title"], "原子習慣")
        self.assertEqual(base["translator"], "蔡世偉")
        self.assertEqual(base["rating_count"], 1200)

    def test_source_rating_from_metadata(self):
        data = {
            "title": "魔戒",
            "author": "J.R.R. Tolkien",
            "translator": "朱學恆",
            "publisher": "聯經",
            "publish_date": "2001/10/01",
            "rate": 4.9,
            "rating_count": 5000,
            "url": "https://example.com/lotr",
            "work_id": "bk:002",
            "isbn": "9789570850000",
            "series": "魔戒三部曲",
        }
        rating = source_rating_from_metadata("博客來", data, strategy="title_author")
        self.assertIsInstance(rating, SourceRating)
        self.assertEqual(rating.source_name, "博客來")
        self.assertEqual(rating.title, "魔戒")
        self.assertEqual(rating.author, "J.R.R. Tolkien")
        self.assertEqual(rating.translator, "朱學恆")
        self.assertEqual(rating.publisher, "聯經")
        self.assertEqual(rating.publish_date, "2001/10/01")
        self.assertEqual(rating.rate, 4.9)
        self.assertEqual(rating.rating_count, 5000)
        self.assertEqual(rating.url, "https://example.com/lotr")
        self.assertEqual(rating.work_id, "bk:002")
        self.assertEqual(rating.strategy, "title_author")
        self.assertEqual(rating.status, SourceStatus.MATCH.value)
        self.assertEqual(rating.metadata.get("series"), "魔戒三部曲")


class DummySource(BaseSource):
    @property
    def name(self) -> str:
        return "Dummy"


class TestFetchFirstAvailable(unittest.TestCase):
    """Unit tests for BaseSource._fetch_first_available."""

    @patch("book_rate.sources.base.BaseSource._fetch_html")
    def test_fetch_first_available_success_on_first(self, mock_fetch):
        mock_fetch.return_value = ("<html>Product Page</html>", False)
        source = DummySource()
        candidates = [
            FetchCandidate(url="https://example.com/p1"),
            FetchCandidate(url="https://example.com/p2"),
        ]
        html, used_curl, url = source._fetch_first_available(candidates)
        self.assertEqual(html, "<html>Product Page</html>")
        self.assertFalse(used_curl)
        self.assertEqual(url, "https://example.com/p1")
        self.assertEqual(mock_fetch.call_count, 1)

    @patch("book_rate.sources.base.BaseSource._fetch_html")
    def test_fetch_first_available_fallback_to_second(self, mock_fetch):
        def side_effect(url, headers=None):
            if "p1" in url:
                return ("<html>WAF Blocked waf/logo.svg</html>", False)
            return ("<html>Valid Comment Page</html>", True)

        mock_fetch.side_effect = side_effect
        source = DummySource()
        candidates = [
            FetchCandidate(url="https://example.com/p1"),
            FetchCandidate(url="https://example.com/p2"),
        ]
        is_invalid = lambda h: not h or "waf/logo.svg" in h
        html, used_curl, url = source._fetch_first_available(candidates, is_invalid=is_invalid)
        self.assertEqual(html, "<html>Valid Comment Page</html>")
        self.assertTrue(used_curl)
        self.assertEqual(url, "https://example.com/p2")
        self.assertEqual(mock_fetch.call_count, 2)

    def test_fetch_first_available_custom_fetcher_with_headers(self):
        source = DummySource()
        received_calls = []

        def custom_fetcher(url, headers=None):
            received_calls.append((url, headers))
            return ("<html>Custom Content</html>", False)

        candidates = [
            FetchCandidate(url="https://example.com/p1", headers={"X-Test": "123"}, referer="https://search.example.com/"),
        ]
        html, used_curl, url = source._fetch_first_available(candidates, fetcher=custom_fetcher)
        self.assertEqual(html, "<html>Custom Content</html>")
        self.assertEqual(url, "https://example.com/p1")
        self.assertEqual(len(received_calls), 1)
        self.assertEqual(received_calls[0][0], "https://example.com/p1")
        self.assertEqual(received_calls[0][1], {"X-Test": "123", "Referer": "https://search.example.com/"})

    @patch("book_rate.sources.base.BaseSource._fetch_html")
    def test_fetch_first_available_all_failed_returns_false_used_curl(self, mock_fetch):
        def side_effect(url, headers=None):
            if "p1" in url:
                # 1st candidate used curl and failed due to WAF
                return ("<html>waf/logo.svg</html>", True)
            # 2nd candidate used requests and failed with empty html
            return ("", False)

        mock_fetch.side_effect = side_effect
        source = DummySource()
        candidates = [
            FetchCandidate(url="https://example.com/p1"),
            FetchCandidate(url="https://example.com/p2"),
        ]
        is_invalid = lambda h: not h or "waf/logo.svg" in h
        html, used_curl, url = source._fetch_first_available(candidates, is_invalid=is_invalid)
        self.assertIsNone(html)
        self.assertFalse(used_curl)
        self.assertIsNone(url)
        self.assertEqual(mock_fetch.call_count, 2)


if __name__ == "__main__":
    unittest.main()
