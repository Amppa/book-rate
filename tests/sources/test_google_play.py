import unittest
from unittest.mock import patch, MagicMock

from book_rate.models import Work, SourceRating
from book_rate.sources.google_play import GooglePlaySource


class TestGooglePlayScraper(unittest.TestCase):
    def test_extract_volume_id_from_url(self):
        source = GooglePlaySource()
        url1 = "https://books.google.com.tw/books?id=z2z_6hLoPmgC&dq=isbn:978957&hl=&source=gbs_api"
        self.assertEqual(source._extract_volume_id_from_url(url1), "z2z_6hLoPmgC")
        
        url2 = "https://play.google.com/store/books/details?id=ZuKTvERuPG8C&source=gbs_api"
        self.assertEqual(source._extract_volume_id_from_url(url2), "ZuKTvERuPG8C")
        
        url3 = "https://play.google.com/store/books/details/z2z_6hLoPmgC"
        self.assertEqual(source._extract_volume_id_from_url(url3), "z2z_6hLoPmgC")
        
        self.assertIsNone(source._extract_volume_id_from_url(None))
        self.assertIsNone(source._extract_volume_id_from_url(""))

    @patch("book_rate.sources.google_play.GooglePlaySource._fetch_html")
    def test_fetch_google_play_rating_json_ld(self, mock_fetch_html):
        source = GooglePlaySource()
        mock_fetch_html.return_value = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@context": "http://schema.org",
              "@type": "Book",
              "name": "Test Book",
              "aggregateRating": {
                "@type": "AggregateRating",
                "ratingValue": "4.7528",
                "ratingCount": "975"
              }
            }
            </script>
          </head>
        </html>
        """
        rate, count, used_curl = source._parse_play_rating("test_id")
        self.assertEqual(rate, 4.7528)
        self.assertEqual(count, 975)

    @patch("book_rate.sources.google_play.GooglePlaySource._fetch_html")
    def test_fetch_google_play_rating_regex_fallback(self, mock_fetch_html):
        source = GooglePlaySource()
        mock_fetch_html.return_value = """
        <html>
          <body>
            <div>Some random text</div>
            "ratingValue" : "4.487"
            "ratingCount" : "630"
          </body>
        </html>
        """
        rate, count, used_curl = source._parse_play_rating("test_id")
        self.assertEqual(rate, 4.487)
        self.assertEqual(count, 630)

    @patch("book_rate.sources.google_play.GooglePlaySource._fetch_html")
    def test_fetch_google_play_rating_failed(self, mock_fetch_html):
        source = GooglePlaySource()
        mock_fetch_html.return_value = "<html><body>No ratings here</body></html>"
        rate, count, used_curl = source._parse_play_rating("test_id")
        self.assertIsNone(rate)
        self.assertIsNone(count)

    @patch("book_rate.sources.google_play.GooglePlaySource._parse_play_details")
    def test_fetch_ratings_direct(self, mock_parse_play):
        source = GooglePlaySource()
        mock_parse_play.return_value = (4.487, 630, False, "Test Title", "Test Author")
        dummy_work = Work(work_id="gb:ZuKTvERuPG8C", title="Test Title", author="Test Author")
        result_rating = source.fetch_ratings(dummy_work)
        self.assertEqual(result_rating.rate, 4.487)
        self.assertEqual(result_rating.rating_count, 630)
        self.assertEqual(result_rating.url, "https://play.google.com/store/books/details?id=ZuKTvERuPG8C")
        self.assertEqual(result_rating.status, "MATCH")
        mock_parse_play.assert_called_once_with("ZuKTvERuPG8C")

    @patch("book_rate.sources.google_play.GooglePlaySource._fetch_html")
    @patch("book_rate.sources.google_play.GooglePlaySource._parse_play_rating")
    def test_search_works_chinese_slug(self, mock_parse_play, mock_fetch_html):
        source = GooglePlaySource()
        mock_fetch_html.return_value = (
            '<html><body>'
            '<a href="/store/books/details/%E7%98%9F%E7%96%AB%E8%88%87%E6%96%87%E6%98%8E_%E4%BA%BA%E9%A1%9E%E7%96%BE%E7%97%85%E5%A4%A7%E6%AD%B7%E5%8F%B2?id=wOzaEAAAQBAJ">Link</a>'
            '</body></html>',
            False
        )
        mock_parse_play.return_value = (4.5, 10, False)
        works = source.search_works("人類大歷史")
        self.assertEqual(len(works), 1)
        self.assertEqual(works[0].title, "瘟疫與文明 人類疾病大歷史")
        self.assertEqual(works[0].author, "Unknown")
        self.assertEqual(works[0].work_id, "gp:wOzaEAAAQBAJ")

    @patch("book_rate.sources.google_play.GooglePlaySource._fetch_html")
    @patch("book_rate.sources.google_play.GooglePlaySource._parse_play_details")
    def test_google_play_search_thinking_fast_and_slow(self, mock_parse_play, mock_fetch_html):
        source = GooglePlaySource()
        mock_fetch_html.return_value = (
            '<html><body>'
            '<a href="/store/books/details/Daniel_Kahneman_Thinking_Fast_and_Slow?id=oV1tXT3HigoC">Link</a>'
            '</body></html>',
            True
        )
        mock_parse_play.return_value = (4.6, 12000, True, "Thinking Fast and Slow", "Daniel Kahneman")
        works = source.search_works("Thinking, Fast and Slow")
        self.assertEqual(len(works), 1)
        self.assertEqual(works[0].title, "Thinking Fast and Slow")
        self.assertEqual(works[0].author, "Daniel Kahneman")
        self.assertEqual(works[0].work_id, "gp:oV1tXT3HigoC")
        self.assertEqual(works[0].ratings["Google Play"].status, "CURL_MATCH")
        self.assertEqual(works[0].ratings["Google Play"].rate, 4.6)

    def test_parse_google_play_html_metadata(self):
        from book_rate.sources.google_play import _parse_google_play_html
        sample_html = """
        <html>
          <head>
            <meta property="og:title" content="Thinking, Fast and Slow - Google Play 圖書">
          </head>
          <body>
            <h1 itemprop="name">Thinking, Fast and Slow</h1>
            <div><a href="/store/books/author?id=Daniel_Kahneman">Daniel Kahneman</a></div>
            <div class="bARER">
              <span>2011年11月</span> · <span>Penguin UK</span>
            </div>
            <div class="rating">
              <span class="rating-value">"ratingValue": "4.6"</span>
              <span class="rating-count">"ratingCount": "12345"</span>
            </div>
            <div>
              <div>出版商</div><div>Penguin UK</div>
              <div>出版日期</div><div>2011年11月</div>
              <div>ISBN</div><div>9780141918921</div>
              <div>語言</div><div>英文</div>
            </div>
          </body>
        </html>
        """
        parsed = _parse_google_play_html(sample_html, "oV1tXT3HigoC", "https://play.google.com/store/books/details?id=oV1tXT3HigoC")
        self.assertEqual(parsed["title"], "Thinking, Fast and Slow")
        self.assertEqual(parsed["author"], "Daniel Kahneman")
        self.assertEqual(parsed["publisher"], "Penguin UK")
        self.assertEqual(parsed["publish_date"], "2011年11月")
        self.assertEqual(parsed["isbn"], "9780141918921")
        self.assertEqual(parsed["language"], "英文")
        self.assertEqual(parsed["rate"], 4.6)
        self.assertEqual(parsed["rating_count"], 12345)

    def test_parse_google_play_harry_potter_metadata(self):
        from book_rate.sources.google_play import _parse_google_play_html
        sample_html = """
        <html>
          <body>
            <h1 itemprop="name">Harry Potter and the Sorcerer's Stone</h1>
            <div class="Vbfug">
              <a href="/store/info/name/John_Williams?id=11gkbjsvcj">John Williams</a>
              <span> · </span>
              <a href="/store/info/name/Victor_L%C3%B3pez?id=113x1sj66">Victor López</a>
            </div>
            <div class="bARER">
              <span>2001年11月</span>
              <span> · </span>
              <a href="/store/info/name/Alfred_Music?id=11gkbjsvcj">Alfred Music</a>
            </div>
          </body>
        </html>
        """
        parsed = _parse_google_play_html(sample_html, "q0nABgAAQBAJ", "https://play.google.com/store/books/details?id=q0nABgAAQBAJ")
        self.assertEqual(parsed["title"], "Harry Potter and the Sorcerer's Stone")
        self.assertEqual(parsed["author"], "John Williams, Victor López")
        self.assertEqual(parsed["publish_date"], "2001年11月")
        self.assertEqual(parsed["publisher"], "Alfred Music")



class TestGooglePlayAdditional(unittest.TestCase):
    def setUp(self):
        self.test_work = Work(
            work_id="test_work_1",
            title="Thinking, Fast and Slow",
            author="Daniel Kahneman",
            title_list=["Thinking, Fast and Slow", "快思慢想"],
            title_zh_list=[],
            author_list=["Daniel Kahneman"],
            isbn_list=["9780374275631"]
        )


    @patch("book_rate.sources.base.BaseSource._fetch_html")
    def test_google_play_source_parsing(self, mock_fetch_html):
        detail_html = """
        <script type="application/ld+json">
        {
            "@context": "http://schema.org",
            "@type": "Book",
            "name": "&quot;Harry Potter and the Sorcerer&#39;s Stone™&quot; -- Selected Themes from the Motion Picture (Solo, Duet, Trio): For B-Flat Clarinet",
            "author": [
                {"@type": "Person", "name": "John Williams"},
                {"@type": "Person", "name": "Victor López"}
            ],
            "aggregateRating": {
                "@type": "AggregateRating",
                "ratingValue": "4.4",
                "ratingCount": "648"
            }
        }
        </script>
        """
        mock_fetch_html.return_value = (detail_html, True)
        source = GooglePlaySource()
        rate, count, used_curl, title, author = source._parse_play_details("q0nABgAAQBAJ")
        self.assertEqual(title, "\"Harry Potter and the Sorcerer's Stone™\" -- Selected Themes from the Motion Picture (Solo, Duet, Trio): For B-Flat Clarinet")
        self.assertEqual(author, "John Williams, Victor López")
        self.assertEqual(rate, 4.4)
        self.assertEqual(count, 648)
        self.assertTrue(used_curl)


    @patch("book_rate.sources.base.BaseSource._fetch_html")
    def test_google_play_search_works(self, mock_fetch_html):
        search_html = """
        <a href="/store/books/details/John_Williams_Harry_Potter_and_the_Sorcerer_s_Ston?id=q0nABgAAQBAJ">
            <div title="&quot;Harry Potter and the Sorcerer&#39;s Stone™&quot; -- Selected Themes from the Motion Picture (Solo, Duet, Trio): For B-Flat Clarinet">
                <div class="Epkrse ">&quot;Harry Potter and the Sorcerer&#39;s Stone™&quot; -- Selected Themes from the Motion Picture (Solo, Duet, Trio): For B-Flat Clarinet</div>
            </div>
        </a>
        """
        detail_html = """
        <script type="application/ld+json">
        {
            "@context": "http://schema.org",
            "@type": "Book",
            "name": "&quot;Harry Potter and the Sorcerer&#39;s Stone™&quot; -- Selected Themes from the Motion Picture (Solo, Duet, Trio): For B-Flat Clarinet",
            "author": [{"@type": "Person", "name": "John Williams"}],
            "aggregateRating": {"@type": "AggregateRating", "ratingValue": "4.4", "ratingCount": "648"}
        }
        </script>
        """
        def fetch_side_effect(url, *args, **kwargs):
            if "search" in url:
                return (search_html, True)
            return (detail_html, True)

        mock_fetch_html.side_effect = fetch_side_effect
        source = GooglePlaySource()
        works = source.search_works("Harry Potter", limit=1)
        self.assertEqual(len(works), 1)
        self.assertEqual(works[0].work_id, "gp:q0nABgAAQBAJ")
        self.assertEqual(works[0].title, "\"Harry Potter and the Sorcerer's Stone™\" -- Selected Themes from the Motion Picture (Solo, Duet, Trio): For B-Flat Clarinet")
        self.assertEqual(works[0].author, "John Williams")
        self.assertIn("Google Play", works[0].ratings)
        self.assertEqual(works[0].ratings["Google Play"].rate, 4.4)
        self.assertEqual(works[0].ratings["Google Play"].rating_count, 648)



if __name__ == "__main__":
    unittest.main()
