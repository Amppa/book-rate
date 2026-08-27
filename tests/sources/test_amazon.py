import unittest
from unittest.mock import patch, MagicMock

from book_rate.models import Work, SourceRating
from book_rate.sources.amazon import AmazonSource, AmazonJPSource


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



class TestAmazonAdditional(unittest.TestCase):
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
        self.dummy_work = Work(
            work_id="non_existent_123",
            title="A Very Unique Non Existent Book Title 999999",
            author="Ghost Author"
        )
        self.unrated_work = Work(
            work_id="unrated_book_123",
            title="Unrated Modern Novel",
            author="New Author"
        )


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
    @patch("requests.Session.get")
    def test_amazon_non_existent_book(self, mock_get, mock_fetch_html):
        mock_fetch_html.return_value = ("", False)
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
    def test_amazon_unrated_book_with_url(self, mock_get, mock_fetch_html):
        html = '''
        <div data-component-type="s-search-result">
          <h2><a href="/Unrated-Novel/dp/B000000111"><span>Unrated Modern Novel</span></a></h2>
          by New Author
        </div>
        '''
        mock_fetch_html.return_value = (html, False)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html
        mock_get.return_value = mock_resp

        source = AmazonSource()
        rating = source.fetch_ratings(self.unrated_work)
        self.assertEqual(rating.source_name, "Amazon")
        self.assertIsNotNone(rating.url)
        self.assertIn("B000000111", rating.url)
        self.assertIsNone(rating.rate)
        self.assertIsNone(rating.rating_count)


    def test_amazon_jp_asin_and_language_parsing(self):
        source = AmazonJPSource()
        block = """
        <div data-component-type="s-search-result" class="s-result-item">
          <h2><span class="a-size-medium">Tuesdays with Morrie (English Edition)</span></h2>
          <div class="a-row a-color-secondary">
            <span>by Mitch Albom</span> | <span>2007/6/29</span>
          </div>
          <a href="/dp/B001PMTRX8">Link</a>
          <span class="a-icon-alt">5つ星のうち4.6</span>
          <span class="a-size-base s-underline-text">15,400</span>
        </div>
        """
        work = source._parse_search_block(block, "Tuesdays with Morrie")
        self.assertIsNotNone(work)
        self.assertEqual(work.work_id, "amjp:B001PMTRX8")
        self.assertEqual(work.isbn, "B001PMTRX8")
        rating = work.ratings["Amazon JP"]
        self.assertEqual(rating.language, "英语")
        self.assertEqual(rating.rate, 4.6)
        self.assertEqual(rating.rating_count, 15400)


    def test_amazon_search_block_gujarati_language(self):
        source = AmazonSource()
        block = """
        <div data-component-type="s-search-result" class="s-result-item">
          <h2><span class="a-size-medium">Tuesdays with Morrie (Gujarati Edition)</span></h2>
          <div class="a-row a-color-secondary">
            <span>by Mitch Albom</span> | <span>April 4, 2017</span>
          </div>
          <a class="a-text-bold" href="/dp/B071XVWXFH">Kindle Edition</a>
          <a href="/dp/B071XVWXFH">Link</a>
          <span class="a-icon-alt">3.6 out of 5 stars</span>
          <span class="a-size-base s-underline-text">100</span>
        </div>
        """
        work = source._parse_search_block(block, "Tuesdays with Morrie")
        self.assertIsNotNone(work)
        self.assertEqual(work.work_id, "am:B071XVWXFH")
        self.assertEqual(work.isbn, "B071XVWXFH")
        rating = work.ratings["Amazon"]
        self.assertEqual(rating.language, "Gujarati")
        self.assertEqual(rating.publish_date, "April 4, 2017")
        self.assertEqual(rating.rate, 3.6)
        self.assertEqual(rating.rating_count, 100)
        self.assertEqual(rating.metadata.get("asin"), "B071XVWXFH")



if __name__ == "__main__":
    unittest.main()
