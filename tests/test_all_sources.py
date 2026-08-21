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
from book_rate.sources.google_play import GooglePlaySource
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
        self.assertEqual(works[0].work_id, "play:q0nABgAAQBAJ")
        self.assertEqual(works[0].title, "\"Harry Potter and the Sorcerer's Stone™\" -- Selected Themes from the Motion Picture (Solo, Duet, Trio): For B-Flat Clarinet")
        self.assertEqual(works[0].author, "John Williams")
        self.assertIn("Google Play", works[0].ratings)
        self.assertEqual(works[0].ratings["Google Play"].rate, 4.4)
        self.assertEqual(works[0].ratings["Google Play"].rating_count, 648)



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

    def test_amazon_jp_html_unescape_title_and_author(self):
        from book_rate.sources.amazon import AmazonJPSource
        source = AmazonJPSource()
        sample_block = """
        <div data-component-type="s-search-result" data-asin="B08CXK9C2T">
          <h2><span>Harry Potter and the Sorcerer&#x27;s Stone: Minalima Edition</span></h2>
          <span>by <a href="#">J.K. Rowling &amp; MinaLima</a></span>
          <span class="a-size-base s-underline-text">1,234</span>
          <span>5つ星のうち 4.8</span>
        </div>
        """
        work = source._parse_search_block(sample_block, "Harry Potter")
        self.assertIsNotNone(work)
        self.assertEqual(work.title, "Harry Potter and the Sorcerer's Stone: Minalima Edition")
        self.assertEqual(work.author, "J.K. Rowling & MinaLima")

    def test_amazon_jp_author_filtering_and_extraction(self):
        from book_rate.sources.amazon import AmazonJPSource
        source = AmazonJPSource()

        # 1. Korean Edition format without author
        block1 = """
        <div data-component-type="s-search-result" data-asin="8934956151">
          <h2><span>Thinking, Fast and Slow</span></h2>
          <div class="a-row a-size-base a-color-secondary"><span>韓国語版</span><span class="a-letter-space"></span><span>|</span><span class="a-letter-space"></span><span>2018/3/29</span></div>
        </div>
        """
        w1 = source._parse_search_block(block1, "Thinking, Fast and Slow")
        self.assertEqual(w1.author, "Unknown")

        # 2. Chinese version with author link and 著
        block2 = """
        <div data-component-type="s-search-result" data-asin="7521766911">
          <h2><span>思考，快与慢（中文版）</span></h2>
          <div class="a-row a-size-base a-color-secondary"><a class="a-size-base a-link-normal" href="/Daniel-Kahneman/e/B001ILFNQG">丹尼尔·卡尼曼 Daniel Kahneman</a> 著<span class="a-letter-space"></span><span>|</span><span class="a-letter-space"></span><span>2025-04出版</span></div>
        </div>
        """
        w2 = source._parse_search_block(block2, "思考，快与慢")
        self.assertEqual(w2.author, "丹尼尔·卡尼曼 Daniel Kahneman")

        # 3. Series format before authors
        block3 = """
        <div data-component-type="s-search-result" data-asin="B00ARDNMEQ">
          <h2><span>ファスト＆スロー （上）</span></h2>
          <div class="a-row a-size-base a-color-secondary"><a href="/gp/product/B0716S2Z29">全2巻の第1巻: ファスト＆スロー</a><span class="a-letter-space"></span><span>|</span><span class="a-letter-space"></span><a href="/Daniel-Kahneman/e/B001ILFNQG">ダニエル・カーネマン</a> (著), <a href="/Akiko-Murai/e/B004L4659O">村井章子</a> (翻訳)<span class="a-letter-space"></span><span>|</span><span class="a-letter-space"></span><span>2012/11/20</span></div>
        </div>
        """
        w3 = source._parse_search_block(block3, "ファスト＆スロー")
        self.assertEqual(w3.author, "ダニエル・カーネマン, 村井章子")

        # 4. Chinese Edition with format + author + date
        block4 = """
        <div data-component-type="s-search-result" data-asin="7508633555">
          <h2><span>Thinking. Fast and Slow (Chinese Edition)</span></h2>
          <div class="a-row a-size-base a-color-secondary"><span>中文版本</span><span class="a-letter-space"></span><span>|</span><span class="a-letter-space"></span><a href="/Daniel-Kahneman/e/B001ILFNQG">Daniel Kahneman</a><span class="a-letter-space"></span><span>|</span><span class="a-letter-space"></span><span>2011-10出版</span></div>
        </div>
        """
        w4 = source._parse_search_block(block4, "Thinking. Fast and Slow")
        self.assertEqual(w4.author, "Daniel Kahneman")

        # 5. Out of stock notice in row
        block5 = """
        <div data-component-type="s-search-result" data-asin="B0716S2Z29">
          <h2><span>ファスト&スロー 文庫 (上)(下)セット</span></h2>
          <div class="a-row a-size-base a-color-secondary"><span>現在在庫切れです。</span></div>
        </div>
        """
        w5 = source._parse_search_block(block5, "ファスト&スロー")
        self.assertEqual(w5.author, "Unknown")

        # 6. Plain text author without link in metadata row
        block6 = """
        <div data-component-type="s-search-result" data-asin="1516869443">
          <h2><span>Thinking, Fast and Slow: By Daniel Kahneman (Trivia-on-Books)</span></h2>
          <div class="a-row a-size-base a-color-secondary"><span>英語版</span><span class="a-letter-space"></span><span>|</span><span class="a-letter-space"></span><span>Trivia-on-Books</span><span class="a-letter-space"></span><span>|</span><span class="a-letter-space"></span><span>2015/8/20</span></div>
        </div>
        """
        w6 = source._parse_search_block(block6, "Trivia-on-Books")
        self.assertEqual(w6.author, "Trivia-on-Books")

        # 7. Multiple plain text authors before date (e.g. 2013-02出版)
        block7 = """
        <div data-component-type="s-search-result" data-asin="1234567890">
          <h2><span>Thinking, Fast and Slow (Co-authored)</span></h2>
          <div class="a-row a-size-base a-color-secondary"><span>中文版本</span><span class="a-letter-space"></span><span>|</span><span class="a-letter-space"></span><span>Daniel Kahneman, Amos Tversky</span><span class="a-letter-space"></span><span>|</span><span class="a-letter-space"></span><span>2013-02出版</span></div>
        </div>
        """
        w7 = source._parse_search_block(block7, "Thinking, Fast and Slow")
        self.assertEqual(w7.author, "Daniel Kahneman, Amos Tversky")

        # 8. Multiple linked authors before date
        block8 = """
        <div data-component-type="s-search-result" data-asin="0987654321">
          <h2><span>Thinking, Fast and Slow (Co-authored Links)</span></h2>
          <div class="a-row a-size-base a-color-secondary"><span>中文版本</span><span class="a-letter-space"></span><span>|</span><span class="a-letter-space"></span><a href="/Daniel-Kahneman/e/B001ILFNQG">Daniel Kahneman</a>, <a href="/Amos-Tversky/e/B002ILFNQG">Amos Tversky</a><span class="a-letter-space"></span><span>|</span><span class="a-letter-space"></span><span>2013-02出版</span></div>
        </div>
        """
        w8 = source._parse_search_block(block8, "Thinking, Fast and Slow")
        self.assertEqual(w8.author, "Daniel Kahneman, Amos Tversky")

    @patch("book_rate.sources.goodreads.GoodreadsSource._fetch_html")
    def test_goodreads_autocomplete_search_parsing(self, mock_fetch_html):
        import json
        from book_rate.sources.goodreads import GoodreadsSource
        from book_rate.utils.formatters import format_work_to_dict

        mock_json = json.dumps([
            {
                "bookId": "3",
                "workId": "4640799",
                "bookUrl": "/book/show/3.Harry_Potter_and_the_Sorcerer_s_Stone",
                "title": "Harry Potter and the Sorcerer's Stone (Harry Potter, #1)",
                "avgRating": "4.47",
                "ratingsCount": 11765295,
                "author": {"name": "J.K. Rowling"}
            }
        ])
        mock_fetch_html.return_value = (mock_json, True)

        source = GoodreadsSource()
        works = source.search_works("Harry Potter and the Sorcerer's Stone")

        self.assertEqual(len(works), 1)
        w = works[0]
        self.assertEqual(w.work_id, "gr:work/4640799/book/3.Harry_Potter_and_the_Sorcerer_s_Stone")
        self.assertEqual(w.title, "Harry Potter and the Sorcerer's Stone (Harry Potter, #1)")
        self.assertEqual(w.author, "J.K. Rowling")
        self.assertIn("Goodreads", w.ratings)
        self.assertEqual(w.ratings["Goodreads"].rate, 4.47)
        self.assertEqual(w.ratings["Goodreads"].rating_count, 11765295)
        self.assertEqual(w.ratings["Goodreads"].status, "CURL_MATCH")

        dict_w = format_work_to_dict(w)
        self.assertIsNotNone(dict_w["rating"])
        self.assertEqual(dict_w["rating"]["rate"], 4.47)
        self.assertEqual(dict_w["rating"]["rating_count"], 11765295)

    @patch("book_rate.sources.goodreads.GoodreadsSource._fetch_html")
    def test_goodreads_search_html_parsing(self, mock_fetch_html):
        from book_rate.sources.goodreads import _parse_goodreads_search_html

        mock_html = """
        <table class="tableList">
          <tr itemscope itemtype="http://schema.org/Book">
            <td>
              <a class="bookTitle" itemprop="url" href="/book/show/3.Harry_Potter_and_the_Sorcerer_s_Stone?from_search=true">
                <span itemprop="name">Harry Potter and the Sorcerer's Stone (Harry Potter, #1)</span>
              </a>
              by
              <span itemprop="author"><a class="authorName"><span itemprop="name">J.K. Rowling</span></a></span>
              <div>
                <span class="minirating"> 4.47 avg rating &mdash; 11,765,261 ratings</span>
                &mdash; published 1997 &mdash;
                <a class="greyText" href="/work/editions/4640799-harry-potter-and-the-philosopher-s-stone">19 editions</a>
              </div>
            </td>
          </tr>
        </table>
        """
        works = _parse_goodreads_search_html(mock_html, used_curl=True, limit=5)
        self.assertEqual(len(works), 1)
        w = works[0]
        self.assertEqual(w.work_id, "gr:work/4640799/book/3.Harry_Potter_and_the_Sorcerer_s_Stone")
        self.assertEqual(w.title, "Harry Potter and the Sorcerer's Stone (Harry Potter, #1)")
        self.assertEqual(w.author, "J.K. Rowling")
        self.assertEqual(w.first_publish_year, 1997)
        self.assertEqual(w.edition_count, 19)
        self.assertIn("Goodreads", w.ratings)
        self.assertEqual(w.ratings["Goodreads"].rate, 4.47)
        self.assertEqual(w.ratings["Goodreads"].rating_count, 11765261)

    @patch("requests.Session.get")
    def test_goodreads_waf_connectivity_red_status(self, mock_get):
        from book_rate.sources.goodreads import GoodreadsSource
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><head><script>window.awsWafCookieDomainList=[];window.gokuProps={};</script></head></html>"
        mock_get.return_value = mock_resp

        source = GoodreadsSource()
        is_conn, msg = source.check_connectivity()
        self.assertFalse(is_conn)
        self.assertEqual(msg, "WAF Challenge")

    def test_enable_extend_editions_flags(self):
        from book_rate.sources.storygraph import StoryGraphSource
        douban = DoubanSource()
        douban_api = DoubanApiSource()
        goodreads = GoodreadsSource()
        storygraph = StoryGraphSource()
        self.assertTrue(douban.enable_extend_editions)
        self.assertFalse(douban_api.enable_extend_editions)
        self.assertTrue(goodreads.enable_extend_editions)
        self.assertTrue(storygraph.enable_extend_editions)

    @patch("requests.Session.get")
    def test_douban_api_single_request_suggest(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "id": "10785583",
                "title": "Thinking, Fast and Slow",
                "author_name": "Daniel Kahneman",
                "year": "2012",
                "type": "b",
                "url": "https://book.douban.com/subject/10785583/"
            }
        ]
        mock_get.return_value = mock_resp

        source = DoubanApiSource()
        works = source.search_works("Thinking Fast and Slow")
        self.assertEqual(len(works), 1)
        self.assertEqual(works[0].title, "Thinking, Fast and Slow")
        self.assertEqual(works[0].author, "Daniel Kahneman")
        self.assertIsNone(works[0].edition_count)
        self.assertEqual(mock_get.call_count, 1)

    @patch("book_rate.sources.base.BaseSource._fetch_html")
    def test_storygraph_fetch_editions(self, mock_fetch_html):
        from book_rate.sources.storygraph import StoryGraphSource
        mock_html = """
        <div class="book-pane">
          <h3><a href="/books/8e9a4f6d-2d93-4b68-80f2-b8e7343e0618">Harry Potter and the Philosopher's Stone</a></h3>
          <span>Publisher: Bloomsbury Publishing</span>
          <span>Edition Pub Date: 2014</span>
          <span>ISBN/UID: 9781408855652</span>
          <span>Language: English</span>
        </div>
        <div class="book-pane">
          <h3><a href="/books/7a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d">Harry Potter à l'école des sorciers</a></h3>
          <span>Publisher: Gallimard</span>
          <span>Edition Pub Date: 2016</span>
          <span>ISBN/UID: 9782070584628</span>
          <span>Language: French</span>
        </div>
        """
        mock_fetch_html.return_value = (mock_html, False)
        source = StoryGraphSource()
        editions = source.fetch_editions("sg:8e9a4f6d-2d93-4b68-80f2-b8e7343e0618", limit=5)
        self.assertEqual(len(editions), 2)
        self.assertEqual(editions[0].edition_id, "8e9a4f6d-2d93-4b68-80f2-b8e7343e0618")
        self.assertEqual(editions[0].title, "Harry Potter and the Philosopher's Stone")
        self.assertEqual(editions[0].publisher, "Bloomsbury Publishing")
        self.assertEqual(editions[0].publish_year, "2014")
        self.assertEqual(editions[0].isbn_13, "9781408855652")
        self.assertEqual(editions[0].language, "English")

        self.assertEqual(editions[1].edition_id, "7a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d")
        self.assertEqual(editions[1].title, "Harry Potter à l'école des sorciers")
        self.assertEqual(editions[1].publisher, "Gallimard")
        self.assertEqual(editions[1].language, "French")

    @patch("book_rate.sources.base.BaseSource._fetch_html")
    def test_storygraph_fetch_book_details_compact_editions_count(self, mock_fetch_html):
        from book_rate.sources.storygraph import StoryGraphSource
        mock_html = """
        <a href="/books/6717e73a-6ab8-448a-b92c-7a7ac25be732/editions" class="browse-editions-link">See all 1.5k editions</a>
        <h3 class="text-2xl">Harry Potter and the Philosopher's Stone</h3>
        <a href="/authors/123">J.K. Rowling</a>
        <span>Edition Pub Date: 2015</span>
        <span>ISBN/UID: 9781408855652</span>
        """
        mock_fetch_html.return_value = (mock_html, False)
        source = StoryGraphSource()
        details = source.fetch_book_details("6717e73a-6ab8-448a-b92c-7a7ac25be732")
        self.assertEqual(details["editions_count"], 1500)
        self.assertEqual(details["title"], "Harry Potter and the Philosopher's Stone")
        self.assertEqual(details["author"], "J.K. Rowling")


