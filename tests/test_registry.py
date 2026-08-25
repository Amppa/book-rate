import unittest

from book_rate.registry import SourceRegistry


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

    def test_get_prefix_by_source_name(self):
        self.assertEqual(SourceRegistry.get_prefix("Google Play"), "gp:")
        self.assertEqual(SourceRegistry.get_prefix("google_play", with_colon=False), "gp")
        self.assertEqual(SourceRegistry.get_prefix_by_source_name("豆瓣"), "db:")
        self.assertEqual(SourceRegistry.get_prefix("豆瓣", with_colon=False), "db")
        self.assertEqual(SourceRegistry.get_prefix_by_source_name("Open Library"), "ol:")
        self.assertEqual(SourceRegistry.get_prefix_by_source_name("博客來"), "bk:")
        self.assertIsNone(SourceRegistry.get_prefix_by_source_name("NonExistentSource"))

    def test_match_id_prefix(self):
        pfx, skey = SourceRegistry.match_id_prefix("gp:12345")
        self.assertEqual(pfx, "gp:")
        self.assertEqual(skey, "google_play")

        pfx_none, skey_none = SourceRegistry.match_id_prefix("OL12345W")
        self.assertIsNone(pfx_none)
        self.assertIsNone(skey_none)



if __name__ == "__main__":
    unittest.main()
