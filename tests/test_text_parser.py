"""Unit tests for book_rate.utils.text_parser and models.to_book_info."""

import unittest
from book_rate.models import SourceRating
from book_rate.utils.text_parser import (
    clean_text,
    clean_author_name,
    extract_year,
    parse_compact_number,
    parse_json_ld_book,
)


class TestTextParser(unittest.TestCase):
    def test_clean_text(self):
        self.assertIsNone(clean_text(None))
        self.assertIsNone(clean_text(""))
        self.assertIsNone(clean_text("   \n\t  "))
        self.assertEqual(clean_text("<h1>Hello &amp; World</h1>"), "Hello & World")
        self.assertEqual(clean_text("  多餘   空格 \n 換行  "), "多餘 空格 換行")
        self.assertEqual(clean_text("Very Long Title Indeed", max_len=10), "Very Long")

    def test_clean_author_name(self):
        self.assertIsNone(clean_author_name(None))
        self.assertEqual(clean_author_name("by Daniel Kahneman"), "Daniel Kahneman")
        self.assertEqual(clean_author_name("作者：馬克斯．菲爾普斯"), "馬克斯．菲爾普斯")
        self.assertEqual(clean_author_name("著者：東野圭吾"), "東野圭吾")
        self.assertEqual(clean_author_name("鈴木一郎 (著)"), "鈴木一郎")
        self.assertEqual(clean_author_name("張三 著"), "張三")
        self.assertEqual(clean_author_name("張三 原著"), "張三")
        self.assertEqual(clean_author_name("張三 等著"), "張三")
        self.assertEqual(clean_author_name("佐藤次郎 等訳"), "佐藤次郎")
        self.assertEqual(clean_author_name("陳儀 譯"), "陳儀")
        self.assertEqual(clean_author_name("John Doe (Author)"), "John Doe")

    def test_extract_year(self):
        self.assertIsNone(extract_year(None))
        self.assertIsNone(extract_year(""))
        self.assertEqual(extract_year("2025/03/31"), "2025")
        self.assertEqual(extract_year("March 2021"), "2021")
        self.assertEqual(extract_year("1998-10-15"), "1998")
        self.assertEqual(extract_year("Published in 2016."), "2016")

    def test_parse_compact_number(self):
        self.assertIsNone(parse_compact_number(None))
        self.assertIsNone(parse_compact_number(""))
        self.assertEqual(parse_compact_number("123"), 123)
        self.assertEqual(parse_compact_number("1,500"), 1500)
        self.assertEqual(parse_compact_number("1.5k"), 1500)
        self.assertEqual(parse_compact_number("2.3M"), 2300000)
        self.assertEqual(parse_compact_number("300+"), 300)
        self.assertIsNone(parse_compact_number("invalid"))

    def test_parse_json_ld_book_standard(self):
        html_doc = """
        <html>
          <script type="application/ld+json">
          {
            "@context": "http://schema.org",
            "@type": "Book",
            "name": "Thinking, Fast and Slow",
            "author": [{"@type": "Person", "name": "Daniel Kahneman"}],
            "translator": [{"@type": "Person", "name": "洪蘭"}],
            "publisher": {"@type": "Organization", "name": "Farrar, Straus and Giroux"},
            "datePublished": "2011-10-25",
            "isbn": "9780374275631",
            "inLanguage": "en",
            "aggregateRating": {
              "@type": "AggregateRating",
              "ratingValue": "4.18",
              "ratingCount": "450,000"
            }
          }
          </script>
        </html>
        """
        data = parse_json_ld_book(html_doc)
        self.assertIsNotNone(data)
        self.assertEqual(data["title"], "Thinking, Fast and Slow")
        self.assertEqual(data["author"], "Daniel Kahneman")
        self.assertEqual(data["translator"], "洪蘭")
        self.assertEqual(data["publisher"], "Farrar, Straus and Giroux")
        self.assertEqual(data["publish_date"], "2011-10-25")
        self.assertEqual(data["isbn"], "9780374275631")
        self.assertEqual(data["language"], "en")
        self.assertEqual(data["rate"], 4.18)
        self.assertEqual(data["count"], 450000)

    def test_parse_json_ld_book_graph(self):
        html_doc = """
        <html>
          <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@graph": [
              {
                "@type": "WebPage",
                "name": "Some Page"
              },
              {
                "@type": "Book",
                "name": "致富心態",
                "author": {"@type": "Person", "name": "摩根．豪瑟"},
                "datePublished": "2021/01/27",
                "isbn": "9789865535971"
              }
            ]
          }
          </script>
        </html>
        """
        data = parse_json_ld_book(html_doc)
        self.assertIsNotNone(data)
        self.assertEqual(data["title"], "致富心態")
        self.assertEqual(data["author"], "摩根．豪瑟")
        self.assertEqual(data["publish_date"], "2021/01/27")
        self.assertEqual(data["isbn"], "9789865535971")

    def test_parse_json_ld_book_array_root_and_single_quotes(self):
        html_doc = """
        <html>
          <head>
            <script type='application/ld+json'>
            [
              {
                "@context": "https://schema.org",
                "@type": "https://schema.org/Book",
                "name": "Atomic Habits",
                "author": "James Clear",
                "isbn": "9780735211292"
              }
            ]
            </script>
          </head>
        </html>
        """
        data = parse_json_ld_book(html_doc)
        self.assertIsNotNone(data)
        self.assertEqual(data["title"], "Atomic Habits")
        self.assertEqual(data["author"], "James Clear")
        self.assertEqual(data["isbn"], "9780735211292")

    def test_source_rating_to_book_info_copy_and_clean(self):
        # 1. Dataclass fields fallback
        r1 = SourceRating(
            source_name="Test",
            author="Author One",
            publisher="Publisher A",
            language="None",
            original_title="Unknown",
            isbn="9780000000000"
        )
        info1 = r1.to_book_info()
        self.assertIsNotNone(info1)
        self.assertEqual(info1["author"], "Author One")
        self.assertEqual(info1["publisher"], "Publisher A")
        self.assertEqual(info1["isbn"], "9780000000000")
        self.assertNotIn("language", info1)
        self.assertNotIn("original_title", info1)

        # 2. Existing book_info dict copy isolation
        orig_dict = {"author": "Custom Author", "language": "en", "extra_bad": "none"}
        r2 = SourceRating(source_name="Test", book_info=orig_dict)
        info2 = r2.to_book_info()
        self.assertEqual(info2["author"], "Custom Author")
        self.assertNotIn("extra_bad", info2)
        # Verify modifying returned dict does not mutate orig_dict
        info2["author"] = "Mutated"
        self.assertEqual(orig_dict["author"], "Custom Author")


if __name__ == "__main__":
    unittest.main()