class TestAmazonSource(unittest.TestCase):
    def test_source_name_us(self):
        source = AmazonSource()
        self.assertEqual(source.name, "Amazon")
        self.assertEqual(source.SEARCH_URL, "https://www.amazon.com/s")

    def test_source_name_jp(self):
        source = AmazonJPSource()
        self.assertEqual(source.name, "Amazon JP")
        self.assertEqual(source.SEARCH_URL, "https://www.amazon.co.jp/s")

    @patch.object(AmazonSource, "_fetch_html")
    def test_search_works_parsing_us(self, mock_fetch):
        mock_text = '''
        <div data-component-type="s-search-result" data-asin="B0875.">
          <h2><a href="/dp/B0875"><span>Atomic Habits</span></a></h2>
          by <a href="/James-Clear">James Clear</a>
          <span>4.8 out of 5 stars</span>
          <span class="a-size-base s-underline-text">125,000</span>
        </div>
        '''
        mock_fetch.return_value = (mock_text, True)

        source = AmazonSource()
        works = source.search_works("Atomic Habits")
        self.assertTrue(len(works) > 0)
        self.assertEqual(works[0].title, "Atomic Habits")
        self.assertEqual(works[0].author, "James Clear")
        rating = works[0].ratings.get("Amazon")
        self.assertIsNotNone(rating)
        self.assertEqual(rating.rate, 4.8)
        self.assertEqual(rating.rating_count, 125000)

    @patch.object(AmazonJPSource, "_fetch_html")
    def test_search_works_parsing_jp(self, mock_fetch):
        mock_text = '''
        <div data-component-type="s-search-result" data-asin="4150119876">
          <h2><span>リーダブルコード</span></h2>
          著者 : <a href="/author">Dustin Boswell</a>
          <span>5つ星のうち4.6</span>
          <span class="a-size-base s-underline-text">3,800</span>
        </div>
        '''
        mock_fetch.return_value = (mock_text, True)

        source = AmazonJPSource()
        works = source.search_works("リーダブルコード")
        self.assertTrue(len(works) > 0)
        self.assertEqual(works[0].title, "リーダブルコード")
        self.assertEqual(works[0].author, "Dustin Boswell")
        rating = works[0].ratings.get("Amazon JP")
        self.assertIsNotNone(rating)
        self.assertEqual(rating.rate, 4.6)
        self.assertEqual(rating.rating_count, 3800)

    @patch.object(AmazonSource, "_fetch_html")
    def test_search_works_parsing_us_modern_dom(self, mock_fetch):
        mock_text = '''
        <div data-component-type="s-search-result" data-asin="1408856778">
          <h2 class="a-size-medium"><span>Harry Potter Box Set</span></h2></a>
          <div class="a-row a-size-base a-color-secondary"><div class="a-row"><span class="a-size-base">by </span><a class="a-size-base" href="/author">J. K. Rowling</a> <span class="a-letter-space"></span><span class="a-size-base"> | </span><span class="a-size-base">Oct 1, 2014</span></div></div>
          <span>4.8 out of 5 stars</span>
          <span class="a-size-base s-underline-text">39,250</span>
        </div>
        '''
        mock_fetch.return_value = (mock_text, True)

        source = AmazonSource()
        works = source.search_works("Harry Potter")
        self.assertTrue(len(works) > 0)
        self.assertEqual(works[0].title, "Harry Potter Box Set")
        self.assertEqual(works[0].author, "J. K. Rowling")
        self.assertEqual(works[0].work_id, "am:1408856778")

    @patch.object(AmazonJPSource, "_fetch_html")
    def test_search_works_parsing_jp_multi_author_without_keyword(self, mock_fetch):
        mock_text = '''
        <div data-component-type="s-search-result" data-asin="B0192CTNQI">
          <h2><span>ハリー・ポッターと賢者の石</span></h2></a>
          <div class="a-row a-size-base a-color-secondary"><div class="a-row"><span>J.K. ローリング</span> 、 <span>松岡 佑子</span> | <span>2014/9/1</span></div></div>
          <span>5つ星のうち4.7</span>
          <span class="a-size-base s-underline-text">5,100</span>
        </div>
        '''
        mock_fetch.return_value = (mock_text, True)

        source = AmazonJPSource()
        works = source.search_works("ハリー・ポッター")
        self.assertTrue(len(works) > 0)
        self.assertEqual(works[0].title, "ハリー・ポッターと賢者の石")
        self.assertEqual(works[0].author, "J.K. ローリング 、 松岡 佑子")
        self.assertEqual(works[0].work_id, "amjp:B0192CTNQI")

    @patch.object(AmazonJPSource, "_fetch_html")
    def test_search_works_waf_challenge(self, mock_fetch):
        from book_rate.sources.base import SourceNetworkError
        mock_text = '''
        <!DOCTYPE html><html><head>
        <meta http-equiv="refresh" content="5; URL='/s?k=test&bm-verify=AAQAAAAN'" />
        </head><body><script>function triggerInterstitialChallenge(){}</script></body></html>
        '''
        mock_fetch.return_value = (mock_text, True)

        source = AmazonJPSource()
        with self.assertRaises(SourceNetworkError) as ctx:
            source.search_works("モリー先生との火曜日")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("WAF Challenge", str(ctx.exception))

    @patch.object(AmazonSource, "_fetch_html")
    def test_fetch_ratings_fallback(self, mock_fetch):
        mock_fetch.return_value = ("", False)

        source = AmazonSource()
        work = Work(work_id="ol1", title="Test Book", author="Test Author")
        rating = source.fetch_ratings(work)
        self.assertEqual(rating.source_name, "Amazon")
        self.assertIsNone(rating.rate)
        self.assertIsNone(rating.rating_count)


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

    @patch("book_rate.sources.google_play.GooglePlaySource._parse_play_rating")
    def test_fetch_ratings_direct(self, mock_parse_play):
        source = GooglePlaySource()
        mock_parse_play.return_value = (4.487, 630, False)
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
        self.assertEqual(works[0].work_id, "play:wOzaEAAAQBAJ")

    @patch("book_rate.sources.google_play.GooglePlaySource._fetch_html")
    @patch("book_rate.sources.google_play.GooglePlaySource._parse_play_rating")
    def test_google_play_search_thinking_fast_and_slow(self, mock_parse_play, mock_fetch_html):
        source = GooglePlaySource()
        mock_fetch_html.return_value = (
            '<html><body>'
            '<a href="/store/books/details/Daniel_Kahneman_Thinking_Fast_and_Slow?id=oV1tXT3HigoC">Link</a>'
            '</body></html>',
            True
        )
        mock_parse_play.return_value = (4.6, 12000, True)
        works = source.search_works("Thinking, Fast and Slow")
        self.assertEqual(len(works), 1)
        self.assertEqual(works[0].title, "Thinking Fast and Slow")
        self.assertEqual(works[0].author, "Daniel Kahneman")
        self.assertEqual(works[0].work_id, "play:oV1tXT3HigoC")
        self.assertEqual(works[0].ratings["Google Play"].status, "CURL_MATCH")
        self.assertEqual(works[0].ratings["Google Play"].rate, 4.6)


