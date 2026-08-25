import unittest
import json
from unittest.mock import patch, MagicMock

from book_rate.orchestrator import RatingOrchestrator
from book_rate.registry import SourceRegistry
from book_rate.models import Work, Edition, SourceRating, RatingRequestPayload
from book_rate.sources.google_books import GoogleBooksSource
from book_rate.sources.douban import DoubanSource, DoubanApiSource
from book_rate.sources.amazon import AmazonJPSource
from book_rate.sources.goodreads import GoodreadsSource
from book_rate.sources.storygraph import StoryGraphSource
from book_rate.sources.books_tw import BooksTwSource
from book_rate.sources.readmoo import ReadmooSource
from book_rate.sources.open_library import OpenLibrarySource
from book_rate.utils.formatters import format_rating_response


class TestRatingOrchestrator(unittest.TestCase):
    @patch("book_rate.work_preparer.WorkPreparer.resolve_work_editions_and_ol_rating")
    @patch("book_rate.sources.readmoo.ReadmooSource.fetch_ratings")
    def test_evaluate_all_sync(self, mock_rm_ratings, mock_resolve):
        mock_resolve.return_value = (
            SourceRating(source_name="Open Library"),
            [],
            Work(work_id="gr:12345", title="Thinking, Fast and Slow", author="Daniel Kahneman"),
            {},
        )
        mock_rm_ratings.return_value = SourceRating(source_name="Readmoo", rate=3.8, rating_count=50, status="MATCH")
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

    @patch("book_rate.work_preparer.WorkPreparer.resolve_work_editions_and_ol_rating")
    @patch("book_rate.sources.readmoo.ReadmooSource.fetch_ratings")
    def test_evaluate_stream(self, mock_rm_ratings, mock_resolve):
        mock_resolve.return_value = (
            SourceRating(source_name="Open Library"),
            [],
            Work(work_id="gr:12345", title="Thinking, Fast and Slow", author="Daniel Kahneman"),
            {},
        )
        mock_rm_ratings.return_value = SourceRating(source_name="Readmoo", rate=3.8, rating_count=50, status="MATCH")
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
        self.assertEqual(w.work_id, "gr:4640799")
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
        self.assertEqual(w.work_id, "gr:4640799")
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



class TestOrchestratorKeyedGoogleInstance(unittest.TestCase):
    def _make_orchestrator_with_shared(self):
        shared = MagicMock()
        shared.fetch_ratings.return_value = SourceRating(
            source_name="Google Books", rate=3.5, rating_count=20, status="MATCH"
        )
        orch = RatingOrchestrator(source_instances={"google_books": shared})
        return orch, shared

    @staticmethod
    def _fake_prepare(mock_resolve):
        mock_resolve.return_value = (
            SourceRating(source_name="Open Library"),
            [],
            Work(work_id="OL1", title="T", author="A"),
            {},
        )

    @patch.object(SourceRegistry, "create_source")
    @patch("book_rate.work_preparer.WorkPreparer.resolve_work_editions_and_ol_rating")
    def test_google_key_builds_transient_keyed_instance(self, mock_resolve, mock_create):
        self._fake_prepare(mock_resolve)
        orch, shared = self._make_orchestrator_with_shared()
        keyed = MagicMock()
        keyed.fetch_ratings.return_value = SourceRating(
            source_name="Google Books", rate=4.4, rating_count=90, status="MATCH"
        )
        mock_create.return_value = keyed

        req = RatingRequestPayload(
            work_id="OL1", title="T", author="A",
            engines=["google_books"], google_key="USER_KEY"
        )
        res = orch.evaluate_all(req)

        mock_create.assert_called_once()
        self.assertEqual(mock_create.call_args.kwargs.get("api_key"), "USER_KEY")
        self.assertEqual(res["ratings"]["google_books"]["average"], 4.4)
        shared.fetch_ratings.assert_not_called()

    @patch.object(SourceRegistry, "create_source")
    @patch("book_rate.work_preparer.WorkPreparer.resolve_work_editions_and_ol_rating")
    def test_without_key_shared_instance_is_used(self, mock_resolve, mock_create):
        self._fake_prepare(mock_resolve)
        orch, shared = self._make_orchestrator_with_shared()

        req = RatingRequestPayload(
            work_id="OL1", title="T", author="A", engines=["google_books"]
        )
        res = orch.evaluate_all(req)

        mock_create.assert_not_called()
        shared.fetch_ratings.assert_called_once()
        self.assertEqual(res["ratings"]["google_books"]["average"], 3.5)



class TestDoubanApiWorkPreparation(unittest.TestCase):
    def test_dbapi_routes_to_douban_details_not_open_library(self):
        """Regression: dbapi: ids must resolve cleanly with douban_api status, never
        fall into the Open Library branch that fabricated /works/dbapi:x ids."""
        from book_rate.work_preparer import WorkPreparer
        preparer = WorkPreparer()
        ol_rating, editions, target_work, crawler_status = \
            preparer.resolve_work_editions_and_ol_rating(
                work_id="dbapi:10785583", title="Mock Title", author="Mock Author", active_title_sources=[]
            )

        self.assertIn("douban_api", crawler_status)
        self.assertEqual(target_work.work_id, "dbapi:10785583")
        self.assertEqual(target_work.title, "Mock Title")
        self.assertEqual(target_work.author, "Mock Author")
        self.assertFalse(target_work.work_id.startswith("/works/dbapi"))
        self.assertEqual(editions, [])

    def test_quick_mode_custom_work_id_preparation(self):
        """Path A: Quick Mode custom: prefix must resolve cleanly in zero-I/O."""
        from book_rate.work_preparer import WorkPreparer
        preparer = WorkPreparer()
        ol_rating, editions, target_work, crawler_status = \
            preparer.resolve_work_editions_and_ol_rating(
                work_id="custom:原子習慣", title="原子習慣", author="詹姆斯·克利爾", active_title_sources=["open_library"]
            )

        self.assertIn("custom", crawler_status)
        self.assertEqual(target_work.work_id, "custom:原子習慣")
        self.assertEqual(target_work.title, "原子習慣")
        self.assertEqual(target_work.author, "詹姆斯·克利爾")
        self.assertEqual(editions, [])



class TestFormatRatingResponse(unittest.TestCase):
    def test_format_rating_response_book_info(self):
        from book_rate.utils.formatters import format_rating_response
        rating = SourceRating(
            source_name="Books.com.tw",
            rate=4.8,
            rating_count=120,
            url="https://www.books.com.tw/products/001",
            title="魔戒",
            author="J.R.R. Tolkien",
            translator="朱學恆",
            publisher="聯經出版公司",
            publish_date="2020/01/01",
            isbn="9789570850000",
            language="繁體中文",
            original_title="The Lord of the Rings",
            work_id="bk:001",
            edition_count=10
        )
        res = format_rating_response("books_tw", rating, "Fallback")
        self.assertIn("book_info", res)
        self.assertEqual(res["book_info"]["author"], "J.R.R. Tolkien")
        self.assertEqual(res["book_info"]["translator"], "朱學恆")
        self.assertEqual(res["book_info"]["publisher"], "聯經出版公司")
        self.assertEqual(res["book_info"]["publish_date"], "2020/01/01")
        self.assertEqual(res["book_info"]["language"], "繁體中文")
        self.assertEqual(res["book_info"]["original_title"], "The Lord of the Rings")
        self.assertEqual(res["book_info"]["edition_count"], 10)
        self.assertEqual(res["book_info"]["isbn"], "9789570850000")
        self.assertEqual(res["book_info"]["work_id"], "bk:001")



if __name__ == "__main__":
    unittest.main()
