import unittest
from unittest.mock import patch, MagicMock

from book_rate.models import Work, SourceRating
from book_rate.sources.open_library import OpenLibrarySource


class TestOpenLibrarySource(unittest.TestCase):
    def test_open_library_instance(self):
        source = OpenLibrarySource()
        self.assertEqual(source.name, "Open Library")
        self.assertTrue(source.enable_extend_editions)


if __name__ == "__main__":
    unittest.main()