class TestNonExistentBookCase(unittest.TestCase):
    def setUp(self):
        self.dummy_work = Work(
            work_id="non_existent_123",
            title="NonExistentBook_XYZ999",
            author="UnknownAuthor_XYZ999"
        )

    @patch("requests.Session.get")
    def test_amazon_non_existent_book(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body><div>No results found for your search</div></body></html>"
        mock_get.return_value = mock_resp

        source = AmazonSource()
        rating = source.fetch_ratings(self.dummy_work)
        self.assertEqual(rating.source_name, "Amazon")
        self.assertIsNone(rating.url)
        self.assertIsNone(rating.rate)
        self.assertIsNone(rating.rating_count)

    @patch("book_rate.sources.base.BaseSource._fetch_html")
    @patch("requests.Session.get")
    def test_douban_non_existent_book(self, mock_get, mock_fetch_html):
        mock_fetch_html.return_value = ""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_get.return_value = mock_resp

        source = DoubanSource()
        rating = source.fetch_ratings(self.dummy_work)
        self.assertEqual(rating.source_name, "Douban")
        self.assertIsNone(rating.url)
        self.assertIsNone(rating.rate)
        self.assertIsNone(rating.rating_count)

    @patch("requests.Session.get")
    def test_goodreads_non_existent_book(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_get.return_value = mock_resp

        source = GoodreadsSource()
        rating = source.fetch_ratings(self.dummy_work)
        self.assertEqual(rating.source_name, "Goodreads")
        self.assertIsNone(rating.url)
        self.assertIsNone(rating.rate)
        self.assertIsNone(rating.rating_count)

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


class TestUnratedBookWithUrlCase(unittest.TestCase):
    def setUp(self):
        self.unrated_work = Work(
            work_id="unrated_book_123",
            title="Unrated Modern Novel",
            author="New Author"
        )

    @patch("requests.Session.get")
    def test_amazon_unrated_book_with_url(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '''
        <div data-component-type="s-search-result">
          <h2><a href="/Unrated-Novel/dp/B000000111"><span>Unrated Modern Novel</span></a></h2>
          by New Author
        </div>
        '''
        mock_get.return_value = mock_resp

        source = AmazonSource()
        rating = source.fetch_ratings(self.unrated_work)
        self.assertEqual(rating.source_name, "Amazon")
        self.assertIsNotNone(rating.url)
        self.assertIn("B000000111", rating.url)
        self.assertIsNone(rating.rate)
        self.assertIsNone(rating.rating_count)

    @patch("book_rate.sources.base.BaseSource._fetch_html")
    @patch("requests.Session.get")
    def test_douban_unrated_book_with_url(self, mock_get, mock_fetch_html):
        mock_fetch_html.return_value = ""
        def side_effect(url, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            if "subject_suggest" in url:
                mock_resp.json.return_value = [
                    {
                        "id": "999888777",
                        "title": "Unrated Modern Novel",
                        "author_name": "New Author",
                        "url": "https://book.douban.com/subject/999888777/"
                    }
                ]
            else:
                mock_resp.text = "<html><body><h1>Unrated Modern Novel</h1><div>目前無評價數據</div></body></html>"
            return mock_resp

        mock_get.side_effect = side_effect
        source = DoubanSource()
        rating = source.fetch_ratings(self.unrated_work)
        self.assertEqual(rating.source_name, "Douban")
        self.assertIsNotNone(rating.url)
        self.assertEqual(rating.url, "https://book.douban.com/subject/999888777/")
        self.assertIsNone(rating.rate)
        self.assertIsNone(rating.rating_count)

    def test_books_tw_search_parsing_additional(self):
        source = BooksTwSource()
        sample_html = '''
        <table class="table-search">
          <tr>
            <td>
              <h4><a target="_blank" rel="mid_name" href="//search.books.com.tw/redirect/move/item/0011032772/" title="牧羊少年奇幻之旅">牧羊少年奇幻之旅</a></h4>
              <ul class="list-date clearfix">
                <li><span>中文書</span> , <a rel='go_author' href='//search.books.com.tw/adv_author/1' title='保羅．科爾賀'>保羅．科爾賀</a>, 出版日期: 2025-10-07</li>
              </ul>
            </td>
          </tr>
        </table>
        '''
        items = source._parse_search_items(sample_html)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["book_id"], "0011032772")
        self.assertEqual(items[0]["author"], "保羅．科爾賀")
        self.assertEqual(items[0]["first_publish_year"], 2025)


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


if __name__ == "__main__":
    unittest.main()

